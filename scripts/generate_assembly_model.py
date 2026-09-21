#!/usr/bin/env python3
"""Generate an inspectable STEP assembly and deterministic fixed-view renders.

CadQuery/OCCT is intentionally an optional local dependency. CI installs the
pinned versions in requirements-assembly.txt and treats every output as required.
All placement data comes from the same configuration and geometry functions as
validate_geometry.py; this script contains no alternate assembly transform.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from math import sqrt
from pathlib import Path
from typing import Any

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_CLEARANCE_Y,
    BLADERUNNER_CLEARANCE_Z,
    BOARD_THICKNESS_MM,
    COMPUTE_BLADE_STEP_J3_ANCHOR_MM,
    DDA_ASSEMBLY_BASIS,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    DDA_ROTATION_180,
    J1_ORIGIN_MM,
    J2_BODY_HEIGHT_MM,
    J2_HEADER_PLASTIC_BACK_LOCAL_X_MM,
    J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
    J2_HEADER_PLASTIC_Y_BOUNDS_MM,
    J2_MATING_POST_LENGTH_MM,
    J2_SOLDER_TAIL_LENGTH_MM,
    J2_PIN1_CENTER_Z_MM,
    J2_PIN2_CENTER_Z_MM,
    J2_MATING_DIRECTION,
    MAX_ASSEMBLED_Z_DEPTH_MM,
)
from fetch_reference_cad import REFERENCE_DIR
from mechanical_geometry import (
    Box,
    assembly_axis_vectors,
    connector_boxes,
    dda_boxes,
    relative_j2,
)
from validate_geometry import (
    PCB,
    board_bounds,
    check_references,
    validate_connector_constraints,
    validate_footprint,
    variant_checks,
)
from verify_connectivity import children, parse_sexpr, properties, transformed_pad


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "mechanical" / "generated"
COMPUTE_BLADE_STEP = REFERENCE_DIR / "compute_blade_dev.step"
FULL_ASSEMBLY = OUTPUT / "full_assembly.step"
FULL_ASSEMBLY_WITH_BLADERUNNER = OUTPUT / "full_assembly_with_bladerunner.step"
LIGHTWEIGHT_ASSEMBLY = OUTPUT / "full_assembly_lightweight.step"
MANIFEST = OUTPUT / "full_assembly_manifest.json"

RENDERS = {
    "render_top.png": {
        # +Z camera looking along -Z: DDA PCB must appear edge-on.
        "offset": (16.0, -7.0, 320.0), "focus": (16.0, -7.0, 10.0),
        "up": (0.0, 1.0, 0.0), "scale": 55.0,
    },
    "render_side.png": {
        # -Y camera looking along +Y: DDA PCB face must be visible.
        "offset": (16.0, -320.0, 15.0), "focus": (16.0, -7.0, 15.0),
        "up": (0.0, 0.0, 1.0), "scale": 35.0,
    },
    "render_end.png": {
        # +X camera looking along -X: upright PCB and Z-stacked rows are visible.
        "offset": (320.0, -7.0, 15.0), "focus": (16.0, -7.0, 15.0),
        "up": (0.0, 0.0, 1.0), "scale": 28.0,
    },
    "render_iso.png": {
        "offset": (250.0, -230.0, 190.0), "focus": (15.0, 0.0, 5.0),
        "up": (0.0, 0.0, 1.0), "scale": 125.0,
    },
    "render_j1_closeup.png": {
        "offset": (-28.0, -32.0, 28.0), "focus": (0.0, 4.5, 5.0),
        "up": (0.0, 0.0, 1.0), "scale": 15.0,
    },
    "render_j2_closeup.png": {
        "offset": (45.0, -48.0, 34.0), "focus": (16.0, -10.0, 13.0),
        "up": (0.0, 0.0, 1.0), "scale": 22.0,
    },
}


def require_cadquery() -> Any:
    try:
        import cadquery as cq
    except ImportError as exc:
        raise RuntimeError(
            "assembly generation requires the pinned packages in requirements-assembly.txt"
        ) from exc
    if cq.__version__ != "2.5.2":
        raise RuntimeError(f"expected CadQuery 2.5.2, found {cq.__version__}")
    return cq


def validate_selected_geometry() -> list[str]:
    if DDA_ROTATION_180:
        raise RuntimeError("full assembly only supports the confirmed/default DDA orientation")
    errors, notes = check_references()
    errors.extend(validate_footprint())
    constraint_errors, constraint_notes = validate_connector_constraints(False)
    errors.extend(constraint_errors)
    notes.extend(constraint_notes)
    variant_errors, variant_notes = variant_checks(False)
    errors.extend(variant_errors)
    notes.extend(variant_notes)
    if errors:
        raise RuntimeError("validated geometry state failed: " + "; ".join(errors))
    return notes


def globalize(box: Box) -> Box:
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    return Box(
        box.name,
        box.xmin + ax, box.xmax + ax,
        box.ymin + ay, box.ymax + ay,
        box.zmin + az, box.zmax + az,
    )


def make_box(cq: Any, box: Box) -> Any:
    return cq.Solid.makeBox(
        box.xmax - box.xmin,
        box.ymax - box.ymin,
        box.zmax - box.zmin,
        cq.Vector(box.xmin, box.ymin, box.zmin),
    )


def pcb_pad_positions() -> dict[str, tuple[float, float]]:
    tree = parse_sexpr(PCB.read_text(encoding="utf-8"))
    result: dict[str, tuple[float, float]] = {}
    for footprint in children(tree, "footprint"):
        reference = properties(footprint).get("Reference")
        if reference not in {"J1", "J2"}:
            continue
        for pad in children(footprint, "pad"):
            x, y = transformed_pad(footprint, pad)
            result[f"{reference}.{pad[1]}"] = (x - J1_ORIGIN_MM[0], y - J1_ORIGIN_MM[1])
    if set(result) != {
        *(f"J1.{pin}" for pin in range(1, 11)),
        *(f"J2.{pin}" for pin in range(1, 13)),
    }:
        raise RuntimeError("could not resolve every J1/J2 pad from the generated PCB")
    return result


def actual_adapter_board(cq: Any, pads: dict[str, tuple[float, float]]) -> Any:
    xmin, xmax, ymin, ymax = board_bounds()
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    board = cq.Solid.makeBox(
        xmax - xmin,
        ymax - ymin,
        BOARD_THICKNESS_MM,
        cq.Vector(ax + xmin, ay + ymin, az + ADAPTER_Z_ABOVE_BLADE_MM),
    )
    for x, y in pads.values():
        hole = cq.Solid.makeCylinder(
            0.50,
            BOARD_THICKNESS_MM + 0.2,
            cq.Vector(ax + x, ay + y, az + ADAPTER_Z_ABOVE_BLADE_MM - 0.1),
            cq.Vector(0, 0, 1),
        )
        board = board.cut(hole)
    return board


def j1_shapes(cq: Any, pads: dict[str, tuple[float, float]]) -> list[tuple[str, Any, Any]]:
    body_box = globalize(next(box for box in connector_boxes() if box.name == "j1_socket_body"))
    body = make_box(cq, body_box)
    for pin in range(1, 11):
        x, y = pads[f"J1.{pin}"]
        hole = cq.Solid.makeCylinder(
            0.72,
            body_box.zmax - body_box.zmin + 0.2,
            cq.Vector(
                COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0] + x,
                COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1] + y,
                body_box.zmin - 0.1,
            ),
            cq.Vector(0, 0, 1),
        )
        body = body.cut(hole)
    contacts = []
    for pin in range(1, 11):
        x, y = pads[f"J1.{pin}"]
        contacts.append(
            cq.Solid.makeCylinder(
                0.32,
                body_box.zmax - body_box.zmin,
                cq.Vector(
                    COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0] + x,
                    COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1] + y,
                    body_box.zmin,
                ),
                cq.Vector(0, 0, 1),
            )
        )
    return [
        ("J1_SLW_105_01_G_D_approx_plastic", body, cq.Color(0.12, 0.12, 0.12)),
        ("J1_approx_contacts", cq.Compound.makeCompound(contacts), cq.Color(0.72, 0.58, 0.18)),
    ]


def j2_shapes(cq: Any, pads: dict[str, tuple[float, float]]) -> list[tuple[str, Any, Any]]:
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    j2_x, j2_y = relative_j2()
    body = Box(
        "j2_plastic",
        ax + j2_x + J2_HEADER_PLASTIC_Y_BOUNDS_MM[0],
        ax + j2_x + J2_HEADER_PLASTIC_Y_BOUNDS_MM[1],
        ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
        ay + j2_y - J2_HEADER_PLASTIC_BACK_LOCAL_X_MM,
        az + ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
        az + ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM + J2_BODY_HEIGHT_MM,
    )
    post_shapes = []
    tail_shapes = []
    pin_size = 0.635
    for pin in range(1, 13):
        px, py = pads[f"J2.{pin}"]
        center_z = J2_PIN1_CENTER_Z_MM if pin % 2 else J2_PIN2_CENTER_Z_MM
        post_shapes.append(
            cq.Solid.makeBox(
                pin_size,
                J2_MATING_POST_LENGTH_MM,
                pin_size,
                cq.Vector(
                    ax + px - pin_size / 2,
                    ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM - J2_MATING_POST_LENGTH_MM,
                    az + center_z - pin_size / 2,
                ),
            )
        )
        tail_bottom_z = ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM - J2_SOLDER_TAIL_LENGTH_MM
        vertical_height = center_z - tail_bottom_z
        tail_shapes.append(
            cq.Solid.makeBox(
                pin_size,
                pin_size,
                vertical_height,
                cq.Vector(
                    ax + px - pin_size / 2,
                    ay + py - pin_size / 2,
                    az + tail_bottom_z,
                ),
            )
        )
        tail_shapes.append(
            cq.Solid.makeBox(
                pin_size,
                max(0.1, py - (j2_y - J2_HEADER_PLASTIC_BACK_LOCAL_X_MM)),
                pin_size,
                cq.Vector(
                    ax + px - pin_size / 2,
                    ay + j2_y - J2_HEADER_PLASTIC_BACK_LOCAL_X_MM,
                    az + center_z - pin_size / 2,
                ),
            )
        )
    return [
        ("J2_TSW_106_08_G_D_RA_approx_plastic", make_box(cq, body), cq.Color(0.10, 0.10, 0.10)),
        ("J2_manufacturer_dimensioned_posts", cq.Compound.makeCompound(post_shapes), cq.Color(0.78, 0.62, 0.18)),
        ("J2_simplified_bent_tails", cq.Compound.makeCompound(tail_shapes), cq.Color(0.68, 0.54, 0.15)),
    ]


def dda_shapes(cq: Any) -> list[tuple[str, Any, Any]]:
    colors = {
        "dda_pcb": cq.Color(0.08, 0.38, 0.16),
        "dda_socket": cq.Color(0.08, 0.08, 0.08),
        "dda_gnss_envelope": cq.Color(0.24, 0.48, 0.76, 0.55),
        "dda_battery_rtc_envelope": cq.Color(0.82, 0.55, 0.17, 0.55),
    }
    return [
        (f"DDA_{box.name}_simplified", make_box(cq, globalize(box)), colors[box.name])
        for box in dda_boxes(False)
    ]


def marker_shapes(cq: Any, pads: dict[str, tuple[float, float]]) -> list[tuple[str, Any, Any]]:
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    _, j2_y = relative_j2()
    pin1_x, pin1_y = pads["J2.1"]
    j1_axis = cq.Solid.makeCylinder(
        0.16, 11.0, cq.Vector(ax, ay, az), cq.Vector(0, 0, 1)
    )
    j2_axis = cq.Solid.makeCylinder(
        0.16,
        J2_MATING_POST_LENGTH_MM + 4.0,
        cq.Vector(ax + pin1_x, ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM, az + J2_PIN1_CENTER_Z_MM),
        cq.Vector(*J2_MATING_DIRECTION),
    )
    pin1 = cq.Solid.makeBox(
        0.9, 0.9, 0.9,
        cq.Vector(
            ax + pin1_x - 0.45,
            ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM - J2_MATING_POST_LENGTH_MM + DDA_MIN_ACCEPTABLE_INSERTION_MM - 0.45,
            az + J2_PIN1_CENTER_Z_MM - 0.45,
        ),
    )
    return [
        ("MARKER_J1_mating_axis", j1_axis, cq.Color(0.85, 0.15, 0.85)),
        ("MARKER_J2_minus_Y_SSD_side_mating_axis", j2_axis, cq.Color(0.95, 0.70, 0.05)),
        ("MARKER_DDA_physical_pin_1", pin1, cq.Color(0.90, 0.05, 0.05)),
    ]


def clearance_frame(cq: Any, blade_bounds: Any) -> list[tuple[str, Any, Any]]:
    """Visualize the exact Y/Z envelope used by validation, not a guessed STL transform."""
    _, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    ymin, ymax = (ay + value for value in BLADERUNNER_CLEARANCE_Y)
    zmin, zmax = (az + value for value in BLADERUNNER_CLEARANCE_Z)
    xmin, xmax = blade_bounds.xmin, blade_bounds.xmax
    t = 0.8
    rails = [
        Box("low_z", xmin, xmax, ymin, ymin + t, zmin, zmin + t),
        Box("low_z_2", xmin, xmax, ymax - t, ymax, zmin, zmin + t),
        Box("high_z", xmin, xmax, ymin, ymin + t, zmax - t, zmax),
        Box("high_z_2", xmin, xmax, ymax - t, ymax, zmax - t, zmax),
    ]
    color = cq.Color(0.55, 0.55, 0.58, 0.45)
    return [
        (f"BladeRunner_validated_clearance_frame_{index}", make_box(cq, box), color)
        for index, box in enumerate(rails, start=1)
    ]


def make_assembly(cq: Any, include_clearance: bool) -> tuple[Any, Any, list[str]]:
    blade = cq.importers.importStep(str(COMPUTE_BLADE_STEP))
    blade_shape = blade.val()
    blade_bounds = blade_shape.BoundingBox()
    pads = pcb_pad_positions()
    parts: list[tuple[str, Any, Any]] = [
        ("Compute_Blade_DEV_official_STEP", blade_shape, cq.Color(0.55, 0.57, 0.60)),
        ("Adapter_PCB_actual_outline_and_holes_0p8mm", actual_adapter_board(cq, pads), cq.Color(0.12, 0.48, 0.22)),
        *j1_shapes(cq, pads),
        *j2_shapes(cq, pads),
        *dda_shapes(cq),
        *marker_shapes(cq, pads),
    ]
    if include_clearance:
        parts.extend(clearance_frame(cq, blade_bounds))
    assembly = cq.Assembly(name=("full_assembly_with_bladerunner_context" if include_clearance else "full_assembly"))
    for name, shape, color in parts:
        assembly.add(shape, name=name, color=color)
    return assembly, blade_bounds, [name for name, _, _ in parts]


def _render_parts(pads: dict[str, tuple[float, float]]) -> list[tuple[str, Box, tuple[int, int, int]]]:
    """Return shared-coordinate solids for deterministic software rendering."""
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    blade = Box("Compute Blade PCB", -0.50008, 250.016, 0.006, 42.505, -1.6, 0.0)
    adapter = globalize(
        Box(
            "Adapter PCB",
            *board_bounds(),
            ADAPTER_Z_ABOVE_BLADE_MM,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
        )
    )
    colors = {
        "blade": (76, 103, 126),
        "adapter": (34, 139, 75),
        "plastic": (35, 35, 38),
        "metal": (196, 153, 45),
        "dda": (22, 112, 52),
        "socket": (24, 24, 26),
        "gnss": (72, 126, 190),
        "battery": (204, 137, 42),
    }
    parts: list[tuple[str, Box, tuple[int, int, int]]] = [
        (blade.name, blade, colors["blade"]),
        (adapter.name, adapter, colors["adapter"]),
    ]
    for box in connector_boxes():
        if box.name in {
            "compute_blade_header_exposed_posts",
            "j2_mating_posts",
            "j2_solder_tails",
        }:
            continue
        color = colors["metal"] if "post" in box.name or "tail" in box.name else colors["plastic"]
        parts.append((box.name, globalize(box), color))
    for box in dda_boxes(False):
        if box.name in {"dda_gnss_envelope", "dda_battery_rtc_envelope"}:
            continue
        color_key = {
            "dda_pcb": "dda",
            "dda_socket": "socket",
            "dda_gnss_envelope": "gnss",
            "dda_battery_rtc_envelope": "battery",
        }[box.name]
        parts.append((box.name, globalize(box), colors[color_key]))

    pin_size = 0.635
    for pin in range(1, 11):
        px, py = pads[f"J1.{pin}"]
        post = Box(
            f"Compute Blade J1 post {pin}",
            ax + px - pin_size / 2,
            ax + px + pin_size / 2,
            ay + py - pin_size / 2,
            ay + py + pin_size / 2,
            az + 2.5,
            az + 9.0,
        )
        parts.append((post.name, post, colors["metal"]))

    # Individual posts and bent tails expose the two Z-stacked mating rows;
    # the aggregate connector boxes above remain the conservative keepouts.
    _, j2_y = relative_j2()
    tail_bottom_z = ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM - J2_SOLDER_TAIL_LENGTH_MM
    for pin in range(1, 13):
        px, py = pads[f"J2.{pin}"]
        center_z = J2_PIN1_CENTER_Z_MM if pin % 2 else J2_PIN2_CENTER_Z_MM
        post = Box(
            f"J2 post {pin}",
            ax + px - pin_size / 2,
            ax + px + pin_size / 2,
            ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM - J2_MATING_POST_LENGTH_MM,
            ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
            az + center_z - pin_size / 2,
            az + center_z + pin_size / 2,
        )
        tail = Box(
            f"J2 tail {pin}",
            ax + px - pin_size / 2,
            ax + px + pin_size / 2,
            ay + py - pin_size / 2,
            ay + py + pin_size / 2,
            az + tail_bottom_z,
            az + center_z,
        )
        parts.extend(((post.name, post, colors["metal"]), (tail.name, tail, colors["metal"])))
    pin1_marker = Box(
        "DDA physical pin 1",
        ax + pads["J2.1"][0] - 0.55,
        ax + pads["J2.1"][0] + 0.55,
        ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM - J2_MATING_POST_LENGTH_MM
        + DDA_MIN_ACCEPTABLE_INSERTION_MM - 0.55,
        ay + j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM - J2_MATING_POST_LENGTH_MM
        + DDA_MIN_ACCEPTABLE_INSERTION_MM + 0.55,
        az + J2_PIN1_CENTER_Z_MM - 0.55,
        az + J2_PIN1_CENTER_Z_MM + 0.55,
    )
    parts.append((pin1_marker.name, pin1_marker, (220, 35, 45)))
    return parts


def _unit3(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = sqrt(sum(value * value for value in vector))
    return tuple(value / length for value in vector)


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(a[index] * b[index] for index in range(3))


def _box_faces(
    box: Box,
) -> list[tuple[tuple[float, float, float], list[tuple[float, float, float]]]]:
    x0, x1, y0, y1, z0, z1 = box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax
    return [
        ((-1, 0, 0), [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]),
        ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
        ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
        ((0, 1, 0), [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)]),
        ((0, 0, -1), [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)]),
        ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
    ]


def render_all(parts: list[tuple[str, Box, tuple[int, int, int]]]) -> dict[str, dict[str, int]]:
    """Render orthographic views in software and reject blank images."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1200, 900
    background = (245, 245, 245)
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    metrics: dict[str, dict[str, int]] = {}
    for filename, view in RENDERS.items():
        position = tuple((ax, ay, az)[index] + view["offset"][index] for index in range(3))
        focus = tuple((ax, ay, az)[index] + view["focus"][index] for index in range(3))
        direction = _unit3(tuple(focus[index] - position[index] for index in range(3)))
        right = _unit3(_cross(direction, view["up"]))
        screen_up = _unit3(_cross(right, direction))
        pixels_per_mm = height / (2.0 * view["scale"])
        faces = []
        for name, box, base_color in parts:
            for normal, vertices in _box_faces(box):
                center = tuple(
                    sum(vertex[index] for vertex in vertices) / 4.0 for index in range(3)
                )
                depth = _dot(
                    tuple(center[index] - position[index] for index in range(3)), direction
                )
                shade = 0.62 + 0.32 * abs(_dot(normal, direction))
                color = tuple(
                    max(0, min(255, round(channel * shade))) for channel in base_color
                )
                polygon = []
                for vertex in vertices:
                    relative = tuple(vertex[index] - focus[index] for index in range(3))
                    polygon.append(
                        (
                            width / 2 + _dot(relative, right) * pixels_per_mm,
                            height / 2 - _dot(relative, screen_up) * pixels_per_mm,
                        )
                    )
                faces.append((depth, polygon, color, name))
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        for _depth, polygon, color, _name in sorted(
            faces, key=lambda item: item[0], reverse=True
        ):
            draw.polygon(polygon, fill=color, outline=(25, 25, 28))
        draw.rectangle((0, 0, width, 34), fill=(255, 255, 255))
        title = filename.replace("render_", "").replace(".png", "").upper()
        draw.text(
            (12, 10),
            title + " — X long axis, Y width, Z outward",
            fill=(15, 15, 18),
            font=ImageFont.load_default(),
        )
        path = OUTPUT / filename
        image.save(path, format="PNG", optimize=True)
        foreground = sum(
            pixel != background for pixel in image.crop((0, 35, width, height)).getdata()
        )
        unique_colors = len(image.getcolors(maxcolors=1_000_000) or [])
        minimum_foreground = int(width * (height - 35) * 0.01)
        if foreground < minimum_foreground or unique_colors < 8:
            raise RuntimeError(
                f"render is blank or near-uniform: {path}; "
                f"foreground={foreground}, colors={unique_colors}"
            )
        metrics[filename] = {
            "foreground_pixels": foreground,
            "unique_colors": unique_colors,
        }
    return metrics


def verify_step(
    cq: Any, path: Path, minimum_solids: int, required_names: list[str] | None = None
) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size < 100_000:
        raise RuntimeError(f"STEP export failed or is unexpectedly small: {path}")
    if required_names:
        text = path.read_text(encoding="utf-8", errors="ignore")
        missing = [name for name in required_names if name not in text]
        if missing:
            raise RuntimeError(f"STEP assembly tree is missing named parts: {missing}")
    imported = cq.importers.importStep(str(path))
    solids = imported.solids().size()
    if solids < minimum_solids:
        raise RuntimeError(f"STEP round-trip has {solids} solids; expected at least {minimum_solids}")
    bounds = imported.val().BoundingBox()
    return {
        "bytes": path.stat().st_size,
        "solids": solids,
        "bounds_mm": {
            "x": [bounds.xmin, bounds.xmax],
            "y": [bounds.ymin, bounds.ymax],
            "z": [bounds.zmin, bounds.zmax],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-renders", action="store_true", help="export and verify STEP without PNG rendering"
    )
    parser.add_argument("--fetch", action="store_true", help="fetch pinned CAD before generation")
    args = parser.parse_args()
    if args.fetch:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_reference_cad.py")], check=True)
    cq = require_cadquery()
    notes = validate_selected_geometry()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    assembly, blade_bounds, _ = make_assembly(cq, False)
    assembly_with_clearance, _, _ = make_assembly(cq, True)
    # Flatten the hierarchy into ordinary multi-solid compounds. Several
    # lightweight CAD viewers display CadQuery's hierarchical STEP assembly as
    # empty even though OCCT can reopen it; the compound representation is
    # broadly interoperable and preserves the same exact B-Reps and transforms.
    cq.exporters.export(
        assembly.toCompound(), str(FULL_ASSEMBLY), exportType=cq.exporters.ExportTypes.STEP
    )
    cq.exporters.export(
        assembly_with_clearance.toCompound(),
        str(FULL_ASSEMBLY_WITH_BLADERUNNER),
        exportType=cq.exporters.ExportTypes.STEP,
    )

    render_parts = _render_parts(pcb_pad_positions())
    lightweight_shapes = [make_box(cq, box) for _name, box, _color in render_parts]
    cq.exporters.export(
        cq.Compound.makeCompound(lightweight_shapes),
        str(LIGHTWEIGHT_ASSEMBLY),
        exportType=cq.exporters.ExportTypes.STEP,
    )

    blade_solids = cq.importers.importStep(str(COMPUTE_BLADE_STEP)).solids().size()
    verification = {
        FULL_ASSEMBLY.name: verify_step(cq, FULL_ASSEMBLY, blade_solids + 10),
        FULL_ASSEMBLY_WITH_BLADERUNNER.name: verify_step(
            cq, FULL_ASSEMBLY_WITH_BLADERUNNER, blade_solids + 14
        ),
        LIGHTWEIGHT_ASSEMBLY.name: verify_step(cq, LIGHTWEIGHT_ASSEMBLY, 25),
    }
    actual_bounds = verification[FULL_ASSEMBLY.name]["bounds_mm"]
    z_depth = actual_bounds["z"][1] - actual_bounds["z"][0]
    if z_depth > MAX_ASSEMBLED_Z_DEPTH_MM:
        raise RuntimeError(
            f"full assembly Z depth {z_depth:.3f} mm exceeds regression limit "
            f"{MAX_ASSEMBLED_Z_DEPTH_MM:.3f} mm"
        )
    if not args.skip_renders:
        render_metrics = render_all(render_parts)
    else:
        render_metrics = {}

    xmin, xmax, ymin, ymax = board_bounds()
    manifest = {
        "cadquery_version": cq.__version__,
        "geometry_state": {
            "compute_blade_j3_anchor_mm": COMPUTE_BLADE_STEP_J3_ANCHOR_MM,
            "dda_minimum_acceptable_insertion_mm": DDA_MIN_ACCEPTABLE_INSERTION_MM,
            "j1_adapter_pcb_underside_z_mm": ADAPTER_Z_ABOVE_BLADE_MM,
            "j2_mating_post_length_mm": J2_MATING_POST_LENGTH_MM,
            "selected_dda_rotation_180": DDA_ROTATION_180,
            "dda_assembly_basis": DDA_ASSEMBLY_BASIS,
            "derived_axis_vectors": assembly_axis_vectors(),
            "j2_mating_direction": J2_MATING_DIRECTION,
            "full_assembly_total_z_depth_mm": z_depth,
            "adapter_board_bounds_relative_j1_mm": [xmin, xmax, ymin, ymax],
            "dda_boxes_relative_j1_mm": [asdict(box) for box in dda_boxes(False)],
        },
        "parts": {
            "compute_blade": "exact pinned official upstream STEP, re-exported by OCCT",
            "adapter_pcb": "actual generated KiCad Edge.Cuts rectangle, connector holes, 0.8 mm thickness",
            "j1": "dimension-driven SLW approximation; exact configured manufacturer STEP unavailable",
            "j2": "dimension-driven TSW approximation; exact configured manufacturer STEP unavailable",
            "dda": "confirmed-orientation simplified measured model",
            "bladerunner": (
                "validated J3-relative clearance frame only; official STL has no shared assembled datum, "
                "so no unvalidated chassis transform is shown"
            ),
        },
        "verification": verification,
        "renders": ([] if args.skip_renders else list(RENDERS)),
        "render_content_metrics": render_metrics,
        "validation_notes": notes,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Generated {FULL_ASSEMBLY.relative_to(ROOT)}")
    print(f"Generated {FULL_ASSEMBLY_WITH_BLADERUNNER.relative_to(ROOT)}")
    print(f"Generated {LIGHTWEIGHT_ASSEMBLY.relative_to(ROOT)}")
    if not args.skip_renders:
        print(f"Generated {len(RENDERS)} fixed-view PNG renders")
    print("Assembly round-trip verification passed and matches selected geometry validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
