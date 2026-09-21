#!/usr/bin/env python3
"""Conservative assembly solids shared by model generation and validation."""

from __future__ import annotations

from dataclasses import dataclass

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BOARD_THICKNESS_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    DDA,
    DDA_PLACEMENT_Y_SIGN,
    DDA_PIN1_TOP_EDGE_OFFSET_MM,
    DDA_ASSEMBLY_BASIS,
    DDA_COLUMN_AXIS,
    DDA_PCB_NORMAL,
    DDA_SOCKET_MATING_AXIS,
    DDA_TOP_TO_BOTTOM_AXIS,
    J1_SEATING_GAP_MM,
    J1_SOCKET_BODY_HEIGHT_MM,
    J1_ORIGIN_MM,
    J2_BODY_HEIGHT_MM,
    J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM,
    J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
    J2_HEADER_PLASTIC_Y_BOUNDS_MM,
    J2_ORIGIN_MM,
    J2_PIN1_CENTER_Z_MM,
    J2_PIN2_CENTER_Z_MM,
    J2_POST_TIP_LOCAL_X_MM,
    J2_COLUMN_AXIS,
    J2_MATING_DIRECTION,
    J2_ROW1_TO_ROW2_AXIS,
    J2_SOLDER_TAIL_AXIS,
    J2_SOLDER_TAIL_LENGTH_MM,
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


def j2_axis_y(distance: float) -> float:
    """Map a J2 footprint-local mating-axis distance into assembly Y."""
    return relative_j2()[1] + DDA_PLACEMENT_Y_SIGN * distance


def j2_axis_interval(start: float, end: float) -> tuple[float, float]:
    values = (j2_axis_y(start), j2_axis_y(end))
    return min(values), max(values)


def j2_column_x(distance: float) -> float:
    """Map a J2 footprint-local six-position-axis distance into assembly X."""
    return relative_j2()[0] + J2_COLUMN_AXIS[0] * distance


def j2_column_interval(start: float, end: float) -> tuple[float, float]:
    values = (j2_column_x(start), j2_column_x(end))
    return min(values), max(values)


def rotate_box_around_y(box: Box, center_x: float, center_z: float) -> Box:
    """Rotate an axis-aligned box 180 degrees around the +Y mating axis."""
    return Box(
        box.name,
        2 * center_x - box.xmax,
        2 * center_x - box.xmin,
        box.ymin,
        box.ymax,
        2 * center_z - box.zmax,
        2 * center_z - box.zmin,
    )


def transform_dda_local_box(box: Box, origin: tuple[float, float, float]) -> Box:
    """Apply the axis-derived DDA assembly basis and translation."""
    corners = []
    for x in (box.xmin, box.xmax):
        for y in (box.ymin, box.ymax):
            for z in (box.zmin, box.zmax):
                local = (x, y, z)
                corners.append(
                    tuple(
                        origin[row]
                        + sum(DDA_ASSEMBLY_BASIS[row][column] * local[column] for column in range(3))
                        for row in range(3)
                    )
                )
    return Box(
        box.name,
        min(point[0] for point in corners),
        max(point[0] for point in corners),
        min(point[1] for point in corners),
        max(point[1] for point in corners),
        min(point[2] for point in corners),
        max(point[2] for point in corners),
    )


def dda_boxes(rotation_180: bool) -> list[Box]:
    j2_x, j2_y = relative_j2()
    # Footprint local +X maps to assembly global +Y after its -90-degree KiCad
    # board rotation (KiCad board coordinates are Y-down).
    mating_y = j2_axis_y(J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM)
    # Confirmed top/component-side pin 1 is in the DDA row farther from its
    # top edge. It mates to the TSW physical-pin-1 (upper) row.
    # Derive the DDA local origin from the modeled physical-pin-1 center. This
    # remains valid when the connector is turned 180 degrees around global Z.
    pin1_local = (DDA.first_column_from_left, DDA_PIN1_TOP_EDGE_OFFSET_MM, 0.0)
    pin1_global = (j2_x, mating_y, J2_PIN1_CENTER_Z_MM)
    origin = tuple(
        pin1_global[row]
        - sum(DDA_ASSEMBLY_BASIS[row][column] * pin1_local[column] for column in range(3))
        for row in range(3)
    )
    center_x = j2_column_x(5 * DDA.row_pitch / 2)
    center_z = (J2_PIN1_CENTER_Z_MM + J2_PIN2_CENTER_Z_MM) / 2

    # Local X follows the six-pin row, local Y goes top-to-bottom, and local Z
    # goes from the socket mating plane toward/through the PCB.
    local_boxes = [
        Box(
            "dda_pcb",
            0.0,
            DDA.pcb_width,
            0.0,
            DDA.pcb_height,
            DDA.pcb_surface_to_mating_plane,
            DDA.pcb_surface_to_mating_plane + DDA.pcb_thickness,
        ),
        Box(
            "dda_socket",
            DDA.pcb_width / 2 - DDA.socket_body_length / 2,
            DDA.pcb_width / 2 + DDA.socket_body_length / 2,
            DDA.top_to_socket_near_edge,
            DDA.top_to_socket_near_edge + DDA.socket_body_depth,
            0.0,
            DDA.pcb_surface_to_mating_plane,
        ),
        Box(
            "dda_gnss_envelope",
            0.0,
            DDA.pcb_width,
            0.0,
            DDA.pcb_height,
            DDA.pcb_surface_to_mating_plane - DDA.gnss_envelope,
            DDA.pcb_surface_to_mating_plane,
        ),
        Box(
            "dda_battery_rtc_envelope",
            0.0,
            DDA.pcb_width,
            0.0,
            DDA.pcb_height,
            DDA.pcb_surface_to_mating_plane + DDA.pcb_thickness,
            DDA.pcb_surface_to_mating_plane + DDA.pcb_thickness + DDA.battery_rtc_envelope,
        ),
    ]
    boxes = [transform_dda_local_box(box, origin) for box in local_boxes]
    if rotation_180:
        boxes = [rotate_box_around_y(box, center_x, center_z) for box in boxes]
    return boxes


def connector_boxes() -> list[Box]:
    j2_x, j2_y = relative_j2()
    body_xmin, body_xmax = j2_column_interval(*J2_HEADER_PLASTIC_Y_BOUNDS_MM)
    posts_xmin, posts_xmax = j2_column_interval(-0.32, 5 * DDA.row_pitch + 0.32)
    tails_xmin, tails_xmax = posts_xmin, posts_xmax
    body_ymin, body_ymax = j2_axis_interval(-1.77, J2_HEADER_PLASTIC_FACE_LOCAL_X_MM)
    posts_ymin, posts_ymax = j2_axis_interval(
        J2_HEADER_PLASTIC_FACE_LOCAL_X_MM, J2_POST_TIP_LOCAL_X_MM
    )
    return [
        Box(
            "compute_blade_header_plastic",
            -3.81,
            1.27,
            -1.27,
            11.43,
            0.0,
            COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
        ),
        Box(
            "compute_blade_header_exposed_posts",
            -2.86,
            0.32,
            -0.32,
            10.48,
            COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
            COMPUTE_BLADE_HEADER_PIN_TIP_MM,
        ),
        Box(
            "j1_socket_body",
            -3.81,
            1.27,
            -1.27,
            11.43,
            COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM + J1_SEATING_GAP_MM,
            COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM
            + J1_SEATING_GAP_MM
            + J1_SOCKET_BODY_HEIGHT_MM,
        ),
        Box(
            "j2_body_elbow_keepout",
            body_xmin,
            body_xmax,
            body_ymin,
            body_ymax,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM + J2_BODY_HEIGHT_MM,
        ),
        Box(
            "j2_mating_posts",
            posts_xmin,
            posts_xmax,
            posts_ymin,
            posts_ymax,
            J2_PIN2_CENTER_Z_MM - 0.32,
            J2_PIN1_CENTER_Z_MM + 0.32,
        ),
        Box(
            "j2_solder_tails",
            tails_xmin,
            tails_xmax,
            j2_y - 0.32,
            j2_y + DDA.row_pitch + 0.32,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM - J2_SOLDER_TAIL_LENGTH_MM,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
        ),
    ]


def dda_assembly_basis() -> tuple[tuple[float, float, float], ...]:
    """Return the exact axis-derived DDA local-to-assembly basis."""
    return DDA_ASSEMBLY_BASIS


def _subtract(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a[index] - b[index] for index in range(3))


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = sum(value * value for value in vector) ** 0.5
    return tuple(round(value / length, 12) for value in vector)


def assembly_axis_vectors() -> dict[str, tuple[float, float, float]]:
    """Derive the physical axes from modeled J2 and DDA reference points."""
    j2_x, j2_y = relative_j2()
    row1_col1 = (j2_x, j2_y, J2_PIN1_CENTER_Z_MM)
    row1_col2 = (
        j2_x + J2_COLUMN_AXIS[0] * DDA.row_pitch,
        j2_y + J2_COLUMN_AXIS[1] * DDA.row_pitch,
        J2_PIN1_CENTER_Z_MM,
    )
    row2_col1 = (j2_x, j2_y, J2_PIN2_CENTER_Z_MM)
    mating_tip = (j2_x, j2_axis_y(J2_POST_TIP_LOCAL_X_MM), J2_PIN1_CENTER_Z_MM)
    mating_face = (
        j2_x,
        j2_axis_y(J2_HEADER_PLASTIC_FACE_LOCAL_X_MM),
        J2_PIN1_CENTER_Z_MM,
    )
    tail_bottom = (
        j2_x,
        j2_y,
        ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM - J2_SOLDER_TAIL_LENGTH_MM,
    )
    tail_top = (j2_x, j2_y, ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM)
    local_normal = (0.0, 0.0, 1.0)
    pcb_normal = tuple(
        sum(DDA_ASSEMBLY_BASIS[row][column] * local_normal[column] for column in range(3))
        for row in range(3)
    )
    return {
        "dda_pcb_normal": _unit(pcb_normal),
        "dda_column_axis": _unit(_subtract(row1_col2, row1_col1)),
        "dda_socket_mating_axis": _unit(_subtract(mating_tip, mating_face)),
        "j2_column_axis": _unit(_subtract(row1_col2, row1_col1)),
        "j2_row1_to_row2": _unit(_subtract(row2_col1, row1_col1)),
        "j2_mating_axis": _unit(_subtract(mating_tip, mating_face)),
        "j2_solder_tail_axis": _unit(_subtract(tail_top, tail_bottom)),
    }


def axis_constraint_errors(
    vectors: dict[str, tuple[float, float, float]] | None = None,
) -> list[str]:
    """Return hard failures for any orientation inconsistent with the photo."""
    actual = assembly_axis_vectors() if vectors is None else vectors
    expected = {
        "dda_pcb_normal": DDA_PCB_NORMAL,
        "dda_column_axis": DDA_COLUMN_AXIS,
        "dda_socket_mating_axis": DDA_SOCKET_MATING_AXIS,
        "j2_column_axis": J2_COLUMN_AXIS,
        "j2_row1_to_row2": J2_ROW1_TO_ROW2_AXIS,
        "j2_mating_axis": J2_MATING_DIRECTION,
        "j2_solder_tail_axis": J2_SOLDER_TAIL_AXIS,
    }
    return [
        f"{name} must be {target}, derived {actual.get(name)}"
        for name, target in expected.items()
        if actual.get(name) != target
    ]


def dda_projected_bounds(boxes: list[Box]) -> tuple[float, float, float, float]:
    """Return the complete simplified DDA assembly projection in XY."""
    return (
        min(box.xmin for box in boxes),
        max(box.xmax for box in boxes),
        min(box.ymin for box in boxes),
        max(box.ymax for box in boxes),
    )


def dda_pcb_envelope_errors(
    boxes: list[Box],
    blade_bounds: tuple[float, float, float, float],
    margin: float,
) -> list[str]:
    """Enforce the DDA's complete projected envelope inside the blade PCB."""
    dx0, dx1, dy0, dy1 = dda_projected_bounds(boxes)
    bx0, bx1, by0, by1 = blade_bounds
    errors = []
    if dx0 < bx0 + margin:
        errors.append("DDA projected X minimum violates the Compute Blade PCB margin")
    if dx1 > bx1 - margin:
        errors.append("DDA projected X maximum violates the Compute Blade PCB margin")
    if dy0 < by0 + margin:
        errors.append("DDA projected Y minimum extends below the Compute Blade PCB -Y edge")
    if dy1 > by1 - margin:
        errors.append("DDA projected Y maximum violates the Compute Blade PCB +Y margin")
    return errors


def adapter_box(board_bounds: tuple[float, float, float, float]) -> Box:
    xmin, xmax, ymin, ymax = board_bounds
    return Box(
        "adapter_pcb",
        xmin,
        xmax,
        ymin,
        ymax,
        ADAPTER_Z_ABOVE_BLADE_MM,
        ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
    )
