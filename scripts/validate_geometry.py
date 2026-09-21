#!/usr/bin/env python3
"""Validate the assembled adapter with conservative, documented envelopes."""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

from design_config import (
    BLADERUNNER_CLEARANCE_Y,
    BLADERUNNER_CLEARANCE_Z,
    BLADE_PCB_ENVELOPE,
    NEARBY_BLADE_COMPONENT_KEEP_OUTS,
    DDA,
    DDA_ROTATION_180,
    J1_ORIGIN_MM,
    J2_FOOTPRINT,
    J2_FOOTPRINT_ROTATION_DEG,
    J2_MATING_FACE_LOCAL_X_MM,
)
from fetch_reference_cad import REFERENCES, REFERENCE_DIR, UPSTREAM_COMMIT, digest
from mechanical_geometry import Box, adapter_box, connector_boxes, dda_boxes, relative_j2
from verify_connectivity import child, children, parse_sexpr, properties


ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "pcb" / "compute-blade-dda-adapter.kicad_pcb"
HALF_BODY_EXPECTED_SIZE = (224.1209, 297.1934, 46.5000)


def stl_bounds(path: Path) -> tuple[tuple[float, float, float], tuple[float, float, float], int]:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"{path.name} is too short to be a binary STL")
    count = struct.unpack_from("<I", data, 80)[0]
    if 84 + count * 50 != len(data):
        raise ValueError(f"{path.name} is not the expected binary STL encoding")
    minima = [float("inf")] * 3
    maxima = [float("-inf")] * 3
    for index in range(count):
        values = struct.unpack_from("<12fH", data, 84 + index * 50)
        for start in range(3, 12, 3):
            for axis in range(3):
                value = values[start + axis]
                minima[axis] = min(minima[axis], value)
                maxima[axis] = max(maxima[axis], value)
    return tuple(minima), tuple(maxima), count


def board_bounds() -> tuple[float, float, float, float]:
    tree = parse_sexpr(PCB.read_text(encoding="utf-8"))
    rectangles = [
        node for node in children(tree, "gr_rect")
        if child(node, "layer") and child(node, "layer")[1] == "Edge.Cuts"
    ]
    if len(rectangles) != 1:
        raise ValueError("expected exactly one rectangular Edge.Cuts outline")
    start = child(rectangles[0], "start")
    end = child(rectangles[0], "end")
    assert start and end
    xs = (float(start[1]) - J1_ORIGIN_MM[0], float(end[1]) - J1_ORIGIN_MM[0])
    ys = (float(start[2]) - J1_ORIGIN_MM[1], float(end[2]) - J1_ORIGIN_MM[1])
    return min(xs), max(xs), min(ys), max(ys)


def validate_footprint() -> list[str]:
    tree = parse_sexpr(PCB.read_text(encoding="utf-8"))
    j2 = next(
        (node for node in children(tree, "footprint") if properties(node).get("Reference") == "J2"),
        None,
    )
    if j2 is None:
        return ["PCB has no J2 footprint"]
    errors = []
    if len(j2) < 2 or j2[1] != J2_FOOTPRINT:
        errors.append(f"J2 must use {J2_FOOTPRINT}, found {j2[1] if len(j2) > 1 else '<missing>'}")
    at = child(j2, "at")
    angle = float(at[3]) if at and len(at) > 3 else 0.0
    if angle % 360 != J2_FOOTPRINT_ROTATION_DEG % 360:
        errors.append(
            f"J2 rotation must be {J2_FOOTPRINT_ROTATION_DEG:g} degrees so its mating axis is +X; found {angle:g}"
        )
    return errors


def check_references() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    for reference in REFERENCES:
        path = REFERENCE_DIR / reference.name
        if not path.exists():
            errors.append(f"missing reference CAD: {path.relative_to(ROOT)}")
            continue
        if digest(path) != reference.sha256:
            errors.append(f"reference CAD hash mismatch: {reference.name}")
    step = REFERENCE_DIR / "compute_blade_dev.step"
    if step.exists():
        text = step.read_text(encoding="utf-8", errors="ignore")
        if "SI_UNIT(.MILLI.,.METRE.)" not in text:
            errors.append("Compute Blade STEP does not declare millimetre length units")
        if not re.search(r"PRODUCT\('J3'", text):
            errors.append("Compute Blade STEP lacks the expected J3 assembly product")
        notes.append(f"Compute Blade STEP: {step.stat().st_size} bytes; J3 product authenticated")

    half = REFERENCE_DIR / "bladerunner_19in_half_body.stl"
    if half.exists():
        minima, maxima, triangles = stl_bounds(half)
        size = tuple(maxima[i] - minima[i] for i in range(3))
        if any(abs(size[i] - HALF_BODY_EXPECTED_SIZE[i]) > 0.01 for i in range(3)):
            errors.append(f"unexpected BladeRunner half-body bounds: {size}")
        notes.append(
            "BladeRunner half body: "
            + " x ".join(f"{value:.2f}" for value in size)
            + f" mm; {triangles} triangles"
        )
    return errors, notes


def variant_checks(rotation_180: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    boxes = dda_boxes(rotation_180)
    blade = Box("compute_blade_pcb", *BLADE_PCB_ENVELOPE)
    for box in boxes:
        if box.overlaps(blade):
            errors.append(f"{box.name} intersects the conservative Compute Blade PCB envelope")

    component_keepouts = [
        Box(f"nearby_blade_component_{index}", *bounds)
        for index, bounds in enumerate(NEARBY_BLADE_COMPONENT_KEEP_OUTS, start=1)
    ]
    for box in boxes:
        for keepout in component_keepouts:
            if box.overlaps(keepout):
                errors.append(f"{box.name} intersects {keepout.name}")

    for box in boxes:
        if box.ymin < BLADERUNNER_CLEARANCE_Y[0] or box.ymax > BLADERUNNER_CLEARANCE_Y[1]:
            errors.append(f"{box.name} exceeds the conservative BladeRunner Y clearance")
        if box.zmin < BLADERUNNER_CLEARANCE_Z[0] or box.zmax > BLADERUNNER_CLEARANCE_Z[1]:
            errors.append(f"{box.name} exceeds the conservative BladeRunner Z clearance")

    j2_x, _ = relative_j2()
    if min(box.xmin for box in boxes) <= j2_x:
        errors.append("DDA does not extend to the intended +X/right side of J2")

    socket = next(box for box in boxes if box.name == "dda_socket")
    pcb = next(box for box in boxes if box.name == "dda_pcb")
    expected_face = j2_x + J2_MATING_FACE_LOCAL_X_MM
    if abs(socket.xmin - expected_face) > 1e-6:
        errors.append("DDA socket mating face does not coincide with the J2 mating plane")
    if abs(pcb.xmin - expected_face - DDA.pcb_surface_to_mating_plane) > 1e-6:
        errors.append("DDA PCB-to-socket mating-plane offset is not 8.3 mm")

    bounds = (
        min(box.xmin for box in boxes), max(box.xmax for box in boxes),
        min(box.ymin for box in boxes), max(box.ymax for box in boxes),
        min(box.zmin for box in boxes), max(box.zmax for box in boxes),
    )
    notes.append(
        f"DDA {'rot180' if rotation_180 else 'default'} envelope: "
        f"X {bounds[0]:.2f}..{bounds[1]:.2f}, Y {bounds[2]:.2f}..{bounds[3]:.2f}, "
        f"Z {bounds[4]:.2f}..{bounds[5]:.2f} mm"
    )
    return errors, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dda-rotation-180", choices=("false", "true"), default=str(DDA_ROTATION_180).lower()
    )
    parser.add_argument("--compare-variants", action="store_true")
    args = parser.parse_args()
    selected = args.dda_rotation_180 == "true"

    errors, notes = check_references()
    errors.extend(validate_footprint())
    try:
        adapter = adapter_box(board_bounds())
        notes.append(f"Adapter PCB envelope: {adapter}")
        for box in [adapter, *connector_boxes()]:
            if box.ymin < BLADERUNNER_CLEARANCE_Y[0] or box.ymax > BLADERUNNER_CLEARANCE_Y[1]:
                errors.append(f"{box.name} exceeds the conservative BladeRunner Y clearance")
            if box.zmin < BLADERUNNER_CLEARANCE_Z[0] or box.zmax > BLADERUNNER_CLEARANCE_Z[1]:
                errors.append(f"{box.name} exceeds the conservative BladeRunner Z clearance")
    except (ValueError, AssertionError) as exc:
        errors.append(str(exc))

    selected_errors, selected_notes = variant_checks(selected)
    errors.extend(selected_errors)
    notes.extend(selected_notes)

    print("Mechanical geometry validation")
    print(f"Pinned Compute Blade commit: {UPSTREAM_COMMIT}")
    print(f"Selected dda_rotation_180={str(selected).lower()}")
    for note in notes:
        print(f"  {note}")

    if args.compare_variants:
        alternate_errors, alternate_notes = variant_checks(not selected)
        for note in alternate_notes:
            print(f"  comparison: {note}")
        status = "PASS" if not alternate_errors else "FAIL (not selected)"
        print(f"  alternate orientation: {status}")
        for error in alternate_errors:
            print(f"    - {error}")

    if errors:
        print("Geometry validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Geometry validation PASSED for the selected orientation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
