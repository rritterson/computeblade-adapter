#!/usr/bin/env python3
"""Conservative parallel-stack solids shared by every generator and validator."""

from __future__ import annotations

from dataclasses import dataclass

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BOARD_THICKNESS_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    COMPUTE_BLADE_STEP_J3_ANCHOR_MM,
    DDA,
    DDA_ASSEMBLY_BASIS,
    DDA_BATTERY_INWARD_Z_MIN_MM,
    DDA_COLUMN_AXIS,
    DDA_GNSS_TOP_Z_MM,
    DDA_OPPOSITE_PCB_SURFACE_Z_MM,
    DDA_PCB_NORMAL,
    DDA_SOCKET_MATING_AXIS,
    DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM,
    DDA_TARGET_BOUNDS_STEP_MM,
    DDA_TOP_TO_BOTTOM_AXIS,
    J1_BODY_Z_MAX_MM,
    J1_BODY_Z_MIN_MM,
    J2_BODY_PLAN_MM,
    J2_BODY_Z_MAX_MM,
    J2_BODY_Z_MIN_MM,
    J2_COLUMN_AXIS,
    J2_DDA_SOCKET_MATING_FACE_Z_MM,
    J2_LOWER_TIP_Z_MM,
    J2_MATING_DIRECTION,
    J2_ORIGIN_MM,
    J2_ROW1_TO_ROW2_AXIS,
    J2_SOLDER_TAIL_AXIS,
    J2_UPPER_TIP_Z_MM,
    J1_ORIGIN_MM,
)


@dataclass(frozen=True)
class Box:
    name: str
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float

    def overlaps(self, other: "Box", tolerance: float = 0.0) -> bool:
        return all(
            left_max > right_min + tolerance and right_max > left_min + tolerance
            for left_min, left_max, right_min, right_max in (
                (self.xmin, self.xmax, other.xmin, other.xmax),
                (self.ymin, self.ymax, other.ymin, other.ymax),
                (self.zmin, self.zmax, other.zmin, other.zmax),
            )
        )

    @property
    def size(self) -> tuple[float, float, float]:
        return self.xmax - self.xmin, self.ymax - self.ymin, self.zmax - self.zmin


def relative_j2() -> tuple[float, float]:
    return J2_ORIGIN_MM[0] - J1_ORIGIN_MM[0], J2_ORIGIN_MM[1] - J1_ORIGIN_MM[1]


def dda_bounds_relative_j3() -> tuple[float, float, float, float]:
    ax, ay, _ = COMPUTE_BLADE_STEP_J3_ANCHOR_MM
    x0, x1, y0, y1 = DDA_TARGET_BOUNDS_STEP_MM
    return x0 - ax, x1 - ax, y0 - ay, y1 - ay


def _rotate_box_z_180(box: Box, center_x: float, center_y: float) -> Box:
    return Box(
        box.name,
        2 * center_x - box.xmax,
        2 * center_x - box.xmin,
        2 * center_y - box.ymax,
        2 * center_y - box.ymin,
        box.zmin,
        box.zmax,
    )


def dda_boxes(rotation_180: bool = False) -> list[Box]:
    """Return the approved flat DDA stack in the J3-relative assembly frame."""
    x0, x1, y0, y1 = dda_bounds_relative_j3()
    socket_x0 = x0 + (DDA.pcb_width - DDA.socket_body_length) / 2
    socket_x1 = socket_x0 + DDA.socket_body_length
    socket_y0 = y0 + DDA.top_to_socket_near_edge
    socket_y1 = socket_y0 + DDA.socket_body_depth
    boxes = [
        Box(
            "dda_pcb", x0, x1, y0, y1,
            DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM, DDA_OPPOSITE_PCB_SURFACE_Z_MM,
        ),
        Box(
            "dda_socket", socket_x0, socket_x1, socket_y0, socket_y1,
            J2_DDA_SOCKET_MATING_FACE_Z_MM, DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM,
        ),
        # This is the outward-only portion. The 4.0 mm input already includes
        # PCB thickness, so this box is exactly 2.4 mm high, not 4.0 mm high.
        Box(
            "dda_gnss_envelope", x0, x1, y0, y1,
            DDA_OPPOSITE_PCB_SURFACE_Z_MM, DDA_GNSS_TOP_Z_MM,
        ),
        # Conservative full-face proxy for the local battery/RTC maximum. It
        # affects inward collision checks only and never the outward height.
        Box(
            "dda_battery_rtc_inward_envelope", x0, x1, y0, y1,
            DDA_BATTERY_INWARD_Z_MIN_MM, DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM,
        ),
    ]
    if rotation_180:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        boxes = [_rotate_box_z_180(box, cx, cy) for box in boxes]
    return boxes


def connector_boxes() -> list[Box]:
    """Return manufacturer-dimensioned connector envelopes relative to J3."""
    j2x, j2y = relative_j2()
    body_length, body_width = J2_BODY_PLAN_MM
    # Pin 1 is 1.90 mm from the DDA left edge and the body is centered over
    # the 12.70 x 2.54 mm pin grid.
    body_x0 = j2x - 1.27
    body_x1 = body_x0 + body_length
    body_y0 = j2y - body_width / 2
    body_y1 = j2y + body_width / 2
    return [
        Box(
            "compute_blade_header_plastic", -3.81, 1.27, -1.27, 11.43,
            0.0, COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
        ),
        Box(
            "compute_blade_header_exposed_posts", -2.86, 0.32, -0.32, 10.48,
            COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM, COMPUTE_BLADE_HEADER_PIN_TIP_MM,
        ),
        Box(
            "j1_hle_body", -3.81, 1.27, -1.27, 11.43,
            J1_BODY_Z_MIN_MM, J1_BODY_Z_MAX_MM,
        ),
        Box(
            "j2_mtlw_reverse_insulator", body_x0, body_x1, body_y0, body_y1,
            J2_BODY_Z_MIN_MM, J2_BODY_Z_MAX_MM,
        ),
        Box(
            "j2_upper_dda_mating_posts",
            j2x - 0.32, j2x + 5 * DDA.row_pitch + 0.32,
            j2y - DDA.row_pitch - 0.32, j2y + 0.32,
            J2_BODY_Z_MAX_MM, J2_UPPER_TIP_Z_MM,
        ),
        Box(
            "j2_lower_posts",
            j2x - 0.32, j2x + 5 * DDA.row_pitch + 0.32,
            j2y - DDA.row_pitch - 0.32, j2y + 0.32,
            J2_LOWER_TIP_Z_MM, J2_BODY_Z_MIN_MM,
        ),
    ]


def dda_assembly_basis() -> tuple[tuple[float, float, float], ...]:
    return DDA_ASSEMBLY_BASIS


def assembly_axis_vectors() -> dict[str, tuple[float, float, float]]:
    """Return the vector contract directly embodied by the parallel model."""
    return {
        "dda_pcb_normal": DDA_PCB_NORMAL,
        "dda_column_axis": DDA_COLUMN_AXIS,
        "dda_top_to_bottom_axis": DDA_TOP_TO_BOTTOM_AXIS,
        "dda_socket_mating_axis": DDA_SOCKET_MATING_AXIS,
        "j2_column_axis": J2_COLUMN_AXIS,
        "j2_row1_to_row2": J2_ROW1_TO_ROW2_AXIS,
        "j2_mating_axis": J2_MATING_DIRECTION,
        "j2_solder_tail_axis": J2_SOLDER_TAIL_AXIS,
    }


def axis_constraint_errors(
    vectors: dict[str, tuple[float, float, float]] | None = None,
) -> list[str]:
    actual = assembly_axis_vectors() if vectors is None else vectors
    expected = assembly_axis_vectors()
    return [
        f"{name} must be {target}, derived {actual.get(name)}"
        for name, target in expected.items()
        if actual.get(name) != target
    ]


def dda_projected_bounds(boxes: list[Box]) -> tuple[float, float, float, float]:
    return (
        min(box.xmin for box in boxes), max(box.xmax for box in boxes),
        min(box.ymin for box in boxes), max(box.ymax for box in boxes),
    )


def dda_pcb_envelope_errors(
    boxes: list[Box],
    blade_bounds: tuple[float, float, float, float],
    margin: float,
) -> list[str]:
    dx0, dx1, dy0, dy1 = dda_projected_bounds(boxes)
    bx0, bx1, by0, by1 = blade_bounds
    errors = []
    if dx0 < bx0 + margin:
        errors.append("DDA projected X minimum violates the Compute Blade PCB margin")
    if dx1 > bx1 - margin:
        errors.append("DDA projected X maximum violates the Compute Blade PCB margin")
    if dy0 < by0 + margin:
        errors.append("DDA projected Y minimum violates the Compute Blade PCB margin")
    if dy1 > by1 - margin:
        errors.append("DDA projected Y maximum violates the Compute Blade PCB margin")
    return errors


def adapter_box(board_bounds: tuple[float, float, float, float]) -> Box:
    xmin, xmax, ymin, ymax = board_bounds
    return Box(
        "adapter_pcb", xmin, xmax, ymin, ymax,
        ADAPTER_Z_ABOVE_BLADE_MM, ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
    )
