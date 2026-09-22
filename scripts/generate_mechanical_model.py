#!/usr/bin/env python3
"""Generate deterministic simplified parallel-DDA solids and diagrams."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_PER_BLADE_DESIGN_MAX_MM,
    BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM,
    BOARD_BOUNDS_RELATIVE_J1_MM,
    BOARD_THICKNESS_MM,
    DDA_ASSEMBLY_BASIS,
    DDA_GNSS_TOP_Z_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    J1_CANDIDATE_PART,
    J1_INSERTION_DEPTH_MIN_MM,
    J2_CANDIDATE_PART,
    J2_DDA_SOCKET_MATING_FACE_Z_MM,
    J2_LOWER_TIP_Z_MM,
    J2_MATING_POST_LENGTH_MM,
)
from mechanical_geometry import Box, adapter_box, assembly_axis_vectors, connector_boxes, dda_boxes


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "mechanical" / "generated"


def triangles(box: Box):
    x0, x1, y0, y1, z0, z1 = box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax
    vertices = (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )
    for a, b, c in (
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ):
        yield vertices[a], vertices[b], vertices[c]


def write_binary_stl(path: Path, boxes: list[Box]) -> None:
    facets = [triangle for box in boxes for triangle in triangles(box)]
    with path.open("wb") as handle:
        handle.write(b"Parallel DDA collision envelope; millimetres".ljust(80, b" "))
        handle.write(struct.pack("<I", len(facets)))
        for triangle in facets:
            handle.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for vertex in triangle:
                handle.write(struct.pack("<3f", *vertex))
            handle.write(struct.pack("<H", 0))


def write_side_svg(path: Path, boxes: list[Box]) -> None:
    colors = {
        "adapter_pcb": "#7d55ac",
        "dda_pcb": "#23713b",
        "dda_socket": "#222222",
        "dda_gnss_envelope": "#568dcc",
        "dda_battery_rtc_inward_envelope": "#d29436",
        "compute_blade_header_plastic": "#202020",
        "compute_blade_header_exposed_posts": "#c7a338",
        "j1_hle_body": "#444444",
        "j2_mtlw_reverse_insulator": "#202020",
        "j2_upper_dda_mating_posts": "#c7a338",
        "j2_lower_posts": "#b8932e",
    }
    scale = 20.0
    width, height = 70.0, 24.0
    y0, z0 = -4.0, -0.5
    shapes = []
    for box in [adapter_box(BOARD_BOUNDS_RELATIVE_J1_MM), *connector_boxes(), *boxes]:
        x = (box.ymin - y0) * scale
        y = (height - (box.zmax - z0)) * scale
        w = max(1.0, (box.ymax - box.ymin) * scale)
        h = max(1.0, (box.zmax - box.zmin) * scale)
        shapes.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{colors[box.name]}" fill-opacity="0.65" stroke="#111"/>'
        )
    limit_y = (height - (BLADERUNNER_PER_BLADE_DESIGN_MAX_MM - z0)) * scale
    physical_y = (height - (BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - z0)) * scale
    path.write_text(
        f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width*scale:.0f}" height="{height*scale:.0f}" viewBox="0 0 {width*scale:.0f} {height*scale:.0f}">
<rect width="100%" height="100%" fill="white"/>
<text x="14" y="22" font-family="sans-serif" font-size="14">Parallel DDA — Y/Z section (+Z outward)</text>
<line x1="0" y1="{limit_y:.1f}" x2="{width*scale:.1f}" y2="{limit_y:.1f}" stroke="#cc7a00" stroke-width="2" stroke-dasharray="7 4"/>
<line x1="0" y1="{physical_y:.1f}" x2="{width*scale:.1f}" y2="{physical_y:.1f}" stroke="#bb2020" stroke-width="2" stroke-dasharray="7 4"/>
{''.join(shapes)}
</svg>\n''',
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    boxes = dda_boxes(False)
    write_binary_stl(OUTPUT / "dda_simple_default.stl", boxes)
    write_side_svg(OUTPUT / "assembly_side_parallel.svg", boxes)
    manifest = {
        "architecture": "parallel DDA, GNSS outward +Z",
        "j1": J1_CANDIDATE_PART,
        "j2": J2_CANDIDATE_PART,
        "adapter_underside_mm": ADAPTER_Z_ABOVE_BLADE_MM,
        "adapter_thickness_mm": BOARD_THICKNESS_MM,
        "j1_required_bottom_entry_reach_mm": J1_INSERTION_DEPTH_MIN_MM,
        "j2_reverse_mating_segment_mm": J2_MATING_POST_LENGTH_MM,
        "j2_lower_tip_z_mm": J2_LOWER_TIP_Z_MM,
        "dda_insertion_mm": DDA_MIN_ACCEPTABLE_INSERTION_MM,
        "dda_mating_face_z_mm": J2_DDA_SOCKET_MATING_FACE_Z_MM,
        "outward_stack_mm": DDA_GNSS_TOP_Z_MM,
        "physical_clearance_mm": BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - DDA_GNSS_TOP_Z_MM,
        "design_reserve_remaining_mm": BLADERUNNER_PER_BLADE_DESIGN_MAX_MM - DDA_GNSS_TOP_Z_MM,
        "dda_assembly_basis": DDA_ASSEMBLY_BASIS,
        "derived_axis_vectors": assembly_axis_vectors(),
        "boxes_relative_to_j3_mm": [box.__dict__ for box in boxes],
    }
    (OUTPUT / "dda_model_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("Generated approved parallel DDA model and section view")


if __name__ == "__main__":
    main()
