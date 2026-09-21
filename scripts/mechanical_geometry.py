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
    DDA_PIN1_TOP_EDGE_OFFSET_MM,
    DDA_ROTATION_MATRIX,
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


def rotate_box_around_y(box: Box, center_x: float, center_z: float) -> Box:
    """Rotate an axis-aligned box 180 degrees around the -Y mating axis."""
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
    """Apply the configured DDA rotation matrix and translation to a local box."""
    corners = []
    for x in (box.xmin, box.xmax):
        for y in (box.ymin, box.ymax):
            for z in (box.zmin, box.zmax):
                local = (x, y, z)
                corners.append(
                    tuple(
                        origin[row]
                        + sum(DDA_ROTATION_MATRIX[row][column] * local[column] for column in range(3))
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
    # Footprint local +X maps to global -Y after its -90-degree board rotation.
    mating_y = j2_y - J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM
    left_x = j2_x - DDA.first_column_from_left
    # Confirmed top/component-side pin 1 is in the DDA row farther from its
    # top edge. It mates to the TSW physical-pin-1 (upper) row.
    top_z = J2_PIN1_CENTER_Z_MM - DDA_PIN1_TOP_EDGE_OFFSET_MM
    center_x = j2_x + 5 * DDA.row_pitch / 2
    center_z = (J2_PIN1_CENTER_Z_MM + J2_PIN2_CENTER_Z_MM) / 2

    origin = (left_x, mating_y, top_z)
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
            j2_x + J2_HEADER_PLASTIC_Y_BOUNDS_MM[0],
            j2_x + J2_HEADER_PLASTIC_Y_BOUNDS_MM[1],
            j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
            j2_y + 1.77,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM + J2_BODY_HEIGHT_MM,
        ),
        Box(
            "j2_mating_posts",
            j2_x - 0.32,
            j2_x + 5 * DDA.row_pitch + 0.32,
            j2_y - J2_POST_TIP_LOCAL_X_MM,
            j2_y - J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
            J2_PIN2_CENTER_Z_MM - 0.32,
            J2_PIN1_CENTER_Z_MM + 0.32,
        ),
    ]


def dda_rotation_matrix() -> tuple[tuple[float, float, float], ...]:
    """Return the exact DDA local-to-Compute-Blade rotation used everywhere."""
    return DDA_ROTATION_MATRIX


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
