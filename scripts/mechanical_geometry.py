#!/usr/bin/env python3
"""Conservative assembly solids shared by model generation and validation."""

from __future__ import annotations

from dataclasses import dataclass

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BOARD_THICKNESS_MM,
    DDA,
    J2_MATING_FACE_LOCAL_X_MM,
    J2_ORIGIN_MM,
    J1_ORIGIN_MM,
    J2_ROW1_CENTER_Z_MM,
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
    mating_x = j2_x + J2_MATING_FACE_LOCAL_X_MM
    pcb_face_x = mating_x + DDA.pcb_surface_to_mating_plane
    left_y = j2_y - DDA.first_column_from_left
    top_z = J2_ROW1_CENTER_Z_MM - DDA.top_to_row1
    center_y = j2_y + 5 * DDA.row_pitch / 2
    center_z = J2_ROW1_CENTER_Z_MM + DDA.row_pitch / 2

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
        Box("j1_socket", -4.31, 1.77, -1.77, 11.93, 0.0, ADAPTER_Z_ABOVE_BLADE_MM),
        Box(
            "j2_right_angle_header",
            j2_x - 1.77,
            j2_x + 13.09,
            j2_y - 1.77,
            j2_y + 14.47,
            ADAPTER_Z_ABOVE_BLADE_MM,
            J2_ROW1_CENTER_Z_MM + DDA.row_pitch + 1.5,
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

