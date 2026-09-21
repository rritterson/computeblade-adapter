#!/usr/bin/env python3
"""Generate deterministic simplified DDA solids and assembly diagrams."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_CLEARANCE_Z,
    COMPUTE_BLADE_EXPOSED_POST_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    DDA_PIN1_TOP_SIDE_POSITION,
    DDA_PIN1_UNDERSIDE_POSITION,
    DDA_ROTATION_180,
    J1_INSERTION_DEPTH_MIN_MM,
    J1_NOMINAL_STACK_HEIGHT_MM,
    J1_SEATING_GAP_MM,
    J2_MATING_POST_LENGTH_MM,
    J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
)
from mechanical_geometry import Box, adapter_box, connector_boxes, dda_boxes


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "mechanical" / "generated"


def triangles(box: Box):
    x0, x1, y0, y1, z0, z1 = box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax
    v = (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )
    for a, b, c in (
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ):
        yield v[a], v[b], v[c]


def write_binary_stl(path: Path, boxes: list[Box]) -> None:
    facets = [triangle for box in boxes for triangle in triangles(box)]
    header = b"Simplified DDA collision envelope; dimensions in mm".ljust(80, b" ")
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(facets)))
        for triangle in facets:
            handle.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for vertex in triangle:
                handle.write(struct.pack("<3f", *vertex))
            handle.write(struct.pack("<H", 0))


def write_svg(path: Path, boxes: list[Box], title: str) -> None:
    colors = {
        "dda_pcb": "#246b35",
        "dda_socket": "#222222",
        "dda_gnss_envelope": "#7aa6d8",
        "dda_battery_rtc_envelope": "#e8b866",
        "adapter_pcb": "#8d5fbd",
        "compute_blade_header_plastic": "#202020",
        "compute_blade_header_exposed_posts": "#c7a338",
        "j1_socket_body": "#555555",
        "j2_body_elbow_keepout": "#333333",
        "j2_mating_posts": "#c7a338",
        "compute_blade_local_envelope": "#4b75a5",
    }
    scale = 10
    x0, z0 = -32.0, -8.0
    width, height = 80.0, 56.0
    context = [
        Box("compute_blade_local_envelope", -30.0, 0.0, -45.0, 45.0, -1.6, 0.0),
        adapter_box((-4.6, 23.4, -2.05, 14.75)),
        *connector_boxes(),
    ]
    shapes = []
    clearance_y = (height - (BLADERUNNER_CLEARANCE_Z[1] - z0)) * scale
    clearance_h = (BLADERUNNER_CLEARANCE_Z[1] - BLADERUNNER_CLEARANCE_Z[0]) * scale
    shapes.append(
        f'<rect x="0" y="{clearance_y:.1f}" width="{width*scale:.1f}" height="{clearance_h:.1f}" '
        'fill="#d9efd9" fill-opacity="0.35" stroke="#4c9a4c" stroke-dasharray="7 4"/>'
    )
    for box in [*context, *boxes]:
        x = (box.xmin - x0) * scale
        y = (height - (box.zmax - z0)) * scale
        w = (box.xmax - box.xmin) * scale
        h = (box.zmax - box.zmin) * scale
        shapes.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{colors[box.name]}" fill-opacity="0.55" stroke="#111"/>'
        )
    path.write_text(
        f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width*scale:.0f}" height="{height*scale:.0f}" viewBox="0 0 {width*scale:.0f} {height*scale:.0f}">
<rect width="100%" height="100%" fill="white"/>
<text x="15" y="24" font-family="sans-serif" font-size="15">{title} — side view (+X right, +Z up)</text>
<line x1="0" y1="{(height+z0)*scale:.1f}" x2="{width*scale}" y2="{(height+z0)*scale:.1f}" stroke="#aa0000" stroke-dasharray="6 4"/>
{''.join(shapes)}
<text x="15" y="48" font-family="sans-serif" font-size="11">Green dashed: conservative BladeRunner Z clearance; blue: local Compute Blade; purple: adapter</text>
</svg>\n''',
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dda-rotation-180",
        choices=("false", "true"),
        default=str(DDA_ROTATION_180).lower(),
    )
    args = parser.parse_args()
    selected = args.dda_rotation_180 == "true"
    OUTPUT.mkdir(parents=True, exist_ok=True)

    manifest = {
        "assembly_parameters_mm": {
            "adapter_pcb_underside_above_blade": ADAPTER_Z_ABOVE_BLADE_MM,
            "compute_blade_exposed_post": COMPUTE_BLADE_EXPOSED_POST_MM,
            "compute_blade_header_pin_tip": COMPUTE_BLADE_HEADER_PIN_TIP_MM,
            "compute_blade_header_plastic_top": COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
            "j1_minimum_insertion": J1_INSERTION_DEPTH_MIN_MM,
            "j1_nominal_stack": J1_NOMINAL_STACK_HEIGHT_MM,
            "j1_seating_gap": J1_SEATING_GAP_MM,
            "dda_acceptable_remaining_exposed_post": DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM,
            "dda_min_acceptable_insertion": DDA_MIN_ACCEPTABLE_INSERTION_MM,
            "j2_mating_post": J2_MATING_POST_LENGTH_MM,
            "j2_post_margin_after_minimum_insertion": J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
        },
        "confirmed_dda_pin1": {
            "top_component_side": DDA_PIN1_TOP_SIDE_POSITION,
            "underside_hole_view": DDA_PIN1_UNDERSIDE_POSITION,
        },
        "selected_dda_rotation_180": selected,
        "variants": {},
    }
    for rotation in (False, True):
        name = "rot180" if rotation else "default"
        boxes = dda_boxes(rotation)
        write_binary_stl(OUTPUT / f"dda_simple_{name}.stl", boxes)
        write_svg(OUTPUT / f"assembly_side_{name}.svg", boxes, f"DDA {name}")
        manifest["variants"][name] = [box.__dict__ for box in boxes]
    (OUTPUT / "dda_model_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Generated both DDA orientation models; selected dda_rotation_180={selected}")


if __name__ == "__main__":
    main()
