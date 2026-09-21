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


def rotate_box_around_x(box: Box, center_y: float, center_z: float) -> Box:
    """Rotate an axis-aligned box 180 degrees around an X-parallel axis."""
    return Box(
        box.name,
        box.xmin,
        box.xmax,
        2 * center_y - box.ymax,
        2 * center_y - box.ymin,
        2 * center_z - box.zmax,
        2 * center_z - box.zmin,
    )


def dda_boxes(rotation_180: bool) -> list[Box]:
    j2_x, j2_y = relative_j2()
    mating_x = j2_x + J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM
    pcb_face_x = mating_x + DDA.pcb_surface_to_mating_plane
    left_y = j2_y - DDA.first_column_from_left
    # Confirmed top/component-side pin 1 is in the DDA row farther from its
    # top edge. It mates to the TSW physical-pin-1 (upper) row.
    top_z = J2_PIN1_CENTER_Z_MM - DDA_PIN1_TOP_EDGE_OFFSET_MM
    center_y = j2_y + 5 * DDA.row_pitch / 2
    center_z = (J2_PIN1_CENTER_Z_MM + J2_PIN2_CENTER_Z_MM) / 2

    boxes = [
        Box(
            "dda_pcb",
            pcb_face_x,
            pcb_face_x + DDA.pcb_thickness,
            left_y,
            left_y + DDA.pcb_width,
            top_z,
            top_z + DDA.pcb_height,
        ),
        Box(
            "dda_socket",
            mating_x,
            pcb_face_x,
            center_y - DDA.socket_body_length / 2,
            center_y + DDA.socket_body_length / 2,
            top_z + DDA.top_to_socket_near_edge,
            top_z + DDA.top_to_socket_near_edge + DDA.socket_body_depth,
        ),
        Box(
            "dda_gnss_envelope",
            pcb_face_x - DDA.gnss_envelope,
            pcb_face_x,
            left_y,
            left_y + DDA.pcb_width,
            top_z,
            top_z + DDA.pcb_height,
        ),
        Box(
            "dda_battery_rtc_envelope",
            pcb_face_x + DDA.pcb_thickness,
            pcb_face_x + DDA.pcb_thickness + DDA.battery_rtc_envelope,
            left_y,
            left_y + DDA.pcb_width,
            top_z,
            top_z + DDA.pcb_height,
        ),
    ]
    if rotation_180:
        boxes = [rotate_box_around_x(box, center_y, center_z) for box in boxes]
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
            j2_x - 1.77,
            j2_x + J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
            j2_y + J2_HEADER_PLASTIC_Y_BOUNDS_MM[0],
            j2_y + J2_HEADER_PLASTIC_Y_BOUNDS_MM[1],
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM,
            ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM + J2_BODY_HEIGHT_MM,
        ),
        Box(
            "j2_mating_posts",
            j2_x + J2_HEADER_PLASTIC_FACE_LOCAL_X_MM,
            j2_x + J2_POST_TIP_LOCAL_X_MM,
            j2_y - 0.32,
            j2_y + 5 * DDA.row_pitch + 0.32,
            J2_PIN2_CENTER_Z_MM - 0.32,
            J2_PIN1_CENTER_Z_MM + 0.32,
        ),
    ]


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
