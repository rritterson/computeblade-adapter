#!/usr/bin/env python3
"""Generate STEP assemblies and fixed renders from the validated shared geometry."""

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
    BLADERUNNER_PER_BLADE_DESIGN_MAX_MM,
    BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM,
    BOARD_THICKNESS_MM,
    COMPUTE_BLADE_PCB_BOUNDS_MM,
    COMPUTE_BLADE_STEP_J3_ANCHOR_MM,
    DDA_ASSEMBLY_BASIS,
    DDA_GNSS_TOP_Z_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    J1_CANDIDATE_PART,
    J1_ORIGIN_MM,
    J1_SOCKET_BODY_HEIGHT_MM,
    J2_BODY_HEIGHT_MM,
    J2_BODY_PLAN_MM,
    J2_CANDIDATE_PART,
    J2_LOWER_POST_LENGTH_MM,
    J2_MATING_POST_LENGTH_MM,
)
from fetch_reference_cad import REFERENCE_DIR
from mechanical_geometry import Box, assembly_axis_vectors, connector_boxes, dda_boxes
from validate_geometry import (
    PCB,
    board_bounds,
    check_references,
    geometry_checks,
    validate_connector_constraints,
    validate_footprint,
)
from verify_connectivity import children, parse_sexpr, properties, transformed_pad


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "mechanical" / "generated"
COMPUTE_BLADE_STEP = REFERENCE_DIR / "compute_blade_dev.step"
FULL_ASSEMBLY = OUTPUT / "full_assembly.step"
FULL_ASSEMBLY_WITH_BLADERUNNER = OUTPUT / "full_assembly_with_bladerunner.step"
LIGHTWEIGHT_ASSEMBLY = OUTPUT / "full_assembly_lightweight.step"
J1_STEP = OUTPUT / "j1_hle_105_02_l_dv_pe_be.step"
J2_STEP = OUTPUT / "j2_mtlw_106_06_g_d_035_reverse.step"
MANIFEST = OUTPUT / "full_assembly_manifest.json"

RENDERS = {
    "render_top.png": ((0, 0, 320), (0, 0, 8), (0, 1, 0), 145),
    "render_side.png": ((0, 250, 35), (0, 0, 8), (0, 0, 1), 145),
    "render_end.png": ((280, 0, 35), (0, 0, 8), (0, 0, 1), 55),
    "render_iso.png": ((260, 220, 180), (0, 0, 7), (0, 0, 1), 145),
    "render_j1_closeup.png": ((-35, -35, 32), (0, 4, 4), (0, 0, 1), 16),
    "render_j2_closeup.png": ((75, 55, 48), (35, 7, 8), (0, 0, 1), 24),
    "assembly_top.png": ((0, 0, 320), (0, 0, 8), (0, 1, 0), 145),
    "assembly_x_view.png": ((280, 0, 35), (0, 0, 8), (0, 0, 1), 55),
    "assembly_y_view.png": ((0, 250, 35), (0, 0, 8), (0, 0, 1), 145),
    "assembly_iso.png": ((260, 220, 180), (0, 0, 7), (0, 0, 1), 145),
}


def require_cadquery() -> Any:
    try:
        import cadquery as cq
    except ImportError as exc:
        raise RuntimeError("install the pinned requirements-assembly.txt toolchain") from exc
    if cq.__version__ != "2.5.2":
        raise RuntimeError(f"expected CadQuery 2.5.2, found {cq.__version__}")
    return cq


def validate_selected_geometry() -> list[str]:
    errors, notes = check_references()
    errors.extend(validate_footprint())
    connector_errors, connector_notes = validate_connector_constraints()
    model_errors, model_notes = geometry_checks()
    errors.extend(connector_errors + model_errors)
    notes.extend(connector_notes + model_notes)
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
        box.xmax - box.xmin, box.ymax - box.ymin, box.zmax - box.zmin,
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
    expected = {*(f"J1.{pin}" for pin in range(1, 11)), *(f"J2.{pin}" for pin in range(1, 13))}
    if set(result) != expected:
        raise RuntimeError("could not resolve all connector pads from generated PCB")
    return result


def actual_adapter_board(cq: Any, pads: dict[str, tuple[float, float]]) -> Any:
    xmin, xmax, ymin, ymax = board_bounds()
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    board = cq.Solid.makeBox(
        xmax - xmin, ymax - ymin, BOARD_THICKNESS_MM,
        cq.Vector(ax + xmin, ay + ymin, az + ADAPTER_Z_ABOVE_BLADE_MM),
    )
    for x, y in pads.values():
        hole = cq.Solid.makeCylinder(
            0.50, BOARD_THICKNESS_MM + 0.2,
            cq.Vector(ax + x, ay + y, az + ADAPTER_Z_ABOVE_BLADE_MM - 0.1),
            cq.Vector(0, 0, 1),
        )
        board = board.cut(hole)
    return board


def connector_shapes(cq: Any) -> list[tuple[str, Any, Any]]:
    colors = {"plastic": cq.Color(0.08, 0.08, 0.09), "metal": cq.Color(0.78, 0.62, 0.18)}
    parts = []
    for box in connector_boxes():
        color = colors["metal"] if "post" in box.name else colors["plastic"]
        parts.append((box.name, make_box(cq, globalize(box)), color))
    return parts


def dda_shapes(cq: Any) -> list[tuple[str, Any, Any]]:
    colors = {
        "dda_pcb": cq.Color(0.06, 0.42, 0.16),
        "dda_socket": cq.Color(0.07, 0.07, 0.08),
        "dda_gnss_envelope": cq.Color(0.25, 0.52, 0.82, 0.55),
        "dda_battery_rtc_inward_envelope": cq.Color(0.85, 0.56, 0.16, 0.55),
    }
    return [(box.name, make_box(cq, globalize(box)), colors[box.name]) for box in dda_boxes()]


def export_connector_models(cq: Any) -> None:
    j1_body = cq.Solid.makeBox(5.08, 12.70, J1_SOCKET_BODY_HEIGHT_MM, cq.Vector(-3.81, -1.27, 0))
    j1_pins = [
        cq.Solid.makeCylinder(0.25, J1_SOCKET_BODY_HEIGHT_MM, cq.Vector(x, y, 0), cq.Vector(0, 0, 1))
        for y in (0, 2.54, 5.08, 7.62, 10.16) for x in (0, -2.54)
    ]
    cq.exporters.export(cq.Compound.makeCompound([j1_body, *j1_pins]), str(J1_STEP), exportType=cq.exporters.ExportTypes.STEP)

    length, width = J2_BODY_PLAN_MM
    j2_body = cq.Solid.makeBox(width, length, J2_BODY_HEIGHT_MM, cq.Vector(-1.245, -1.27, -J2_BODY_HEIGHT_MM))
    j2_pins = []
    for y in (0, 2.54, 5.08, 7.62, 10.16, 12.70):
        for x in (0, 2.54):
            j2_pins.append(
                cq.Solid.makeBox(0.635, 0.635, J2_LOWER_POST_LENGTH_MM + J2_MATING_POST_LENGTH_MM,
                    cq.Vector(x - 0.3175, y - 0.3175, -J2_LOWER_POST_LENGTH_MM))
            )
    cq.exporters.export(cq.Compound.makeCompound([j2_body, *j2_pins]), str(J2_STEP), exportType=cq.exporters.ExportTypes.STEP)


def clearance_planes(cq: Any, blade_bounds: Any) -> list[tuple[str, Any, Any]]:
    x0, x1 = blade_bounds.xmin, blade_bounds.xmax
    y0, y1 = COMPUTE_BLADE_PCB_BOUNDS_MM[2], COMPUTE_BLADE_PCB_BOUNDS_MM[3]
    parts = []
    for name, z, color in (
        ("BladeRunner_1mm_design_plane", BLADERUNNER_PER_BLADE_DESIGN_MAX_MM, cq.Color(0.95, 0.55, 0.05, 0.3)),
        ("BladeRunner_physical_clearance_plane", BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM, cq.Color(0.85, 0.12, 0.12, 0.25)),
    ):
        box = Box(name, x0, x1, y0, y1, z, z + 0.08)
        parts.append((name, make_box(cq, box), color))
    return parts


def exact_collision_check(cq: Any, blade_shape: Any, adapter: Any) -> dict[str, float]:
    """Require no overlap with official blade CAD outside the intended J1 mating region."""
    volumes: dict[str, float] = {}
    for box in dda_boxes():
        volume = blade_shape.intersect(make_box(cq, globalize(box))).Volume()
        volumes[box.name] = volume
        if volume > 0.01:
            raise RuntimeError(f"official Compute Blade collision: {box.name} overlap {volume:.4f} mm^3")
    for box in connector_boxes():
        if box.name.startswith("j2_"):
            volume = blade_shape.intersect(make_box(cq, globalize(box))).Volume()
            volumes[box.name] = volume
            if volume > 0.01:
                raise RuntimeError(f"official Compute Blade collision: {box.name} overlap {volume:.4f} mm^3")
    # Remove the local J1/header mating volume before testing the interposer.
    ax, ay, _ = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    intentional = cq.Solid.makeBox(8.0, 16.0, 12.0, cq.Vector(ax - 5.0, ay - 2.0, 0.0))
    adapter_test = adapter.cut(intentional)
    volumes["adapter_outside_J1_mating_region"] = blade_shape.intersect(adapter_test).Volume()
    if volumes["adapter_outside_J1_mating_region"] > 0.01:
        raise RuntimeError(
            "official Compute Blade collision: adapter outside J1 region overlap "
            f"{volumes['adapter_outside_J1_mating_region']:.4f} mm^3"
        )
    return volumes


def make_assembly(cq: Any, include_clearance: bool) -> tuple[Any, Any, list[str], dict[str, float]]:
    blade = cq.importers.importStep(str(COMPUTE_BLADE_STEP)).val()
    blade_bounds = blade.BoundingBox()
    pads = pcb_pad_positions()
    adapter = actual_adapter_board(cq, pads)
    collisions = exact_collision_check(cq, blade, adapter)
    parts: list[tuple[str, Any, Any]] = [
        ("Compute_Blade_DEV_official_STEP", blade, cq.Color(0.55, 0.57, 0.60)),
        ("Adapter_PCB_actual_outline_0p6mm", adapter, cq.Color(0.10, 0.50, 0.22)),
        *connector_shapes(cq),
        *dda_shapes(cq),
    ]
    if include_clearance:
        parts.extend(clearance_planes(cq, blade_bounds))
    assembly = cq.Assembly(name="parallel_dda_assembly")
    for name, shape, color in parts:
        assembly.add(shape, name=name, color=color)
    return assembly, blade_bounds, [name for name, _, _ in parts], collisions


def render_parts() -> list[tuple[str, Box, tuple[int, int, int]]]:
    colors = {
        "blade": (78, 102, 126), "adapter": (34, 145, 76), "plastic": (35, 35, 38),
        "metal": (196, 153, 45), "pcb": (22, 116, 54), "gnss": (70, 130, 200), "battery": (210, 140, 40),
    }
    xmin, xmax, ymin, ymax = board_bounds()
    parts = [
        ("Compute Blade PCB", Box("blade", *COMPUTE_BLADE_PCB_BOUNDS_MM), colors["blade"]),
        ("Adapter PCB", globalize(Box("adapter", xmin, xmax, ymin, ymax, ADAPTER_Z_ABOVE_BLADE_MM, ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM)), colors["adapter"]),
    ]
    for box in connector_boxes():
        parts.append((box.name, globalize(box), colors["metal"] if "post" in box.name else colors["plastic"]))
    for box in dda_boxes():
        key = {"dda_pcb": "pcb", "dda_socket": "plastic", "dda_gnss_envelope": "gnss", "dda_battery_rtc_inward_envelope": "battery"}[box.name]
        parts.append((box.name, globalize(box), colors[key]))
    return parts


def _unit(v):
    length = sqrt(sum(value * value for value in v))
    return tuple(value / length for value in v)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _dot(a, b):
    return sum(a[i]*b[i] for i in range(3))


def _faces(box: Box):
    x0, x1, y0, y1, z0, z1 = box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax
    return [
        ((-1,0,0),[(x0,y0,z0),(x0,y0,z1),(x0,y1,z1),(x0,y1,z0)]),
        ((1,0,0),[(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)]),
        ((0,-1,0),[(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)]),
        ((0,1,0),[(x0,y1,z0),(x0,y1,z1),(x1,y1,z1),(x1,y1,z0)]),
        ((0,0,-1),[(x0,y0,z0),(x0,y1,z0),(x1,y1,z0),(x1,y0,z0)]),
        ((0,0,1),[(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]),
    ]


def render_all(parts: list[tuple[str, Box, tuple[int, int, int]]]) -> dict[str, dict[str, int]]:
    from PIL import Image, ImageDraw, ImageFont
    width, height = 1200, 900
    background = (245, 245, 245)
    ax, ay, az = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    metrics = {}
    for filename, (offset, focus_offset, up, scale) in RENDERS.items():
        position = (ax + offset[0], ay + offset[1], az + offset[2])
        focus = (ax + focus_offset[0], ay + focus_offset[1], az + focus_offset[2])
        direction = _unit(tuple(focus[i] - position[i] for i in range(3)))
        right = _unit(_cross(direction, up))
        screen_up = _unit(_cross(right, direction))
        ppm = height / (2.0 * scale)
        faces = []
        for name, box, base in parts:
            for normal, vertices in _faces(box):
                center = tuple(sum(v[i] for v in vertices)/4 for i in range(3))
                depth = _dot(tuple(center[i]-position[i] for i in range(3)), direction)
                shade = 0.62 + 0.32 * abs(_dot(normal, direction))
                color = tuple(round(c*shade) for c in base)
                polygon = []
                for vertex in vertices:
                    relative = tuple(vertex[i]-focus[i] for i in range(3))
                    polygon.append((width/2 + _dot(relative,right)*ppm, height/2 - _dot(relative,screen_up)*ppm))
                faces.append((depth, polygon, color))
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        for _depth, polygon, color in sorted(faces, key=lambda item: item[0], reverse=True):
            draw.polygon(polygon, fill=color, outline=(25,25,28))
        # Explicit neighboring-blade design plane annotation.
        draw.rectangle((0,0,width,34), fill=(255,255,255))
        draw.text((12,10), filename.replace(".png", "").upper() + " — parallel DDA, GNSS +Z", fill=(15,15,18), font=ImageFont.load_default())
        path = OUTPUT / filename
        image.save(path, format="PNG", optimize=True)
        foreground = sum(pixel != background for pixel in image.crop((0,35,width,height)).getdata())
        colors = len(image.getcolors(maxcolors=1_000_000) or [])
        if foreground < width*(height-35)*0.01 or colors < 8:
            raise RuntimeError(f"blank or near-uniform render: {filename}")
        metrics[filename] = {"foreground_pixels": foreground, "unique_colors": colors}
    return metrics


def verify_step(cq: Any, path: Path, minimum_solids: int) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size < 10_000:
        raise RuntimeError(f"STEP export failed: {path}")
    imported = cq.importers.importStep(str(path))
    solids = imported.solids().size()
    if solids < minimum_solids:
        raise RuntimeError(f"{path.name}: {solids} solids; expected at least {minimum_solids}")
    bounds = imported.val().BoundingBox()
    return {"bytes": path.stat().st_size, "solids": solids, "bounds_mm": {"x":[bounds.xmin,bounds.xmax], "y":[bounds.ymin,bounds.ymax], "z":[bounds.zmin,bounds.zmax]}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-renders", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.fetch:
        subprocess.run([sys.executable, str(ROOT / "scripts/fetch_reference_cad.py")], check=True)
    cq = require_cadquery()
    notes = validate_selected_geometry()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    export_connector_models(cq)
    assembly, _, _, collisions = make_assembly(cq, False)
    with_clearance, _, _, _ = make_assembly(cq, True)
    cq.exporters.export(assembly.toCompound(), str(FULL_ASSEMBLY), exportType=cq.exporters.ExportTypes.STEP)
    cq.exporters.export(with_clearance.toCompound(), str(FULL_ASSEMBLY_WITH_BLADERUNNER), exportType=cq.exporters.ExportTypes.STEP)
    lightweight = cq.Compound.makeCompound([make_box(cq, box) for _name, box, _color in render_parts()])
    cq.exporters.export(lightweight, str(LIGHTWEIGHT_ASSEMBLY), exportType=cq.exporters.ExportTypes.STEP)
    blade_solids = cq.importers.importStep(str(COMPUTE_BLADE_STEP)).solids().size()
    verification = {
        FULL_ASSEMBLY.name: verify_step(cq, FULL_ASSEMBLY, blade_solids + 8),
        FULL_ASSEMBLY_WITH_BLADERUNNER.name: verify_step(cq, FULL_ASSEMBLY_WITH_BLADERUNNER, blade_solids + 10),
        LIGHTWEIGHT_ASSEMBLY.name: verify_step(cq, LIGHTWEIGHT_ASSEMBLY, 10),
        J1_STEP.name: verify_step(cq, J1_STEP, 2),
        J2_STEP.name: verify_step(cq, J2_STEP, 2),
    }
    renders = {} if args.skip_renders else render_all(render_parts())
    manifest = {
        "cadquery_version": cq.__version__,
        "architecture": "parallel DDA; GNSS outward +Z; socket/battery inward -Z",
        "j1": {"part": J1_CANDIDATE_PART, "model": "manufacturer-dimensioned approximation"},
        "j2": {"part": J2_CANDIDATE_PART, "model": "manufacturer-dimensioned reverse-mount approximation"},
        "geometry_state": {
            "dda_assembly_basis": DDA_ASSEMBLY_BASIS,
            "derived_axis_vectors": assembly_axis_vectors(),
            "dda_insertion_mm": DDA_MIN_ACCEPTABLE_INSERTION_MM,
            "outward_stack_mm": DDA_GNSS_TOP_Z_MM,
            "physical_clearance_mm": BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - DDA_GNSS_TOP_Z_MM,
            "design_reserve_remaining_mm": BLADERUNNER_PER_BLADE_DESIGN_MAX_MM - DDA_GNSS_TOP_Z_MM,
            "dda_boxes_relative_j3_mm": [asdict(box) for box in dda_boxes()],
        },
        "official_compute_blade_collision_volumes_mm3": collisions,
        "verification": verification,
        "renders": renders,
        "validation_notes": notes,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Generated and round-trip verified parallel-DDA STEP assemblies and connector models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
