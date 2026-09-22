#!/usr/bin/env python3
"""Validate the approved parallel-DDA stack against electrical/mechanical contracts."""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_PER_BLADE_DESIGN_MAX_MM,
    BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM,
    BLADERUNNER_Z_SAFETY_MARGIN_MM,
    BOARD_BOUNDS_RELATIVE_J1_MM,
    BOARD_THICKNESS_MM,
    COMPUTE_BLADE_EXPOSED_POST_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    COMPUTE_BLADE_PCB_BOUNDS_MM,
    COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM,
    COMPUTE_BLADE_STEP_BOUNDS_MM,
    COMPUTE_BLADE_STEP_J3_ANCHOR_MM,
    COMPUTE_BLADE_STEP_J3_REF_DIRECTION,
    DDA,
    DDA_ASSEMBLY_BASIS,
    DDA_GNSS_TOP_Z_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    DDA_OPPOSITE_PCB_SURFACE_Z_MM,
    DDA_PCB_ENVELOPE_MARGIN_MM,
    DDA_PIN1_TOP_EDGE_OFFSET_MM,
    DDA_PIN1_TOP_SIDE_POSITION,
    DDA_PIN1_UNDERSIDE_POSITION,
    DDA_ROTATION_180,
    DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM,
    DDA_TARGET_BOUNDS_STEP_MM,
    J1_BOTTOM_ENTRY_CONTACT_MIN_MM,
    J1_CANDIDATE_PART,
    J1_FOOTPRINT,
    J1_INSERTION_DEPTH_MIN_MM,
    J1_NOMINAL_STACK_HEIGHT_MM,
    J1_ORIGIN_MM,
    J1_SEATING_GAP_MM,
    J2_BODY_Z_MAX_MM,
    J2_CANDIDATE_PART,
    J2_DDA_SOCKET_MATING_FACE_Z_MM,
    J2_FOOTPRINT,
    J2_FOOTPRINT_ROTATION_DEG,
    J2_LOWER_POST_LENGTH_MM,
    J2_LOWER_TIP_Z_MM,
    J2_MATING_POST_LENGTH_MM,
    J2_OAL_MM,
    J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
    J2_UPPER_TIP_Z_MM,
)
from fetch_reference_cad import REFERENCES, REFERENCE_DIR, UPSTREAM_COMMIT, digest
from mechanical_geometry import (
    Box,
    adapter_box,
    assembly_axis_vectors,
    axis_constraint_errors,
    connector_boxes,
    dda_boxes,
    dda_pcb_envelope_errors,
    dda_projected_bounds,
)
from verify_connectivity import child, children, parse_sexpr, properties, transformed_pad


ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "pcb" / "compute-blade-dda-adapter.kicad_pcb"
HALF_BODY_EXPECTED_SIZE = (224.1209, 297.1934, 46.5000)


def step_vector(text: str, entity: str) -> tuple[float, float, float]:
    match = re.search(
        rf"#{re.escape(entity)}\s*=\s*(?:CARTESIAN_POINT|DIRECTION)\('',\(([^)]+)\)\);",
        text,
    )
    if not match:
        raise ValueError(f"STEP entity #{entity} is missing or not a point/vector")
    values = tuple(float(value) for value in match.group(1).split(","))
    if len(values) != 3:
        raise ValueError(f"STEP entity #{entity} is not three-dimensional")
    return values


def compute_blade_j3_frame(text: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    product = re.search(r"#\d+\s*=\s*PRODUCT\('J3','J3'", text)
    if not product:
        raise ValueError("Compute Blade STEP lacks the expected J3 assembly product")
    window = text[max(0, product.start() - 1200):product.end() + 1600]
    placements = re.findall(
        r"#\d+\s*=\s*AXIS2_PLACEMENT_3D\('',#(\d+),#(\d+),#(\d+)\);", window
    )
    candidates = []
    for point_id, _axis_id, ref_id in placements:
        point = step_vector(text, point_id)
        if any(abs(value) > 1e-9 for value in point):
            candidates.append((point, step_vector(text, ref_id)))
    if len(candidates) != 1:
        raise ValueError(f"expected one non-origin J3 placement, found {len(candidates)}")
    return candidates[0]


def compute_blade_pcb_bounds(text: str) -> tuple[float, float, float, float, float, float]:
    board = re.search(r"#\d+\s*=\s*PRODUCT\('Board','Board'", text)
    j3 = re.search(r"#\d+\s*=\s*PRODUCT\('J3','J3'", text)
    if not board or not j3 or j3.start() <= board.end():
        raise ValueError("Compute Blade STEP lacks the expected Board/J3 product ordering")
    brep = text.find("ADVANCED_BREP_SHAPE_REPRESENTATION", board.end(), j3.start())
    if brep < 0:
        raise ValueError("Compute Blade STEP Board product lacks an advanced B-Rep")
    placements = re.findall(
        r"AXIS2_PLACEMENT_3D\('',#(\d+),#\d+,#\d+\);", text[board.end():brep]
    )
    offsets = [step_vector(text, point_id) for point_id in placements]
    offset = next((point for point in offsets if any(abs(v) > 1e-9 for v in point)), (0, 0, 0))
    points = []
    for match in re.finditer(r"CARTESIAN_POINT\('',\(([^)]+)\)\)", text[brep:j3.start()]):
        values = tuple(float(value) for value in match.group(1).split(","))
        if len(values) == 3:
            points.append(values)
    if not points:
        raise ValueError("Compute Blade STEP Board B-Rep contains no points")
    return tuple(
        value
        for axis in range(3)
        for value in (
            min(point[axis] for point in points) + offset[axis],
            max(point[axis] for point in points) + offset[axis],
        )
    )


def vector_close(actual: tuple[float, ...], expected: tuple[float, ...], tolerance: float) -> bool:
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))


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
    start, end = child(rectangles[0], "start"), child(rectangles[0], "end")
    assert start and end
    xs = (float(start[1]) - J1_ORIGIN_MM[0], float(end[1]) - J1_ORIGIN_MM[0])
    ys = (float(start[2]) - J1_ORIGIN_MM[1], float(end[2]) - J1_ORIGIN_MM[1])
    return min(xs), max(xs), min(ys), max(ys)


def _find_footprint(tree: list, reference: str) -> list | None:
    return next(
        (node for node in children(tree, "footprint") if properties(node).get("Reference") == reference),
        None,
    )


def validate_footprint() -> list[str]:
    tree = parse_sexpr(PCB.read_text(encoding="utf-8"))
    j1, j2 = _find_footprint(tree, "J1"), _find_footprint(tree, "J2")
    errors: list[str] = []
    for ref, footprint, expected in (("J1", j1, J1_FOOTPRINT), ("J2", j2, J2_FOOTPRINT)):
        if footprint is None:
            errors.append(f"PCB has no {ref} footprint")
        elif len(footprint) < 2 or footprint[1] != expected:
            errors.append(f"{ref} must use {expected}, found {footprint[1] if len(footprint) > 1 else '<missing>'}")
    if j2 is None:
        return errors
    at = child(j2, "at")
    angle = float(at[3]) if at and len(at) > 3 else 0.0
    if angle % 360 != J2_FOOTPRINT_ROTATION_DEG % 360:
        errors.append(f"J2 rotation must be {J2_FOOTPRINT_ROTATION_DEG:g} degrees; found {angle:g}")
    pads = {pad[1]: pad for pad in children(j2, "pad")}
    if not all(pin in pads for pin in ("1", "2", "3")):
        errors.append("J2 footprint lacks physical pads 1, 2, or 3")
        return errors
    p1, p2, p3 = (transformed_pad(j2, pads[pin]) for pin in ("1", "2", "3"))
    row = tuple(round(p2[i] - p1[i], 6) for i in range(2))
    column = tuple(round(p3[i] - p1[i], 6) for i in range(2))
    if row != (0.0, -2.54):
        errors.append(f"J2 physical row 1->2 must map to -Y; found {row}")
    if column != (2.54, 0.0):
        errors.append(f"J2 six-position axis must map to +X; found {column}")
    return errors


def check_references() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    for reference in REFERENCES:
        path = REFERENCE_DIR / reference.name
        if not path.exists():
            errors.append(f"missing reference CAD: {path.relative_to(ROOT)}")
        elif digest(path) != reference.sha256:
            errors.append(f"reference CAD hash mismatch: {reference.name}")
    step = REFERENCE_DIR / "compute_blade_dev.step"
    if step.exists():
        text = step.read_text(encoding="utf-8", errors="ignore")
        try:
            anchor, direction = compute_blade_j3_frame(text)
            bounds = compute_blade_pcb_bounds(text)
            if not vector_close(anchor, COMPUTE_BLADE_STEP_J3_ANCHOR_MM, 1e-6):
                errors.append(f"unexpected Compute Blade J3 anchor: {anchor}")
            if not vector_close(direction, COMPUTE_BLADE_STEP_J3_REF_DIRECTION, 1e-6):
                errors.append(f"unexpected Compute Blade J3 direction: {direction}")
            if not vector_close(bounds, COMPUTE_BLADE_PCB_BOUNDS_MM, 1e-6):
                errors.append(f"unexpected Compute Blade PCB bounds: {bounds}")
            notes.append(f"official STEP J3 anchor {anchor}; PCB bounds {bounds}")
        except ValueError as exc:
            errors.append(str(exc))
    half = REFERENCE_DIR / "bladerunner_19in_half_body.stl"
    if half.exists():
        minima, maxima, triangles = stl_bounds(half)
        size = tuple(maxima[i] - minima[i] for i in range(3))
        if any(abs(size[i] - HALF_BODY_EXPECTED_SIZE[i]) > 0.01 for i in range(3)):
            errors.append(f"unexpected BladeRunner half-body bounds: {size}")
        notes.append(
            f"authenticated BladeRunner half-body mesh {size[0]:.4f} x {size[1]:.4f} x {size[2]:.4f} mm; {triangles} triangles"
        )
        notes.append(
            "per-blade physical clearance uses the previously slit-edge-derived 19.9317 mm value; "
            "mesh hash and outer bounds are revalidated here"
        )
    return errors, notes


def validate_connector_constraints() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    errors.extend(axis_constraint_errors())
    if DDA_ASSEMBLY_BASIS != ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        errors.append("DDA transform must preserve an XY PCB plane with +Z outward")

    measured = COMPUTE_BLADE_HEADER_PIN_TIP_MM - COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM
    if abs(measured - COMPUTE_BLADE_EXPOSED_POST_MM) > 1e-9:
        errors.append("Compute Blade exposed-post arithmetic is inconsistent")
    expected_hle = J1_BOTTOM_ENTRY_CONTACT_MIN_MM + BOARD_THICKNESS_MM
    if abs(J1_INSERTION_DEPTH_MIN_MM - expected_hle) > 1e-9:
        errors.append("HLE bottom-entry requirement must include adapter thickness")
    if COMPUTE_BLADE_EXPOSED_POST_MM < J1_INSERTION_DEPTH_MIN_MM:
        errors.append("Compute Blade post does not meet HLE bottom-entry reach")
    if ADAPTER_Z_ABOVE_BLADE_MM != COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM + J1_SEATING_GAP_MM:
        errors.append("adapter underside must sit at the header-plastic top plus explicit gap")
    notes.append(
        f"J1 {J1_CANDIDATE_PART}: {COMPUTE_BLADE_EXPOSED_POST_MM:.3f} mm post >= "
        f"{J1_BOTTOM_ENTRY_CONTACT_MIN_MM:.3f} + {BOARD_THICKNESS_MM:.3f} = "
        f"{J1_INSERTION_DEPTH_MIN_MM:.3f} mm required; open pass-through prevents closed-end bottoming"
    )

    expected_upper = J2_OAL_MM - 1.520 - J2_LOWER_POST_LENGTH_MM
    if abs(J2_MATING_POST_LENGTH_MM - expected_upper) > 1e-9:
        errors.append("MTLW upper post is not derived from OAL/body/-035 geometry")
    if J2_MATING_POST_LENGTH_MM < DDA_MIN_ACCEPTABLE_INSERTION_MM:
        errors.append("reverse MTLW segment is too short for DDA insertion")
    if J2_LOWER_TIP_Z_MM <= 0:
        errors.append("reverse MTLW lower geometry crosses the Compute Blade PCB plane")
    insertion = J2_UPPER_TIP_Z_MM - J2_DDA_SOCKET_MATING_FACE_Z_MM
    if abs(insertion - DDA_MIN_ACCEPTABLE_INSERTION_MM) > 1e-9:
        errors.append("modeled DDA insertion is not exactly 3.40 mm")
    notes.append(
        f"J2 {J2_CANDIDATE_PART}: upper/reversed mating segment {J2_MATING_POST_LENGTH_MM:.3f} mm; "
        f"insertion {insertion:.3f} mm; free post {J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM:.3f} mm; "
        f"lower tip Z {J2_LOWER_TIP_Z_MM:.3f} mm"
    )

    if DDA_PIN1_TOP_SIDE_POSITION != "bottom-left" or DDA_PIN1_UNDERSIDE_POSITION != "bottom-right":
        errors.append("confirmed DDA physical pin-1 orientation changed")
    if abs(DDA_PIN1_TOP_EDGE_OFFSET_MM - DDA.top_to_row2) > 1e-9:
        errors.append("DDA physical pin 1 must be in the row farther from its top edge")
    if abs(DDA_OPPOSITE_PCB_SURFACE_Z_MM - DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM - 1.6) > 1e-9:
        errors.append("DDA PCB thickness must be 1.6 mm")
    if abs(DDA_GNSS_TOP_Z_MM - DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM - 4.0) > 1e-9:
        errors.append("DDA outward 4.0 mm total was incorrectly added to PCB thickness")
    return errors, notes


def geometry_checks() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    boxes = dda_boxes(False)
    errors.extend(
        dda_pcb_envelope_errors(
            boxes, COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM, DDA_PCB_ENVELOPE_MARGIN_MM
        )
    )
    projected = dda_projected_bounds(boxes)
    expected = tuple(
        DDA_TARGET_BOUNDS_STEP_MM[i] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[i // 2]
        for i in range(4)
    )
    if not vector_close(projected, expected, 1e-6):
        errors.append(f"DDA projected bounds differ from approved placement: {projected}")

    blade = Box("compute_blade_pcb", *(
        COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM[0:2]
        + COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM[2:4]
        + (COMPUTE_BLADE_PCB_BOUNDS_MM[4], COMPUTE_BLADE_PCB_BOUNDS_MM[5])
    ))
    adapter = adapter_box(board_bounds())
    for box in boxes:
        if box.overlaps(blade):
            errors.append(f"{box.name} intersects the Compute Blade PCB solid")
        if box.overlaps(adapter):
            errors.append(f"{box.name} intersects the adapter PCB")

    total = DDA_GNSS_TOP_Z_MM
    physical_margin = BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - total
    reserve_margin = BLADERUNNER_PER_BLADE_DESIGN_MAX_MM - total
    if total > BLADERUNNER_PER_BLADE_DESIGN_MAX_MM:
        errors.append("outward stack exceeds the BladeRunner design maximum")
    if physical_margin < BLADERUNNER_Z_SAFETY_MARGIN_MM:
        errors.append("nominal physical BladeRunner clearance is below 1.0 mm")
    if J2_BODY_Z_MAX_MM > ADAPTER_Z_ABOVE_BLADE_MM:
        errors.append("reverse MTLW insulator is not on the Compute-Blade side of adapter")

    global_bounds = (
        projected[0] + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
        projected[1] + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
        projected[2] + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
        projected[3] + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
    )
    notes.extend([
        f"DDA projected STEP-frame XY bounds: X {global_bounds[0]:.3f}..{global_bounds[1]:.3f}, Y {global_bounds[2]:.3f}..{global_bounds[3]:.3f} mm",
        f"adapter underside {ADAPTER_Z_ABOVE_BLADE_MM:.3f} mm; DDA mating plane {J2_DDA_SOCKET_MATING_FACE_Z_MM:.3f} mm; socket-side PCB surface {DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM:.3f} mm",
        f"outward stack {total:.4f} mm; physical clearance {physical_margin:.4f} mm; margin after {BLADERUNNER_Z_SAFETY_MARGIN_MM:.1f} mm reserve {reserve_margin:.4f} mm",
        "orientation vectors: " + "; ".join(f"{key}={value}" for key, value in assembly_axis_vectors().items()),
    ])
    return errors, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare-variants", action="store_true", help="retained for CI compatibility")
    args = parser.parse_args()
    errors, notes = check_references()
    errors.extend(validate_footprint())
    connector_errors, connector_notes = validate_connector_constraints()
    geometry_errors, geometry_notes = geometry_checks()
    errors.extend(connector_errors + geometry_errors)
    notes.extend(connector_notes + geometry_notes)
    if args.compare_variants:
        notes.append("no alternate DDA orientation is generated; confirmed GNSS-outward orientation only")

    if board_bounds() != BOARD_BOUNDS_RELATIVE_J1_MM:
        errors.append("generated PCB outline differs from shared configuration")
    if DDA_ROTATION_180:
        errors.append("confirmed parallel orientation must not select a 180-degree diagnostic variant")

    print("Parallel-DDA mechanical geometry validation")
    print(f"Pinned Compute Blade commit: {UPSTREAM_COMMIT}")
    for note in notes:
        print(f"  {note}")
    if errors:
        print("Geometry validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Geometry validation PASSED for the approved parallel orientation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
