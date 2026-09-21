#!/usr/bin/env python3
"""Validate the assembled adapter with conservative, documented envelopes."""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_CLEARANCE_Y,
    BLADERUNNER_CLEARANCE_Z,
    BOARD_BOUNDS_RELATIVE_J1_MM,
    BLADE_PCB_ENVELOPE,
    COMPUTE_BLADE_EXPOSED_POST_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    COMPUTE_BLADE_PCB_BOUNDS_MM,
    COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM,
    COMPUTE_BLADE_STEP_J3_ANCHOR_MM,
    COMPUTE_BLADE_STEP_J3_REF_DIRECTION,
    COMPUTE_BLADE_STEP_BOUNDS_MM,
    DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    DDA_PCB_ENVELOPE_MARGIN_MM,
    DDA_PLACEMENT_Y_SIGN,
    NEARBY_BLADE_COMPONENT_KEEP_OUTS,
    DDA,
    DDA_PIN1_TOP_EDGE_OFFSET_MM,
    DDA_PIN1_TOP_SIDE_POSITION,
    DDA_PIN1_UNDERSIDE_POSITION,
    DDA_ROTATION_180,
    DDA_ASSEMBLY_BASIS,
    J1_INSERTION_DEPTH_MIN_MM,
    J1_NOMINAL_STACK_HEIGHT_MM,
    J1_ORIGIN_MM,
    J1_SEATING_GAP_MM,
    J1_SOCKET_BODY_HEIGHT_MM,
    J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM,
    J2_FOOTPRINT,
    J2_FOOTPRINT_ROTATION_DEG,
    J2_MATING_DIRECTION,
    J2_MATING_POST_LENGTH_MM,
    J2_ALTERNATIVE_MATING_POST_LENGTH_MM,
    J2_ALTERNATIVE_SOLDER_TAIL_LENGTH_MM,
    J2_PIN1_CENTER_Z_MM,
    J2_PIN1_IS_UPPER_MATING_ROW,
    J2_PIN2_CENTER_Z_MM,
    J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
    J2_POST_TIP_LOCAL_X_MM,
    J2_SOLDER_TAIL_LENGTH_MM,
    MAX_ASSEMBLED_Z_DEPTH_MM,
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
    j2_axis_y,
    relative_j2,
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
    """Extract J3's placement origin and +X reference direction from the STEP."""
    product = re.search(r"#\d+\s*=\s*PRODUCT\('J3','J3'", text)
    if not product:
        raise ValueError("Compute Blade STEP lacks the expected J3 assembly product")
    window = text[max(0, product.start() - 1200):product.end() + 1600]
    placements = re.findall(
        r"#\d+\s*=\s*AXIS2_PLACEMENT_3D\('',#(\d+),#(\d+),#(\d+)\);",
        window,
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
    """Extract the official PCB solid bounds from the STEP `Board` product."""
    board = re.search(r"#\d+\s*=\s*PRODUCT\('Board','Board'", text)
    j3 = re.search(r"#\d+\s*=\s*PRODUCT\('J3','J3'", text)
    if not board or not j3 or j3.start() <= board.end():
        raise ValueError("Compute Blade STEP lacks the expected Board/J3 product ordering")
    brep = text.find("ADVANCED_BREP_SHAPE_REPRESENTATION", board.end(), j3.start())
    if brep < 0:
        raise ValueError("Compute Blade STEP Board product lacks an advanced B-Rep")
    placement_window = text[board.end():brep]
    placements = re.findall(
        r"AXIS2_PLACEMENT_3D\('',#(\d+),#\d+,#\d+\);", placement_window
    )
    offsets = [step_vector(text, point_id) for point_id in placements]
    offset = next((point for point in offsets if any(abs(v) > 1e-9 for v in point)), (0.0, 0.0, 0.0))
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
            f"J2 rotation must be {J2_FOOTPRINT_ROTATION_DEG:g} degrees so its mating axis is +Y/top-side; found {angle:g}"
        )
    pads = {pad[1]: pad for pad in children(j2, "pad")}
    if "1" not in pads or "2" not in pads:
        errors.append("J2 footprint must contain physical pads 1 and 2")
    else:
        pad1_at = child(pads["1"], "at")
        pad2_at = child(pads["2"], "at")
        if not pad1_at or not pad2_at:
            errors.append("J2 pads 1 and 2 must have explicit coordinates")
        elif (float(pad1_at[1]), float(pad1_at[2])) != (0.0, 0.0) or (
            float(pad2_at[1]), float(pad2_at[2])
        ) != (2.54, 0.0):
            errors.append("J2 physical pads 1 and 2 no longer match the explicit footprint orientation")
    if all(pin in pads for pin in ("1", "2", "3")):
        pad1 = transformed_pad(j2, pads["1"])
        pad2 = transformed_pad(j2, pads["2"])
        pad3 = transformed_pad(j2, pads["3"])
        column_step = tuple(round(pad3[index] - pad1[index], 6) for index in range(2))
        tail_row_step = tuple(round(pad2[index] - pad1[index], 6) for index in range(2))
        if column_step != (-2.54, 0.0):
            errors.append(f"J2 six-position axis must run along assembly -X; found {column_step}")
        if tail_row_step != (0.0, 2.54):
            errors.append(f"J2 through-hole tail rows must separate along board +Y; found {tail_row_step}")
    if J2_MATING_DIRECTION != (0.0, 1.0, 0.0):
        errors.append("J2 mating direction must be global +Y toward the blade top/interior")
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
        try:
            anchor, ref_direction = compute_blade_j3_frame(text)
            if not vector_close(anchor, COMPUTE_BLADE_STEP_J3_ANCHOR_MM, 1e-6):
                errors.append(f"unexpected Compute Blade J3 STEP anchor: {anchor}")
            if not vector_close(ref_direction, COMPUTE_BLADE_STEP_J3_REF_DIRECTION, 1e-6):
                errors.append(f"unexpected Compute Blade J3 +X reference direction: {ref_direction}")
            notes.append(
                "Compute Blade STEP J3 frame: origin "
                + ", ".join(f"{value:.6f}" for value in anchor)
                + "; local +X follows the Compute Blade long axis"
            )
            pcb_bounds = compute_blade_pcb_bounds(text)
            if not vector_close(pcb_bounds, COMPUTE_BLADE_PCB_BOUNDS_MM, 1e-6):
                errors.append(f"unexpected Compute Blade PCB solid bounds: {pcb_bounds}")
            notes.append(
                "Compute Blade PCB solid bounds from official STEP: "
                f"X {pcb_bounds[0]:.3f}..{pcb_bounds[1]:.3f}, "
                f"Y {pcb_bounds[2]:.3f}..{pcb_bounds[3]:.3f}, "
                f"Z {pcb_bounds[4]:.3f}..{pcb_bounds[5]:.3f} mm"
            )
        except ValueError as exc:
            errors.append(str(exc))
        notes.append(f"Compute Blade STEP: {step.stat().st_size} bytes; J3 placement extracted")

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


def validate_connector_constraints(selected_rotation_180: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []

    derived_vectors = assembly_axis_vectors()
    errors.extend(axis_constraint_errors(derived_vectors))
    expected_basis = ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    if DDA_ASSEMBLY_BASIS != expected_basis:
        errors.append("axis-derived DDA basis does not map its PCB into the XZ plane")
    if DDA_PLACEMENT_Y_SIGN != 1 or J2_MATING_DIRECTION[1] != DDA_PLACEMENT_Y_SIGN:
        errors.append("DDA/J2 direction does not target the blade top/interior +Y side")
    notes.append(
        "Axis-derived IMG_0542 orientation: DDA plane XZ; columns -X; mating/PCB normal +Y; "
        "J2 row 1->2 -Z; solder tails +Z"
    )
    notes.append(
        "Derived vectors: "
        + "; ".join(f"{name}={value}" for name, value in derived_vectors.items())
    )

    measured_exposed = COMPUTE_BLADE_HEADER_PIN_TIP_MM - COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM
    if abs(measured_exposed - COMPUTE_BLADE_EXPOSED_POST_MM) > 1e-9:
        errors.append("Compute Blade pin-tip minus plastic-top does not equal measured exposed post")
    if COMPUTE_BLADE_EXPOSED_POST_MM < J1_INSERTION_DEPTH_MIN_MM:
        errors.append(
            "Compute Blade exposed post is shorter than the SLW minimum insertion depth"
        )
    expected_stack = COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM + J1_SOCKET_BODY_HEIGHT_MM
    if abs(J1_NOMINAL_STACK_HEIGHT_MM - expected_stack) > 1e-9:
        errors.append("nominal J1 stack is not header-plastic height plus SLW body height")
    if abs(ADAPTER_Z_ABOVE_BLADE_MM - (J1_NOMINAL_STACK_HEIGHT_MM + J1_SEATING_GAP_MM)) > 1e-9:
        errors.append("adapter height does not include the explicit J1 seating-gap parameter")
    notes.append(
        f"J1 engagement: measured exposed post {COMPUTE_BLADE_EXPOSED_POST_MM:.3f} mm "
        f">= SLW minimum insertion {J1_INSERTION_DEPTH_MIN_MM:.3f} mm"
    )
    notes.append(
        f"J1 stack: {J1_NOMINAL_STACK_HEIGHT_MM:.3f} mm nominal + "
        f"{J1_SEATING_GAP_MM:.3f} mm seating gap = {ADAPTER_Z_ABOVE_BLADE_MM:.3f} mm"
    )

    calculated_requirement = (
        COMPUTE_BLADE_EXPOSED_POST_MM - DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM
    )
    if abs(DDA_MIN_ACCEPTABLE_INSERTION_MM - 3.40) > 1e-9:
        errors.append("DDA minimum acceptable insertion must remain exactly 3.40 mm")
    if abs(DDA_MIN_ACCEPTABLE_INSERTION_MM - calculated_requirement) > 1e-9:
        errors.append("DDA insertion requirement is not exposed post minus acceptable remainder")
    if J2_MATING_POST_LENGTH_MM < DDA_MIN_ACCEPTABLE_INSERTION_MM:
        errors.append("TSW usable mating post is shorter than the required DDA insertion")
    post_margin = J2_MATING_POST_LENGTH_MM - DDA_MIN_ACCEPTABLE_INSERTION_MM
    if abs(post_margin - J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM) > 1e-9:
        errors.append("TSW post-length margin calculation is inconsistent")
    if post_margin <= 0:
        errors.append("no TSW post remains after the minimum acceptable DDA insertion")
    notes.append(
        f"DDA acceptance requirement: {COMPUTE_BLADE_EXPOSED_POST_MM:.3f} mm exposed post - "
        f"{DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM:.3f} mm acceptable remainder = "
        f"{DDA_MIN_ACCEPTABLE_INSERTION_MM:.3f} mm minimum insertion"
    )
    notes.append(
        f"J2 post check: {J2_MATING_POST_LENGTH_MM:.3f} mm usable post >= "
        f"{DDA_MIN_ACCEPTABLE_INSERTION_MM:.3f} mm required; "
        f"post-length margin {post_margin:.3f} mm"
    )
    if J2_SOLDER_TAIL_LENGTH_MM < 0.8:
        errors.append("TSW-106-08 solder tail is shorter than the 0.8 mm adapter PCB")
    if J2_ALTERNATIVE_MATING_POST_LENGTH_MM != J2_MATING_POST_LENGTH_MM:
        errors.append("documented -09 comparison no longer has the same mating-post length")
    if J2_ALTERNATIVE_SOLDER_TAIL_LENGTH_MM <= J2_SOLDER_TAIL_LENGTH_MM:
        errors.append("documented -09 comparison must retain its longer solder tail")
    notes.append(
        f"TSW variant check: -08 tail {J2_SOLDER_TAIL_LENGTH_MM:.3f} mm; "
        f"-09 tail {J2_ALTERNATIVE_SOLDER_TAIL_LENGTH_MM:.3f} mm; both mating posts "
        f"{J2_MATING_POST_LENGTH_MM:.3f} mm"
    )

    if not J2_PIN1_IS_UPPER_MATING_ROW or J2_PIN1_CENTER_Z_MM <= J2_PIN2_CENTER_Z_MM:
        errors.append("TSW physical pin 1 must be the upper right-angle mating row")
    if DDA_PIN1_TOP_SIDE_POSITION != "bottom-left":
        errors.append("DDA physical pin 1 must be bottom-left in the readable top-side view")
    if DDA_PIN1_UNDERSIDE_POSITION != "bottom-right":
        errors.append("DDA physical pin 1 must be bottom-right in the underside hole view")
    if abs(DDA_PIN1_TOP_EDGE_OFFSET_MM - DDA.top_to_row2) > 1e-9:
        errors.append("DDA physical pin 1 must occupy the row farther from its top edge")
    if selected_rotation_180:
        errors.append("selected 180-degree DDA rotation contradicts the confirmed physical pin-1 orientation")
    notes.append(
        "Pin-1 orientation: TSW pin 1 upper row -> DDA bottom-left from readable top side "
        "(bottom-right from underside)"
    )
    return errors, notes


def variant_checks(rotation_180: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    boxes = dda_boxes(rotation_180)
    errors.extend(
        dda_pcb_envelope_errors(
            boxes, COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM, DDA_PCB_ENVELOPE_MARGIN_MM
        )
    )
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

    j2_x, j2_y = relative_j2()
    if min(box.ymin for box in boxes) <= j2_y:
        errors.append("DDA does not extend exclusively toward the top/interior +Y side of J2")

    socket = next(box for box in boxes if box.name == "dda_socket")
    pcb = next(box for box in boxes if box.name == "dda_pcb")
    expected_face = j2_axis_y(J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM)
    if abs(socket.ymin - expected_face) > 1e-6:
        errors.append("DDA socket mating face does not coincide with the J2 mating plane")
    if abs(pcb.ymin - (expected_face + DDA.pcb_surface_to_mating_plane)) > 1e-6:
        errors.append("DDA PCB-to-socket mating-plane offset is not 8.3 mm")

    connectors = connector_boxes()
    header_body = next(box for box in connectors if box.name == "j2_body_elbow_keepout")
    posts = next(box for box in connectors if box.name == "j2_mating_posts")
    insertion = max(0.0, min(posts.ymax, socket.ymax) - max(posts.ymin, socket.ymin))
    if abs(insertion - DDA_MIN_ACCEPTABLE_INSERTION_MM) > 1e-6:
        errors.append("modeled TSW-to-DDA insertion is not exactly the 3.40 mm requirement")
    if socket.overlaps(header_body):
        errors.append("DDA socket intersects the simplified TSW plastic body/elbow keepout")
    axial_clearance = socket.ymin - header_body.ymax
    if axial_clearance < 0:
        errors.append("TSW body/elbow blocks the required 3.40 mm DDA insertion")
    if abs(axial_clearance - J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM) > 1e-6:
        errors.append("modeled J2 axial body clearance does not match the post-length margin")
    if abs(posts.ymax - j2_axis_y(J2_POST_TIP_LOCAL_X_MM)) > 1e-6:
        errors.append("TSW post-tip position does not match its manufacturer post length")

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
    projected = dda_projected_bounds(boxes)
    blade_xy = COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM
    notes.append(
        f"Compute Blade PCB relative XY: X {blade_xy[0]:.3f}..{blade_xy[1]:.3f}, "
        f"Y {blade_xy[2]:.3f}..{blade_xy[3]:.3f} mm; "
        f"DDA projected XY: X {projected[0]:.3f}..{projected[1]:.3f}, "
        f"Y {projected[2]:.3f}..{projected[3]:.3f} mm; "
        f"edge clearances Y- {projected[2] - blade_xy[2]:.3f} mm, "
        f"Y+ {blade_xy[3] - projected[3]:.3f} mm; required margin "
        f"{DDA_PCB_ENVELOPE_MARGIN_MM:.3f} mm"
    )
    global_boxes = [
        Box(
            box.name,
            box.xmin + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
            box.xmax + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
            box.ymin + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
            box.ymax + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
            box.zmin + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[2],
            box.zmax + COMPUTE_BLADE_STEP_J3_ANCHOR_MM[2],
        )
        for box in [*boxes, *connector_boxes()]
    ]
    bx = COMPUTE_BLADE_STEP_BOUNDS_MM
    assembly_bounds = (
        min(bx[0], *(box.xmin for box in global_boxes)),
        max(bx[1], *(box.xmax for box in global_boxes)),
        min(bx[2], *(box.ymin for box in global_boxes)),
        max(bx[3], *(box.ymax for box in global_boxes)),
        min(bx[4], *(box.zmin for box in global_boxes)),
        max(bx[5], *(box.zmax for box in global_boxes)),
    )
    z_depth = assembly_bounds[5] - assembly_bounds[4]
    if z_depth > MAX_ASSEMBLED_Z_DEPTH_MM:
        errors.append(
            f"assembled Z depth {z_depth:.3f} mm exceeds {MAX_ASSEMBLED_Z_DEPTH_MM:.3f} mm; wrong-axis rotation suspected"
        )
    notes.append(
        "Assembled bounds without BladeRunner frame: "
        f"X {assembly_bounds[0]:.3f}..{assembly_bounds[1]:.3f}, "
        f"Y {assembly_bounds[2]:.3f}..{assembly_bounds[3]:.3f}, "
        f"Z {assembly_bounds[4]:.3f}..{assembly_bounds[5]:.3f} mm; "
        f"total Z depth {z_depth:.3f} mm"
    )
    notes.append(
        f"Simplified TSW body/elbow axial clearance at "
        f"{DDA_MIN_ACCEPTABLE_INSERTION_MM:.2f} mm insertion: {axial_clearance:.3f} mm"
    )
    anchor = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    notes.append(
        "DDA envelope in official STEP J3-aligned frame: "
        f"X {anchor[0] + bounds[0]:.2f}..{anchor[0] + bounds[1]:.2f}, "
        f"Y {anchor[1] + bounds[2]:.2f}..{anchor[1] + bounds[3]:.2f}, "
        f"Z {anchor[2] + bounds[4]:.2f}..{anchor[2] + bounds[5]:.2f} mm"
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
    constraint_errors, constraint_notes = validate_connector_constraints(selected)
    errors.extend(constraint_errors)
    notes.extend(constraint_notes)
    try:
        adapter = adapter_box(board_bounds())
        if board_bounds() != BOARD_BOUNDS_RELATIVE_J1_MM:
            errors.append("generated PCB outline differs from the shared configured board bounds")
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
