#!/usr/bin/env python3
"""Single authoritative electrical-placement and mechanical-stack configuration."""

from __future__ import annotations

from dataclasses import dataclass


# Assembly coordinates are those of the official Compute Blade STEP:
# X = blade long axis, Y = blade width, Z = outward PCB normal.
PITCH_MM = 2.54
BOARD_THICKNESS_MM = 1.0
SIGNAL_TRACE_WIDTH_MM = 0.25
POWER_TRACE_WIDTH_MM = 0.50

# J1 pin 1 is the official STEP J3 anchor. KiCad coordinates are translated
# into that frame by subtracting this board-space origin.
J1_ORIGIN_MM = (100.0, 60.16)

# The approved DDA placement is expressed in the official STEP frame. The
# physical pin-1 center is the leftmost column in the row farther from the DDA
# top edge: (160 + 1.90, 19.5 + 6.04) mm.
DDA_TARGET_BOUNDS_STEP_MM = (160.0, 176.5, 19.5, 42.0)
COMPUTE_BLADE_STEP_J3_ANCHOR_MM = (133.07507717394, 18.325064806914, 0.0)
J2_PIN1_STEP_MM = (
    DDA_TARGET_BOUNDS_STEP_MM[0] + 1.90,
    DDA_TARGET_BOUNDS_STEP_MM[2] + 6.04,
)
J2_ORIGIN_MM = (
    J1_ORIGIN_MM[0] + J2_PIN1_STEP_MM[0] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
    J1_ORIGIN_MM[1] + J2_PIN1_STEP_MM[1] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
)
J2_CENTERLINE_OFFSET_MM = J2_ORIGIN_MM[0] - J1_ORIGIN_MM[0]

# Compact interposer outline. The DDA itself overhangs this board while staying
# inside the Compute Blade footprint.
BOARD_BOUNDS_RELATIVE_J1_MM = (-5.0, 44.0, -3.0, 13.0)
# The pathfinder may explore a larger virtual field, but generated copper is
# asserted to remain inside the physical outline before the board is written.
ROUTING_BOUNDS_RELATIVE_J1_MM = (-5.0, 44.0, -10.0, 20.0)
DDA_PCB_ENVELOPE_MARGIN_MM = 0.5

# The project-local MTLW footprint uses local +Y for successive connector
# columns and local +X from odd to even pins. +90 degrees maps columns to global
# +X and the odd-to-even row vector to global -Y.
J2_FOOTPRINT_ROTATION_DEG = 90.0

# Parallel-DDA orientation contract. Local DDA X/Y/Z map directly to assembly
# X/Y/Z. The GNSS face is +Z; the socket/battery face and mating direction are
# -Z toward the adapter and Compute Blade.
DDA_COLUMN_AXIS = (1.0, 0.0, 0.0)
DDA_TOP_TO_BOTTOM_AXIS = (0.0, 1.0, 0.0)
DDA_PCB_NORMAL = (0.0, 0.0, 1.0)
DDA_SOCKET_MATING_AXIS = (0.0, 0.0, -1.0)
J2_COLUMN_AXIS = (1.0, 0.0, 0.0)
J2_ROW1_TO_ROW2_AXIS = (0.0, -1.0, 0.0)
J2_MATING_DIRECTION = (0.0, 0.0, 1.0)
J2_SOLDER_TAIL_AXIS = (0.0, 0.0, -1.0)
DDA_ASSEMBLY_BASIS = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
DDA_ROTATION_180 = False

# Exact manufacturer part selections. Footprints are project-local,
# dimension-driven implementations of the Samtec recommended through-hole
# patterns with explicit fab/courtyard data.
J1_FOOTPRINT = "Adapter:Samtec_HLE-105-02-L-DV-PE-BE"
J2_FOOTPRINT = "Adapter:Samtec_MTLW-106-05-G-D-140"
J1_MODEL = "${KIPRJMOD}/../mechanical/generated/j1_hle_105_02_l_dv_pe_be.step"
J2_MODEL = "${KIPRJMOD}/../mechanical/generated/j2_mtlw_106_05_g_d_140.step"
J1_CANDIDATE_PART = "Samtec HLE-105-02-L-DV-PE-BE"
J2_CANDIDATE_PART = "Samtec MTLW-106-05-G-D-140"
J2_USES_DESIGNATED_MATING_END = True

# Physically measured Compute Blade extension-header dimensions.
COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM = 2.5
COMPUTE_BLADE_HEADER_PIN_TIP_MM = 9.0
COMPUTE_BLADE_EXPOSED_POST_MM = 6.5

# HLE-105-02-L-DV-PE-BE manufacturer geometry. Bottom entry requires at least
# 2.59 mm of post reach plus the host-board thickness. The housing is open/pass
# through, so the remaining Compute Blade post cannot bottom in a closed bore.
J1_SOCKET_BODY_HEIGHT_MM = 3.66
J1_BOTTOM_ENTRY_CONTACT_MIN_MM = 2.59
J1_INSERTION_DEPTH_MIN_MM = J1_BOTTOM_ENTRY_CONTACT_MIN_MM + BOARD_THICKNESS_MM
J1_INSERTION_DEPTH_MAX_MM = COMPUTE_BLADE_EXPOSED_POST_MM
J1_SEATING_GAP_MM = 0.0
J1_NOMINAL_STACK_HEIGHT_MM = COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM
ADAPTER_Z_ABOVE_BLADE_MM = J1_NOMINAL_STACK_HEIGHT_MM + J1_SEATING_GAP_MM
J1_BODY_Z_MIN_MM = ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM
J1_BODY_Z_MAX_MM = J1_BODY_Z_MIN_MM + J1_SOCKET_BODY_HEIGHT_MM

# Conventional MTLW-106-05-G-D-140 manufacturer geometry. The -140 dimension
# is the designated, gold-plated mating post; the opposite end is the solder
# tail. The body sits conventionally on the adapter's outward/top surface.
J2_OAL_MM = 8.510
J2_BODY_HEIGHT_MM = 1.520
J2_MATING_POST_LENGTH_MM = 3.556  # -140 inches converted to millimetres
J2_SOLDER_TAIL_LENGTH_MM = J2_OAL_MM - J2_BODY_HEIGHT_MM - J2_MATING_POST_LENGTH_MM
J2_LOWER_POST_LENGTH_MM = J2_SOLDER_TAIL_LENGTH_MM
J2_MIN_SOLDER_PROTRUSION_BELOW_PCB_MM = 0.8
J2_BODY_PLAN_MM = (15.24, 5.03)

# User-defined DDA engagement requirement.
DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM = 3.1
DDA_MIN_ACCEPTABLE_INSERTION_MM = 3.40
J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM = round(
    J2_MATING_POST_LENGTH_MM - DDA_MIN_ACCEPTABLE_INSERTION_MM, 3
)

# The insulator sits on the adapter top in the manufacturer's normal mounting
# orientation. The designated mating post points +Z into the DDA socket.
J2_BODY_Z_MIN_MM = ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM
J2_BODY_Z_MAX_MM = J2_BODY_Z_MIN_MM + J2_BODY_HEIGHT_MM
J2_LOWER_TIP_Z_MM = J2_BODY_Z_MIN_MM - J2_LOWER_POST_LENGTH_MM
J2_UPPER_TIP_Z_MM = J2_BODY_Z_MAX_MM + J2_MATING_POST_LENGTH_MM
J2_DDA_SOCKET_MATING_FACE_Z_MM = J2_UPPER_TIP_Z_MM - DDA_MIN_ACCEPTABLE_INSERTION_MM


@dataclass(frozen=True)
class DdaDimensions:
    pcb_width: float = 16.5
    pcb_height: float = 22.5
    pcb_thickness: float = 1.6
    socket_body_length: float = 15.6
    socket_body_depth: float = 5.0
    top_to_socket_near_edge: float = 2.5
    top_to_row1: float = 3.5
    row_pitch: float = 2.54
    first_column_from_left: float = 1.90
    pcb_surface_to_mating_plane: float = 8.3
    # Total socket-side PCB surface to GNSS top, INCLUDING the 1.6 mm PCB.
    socket_side_surface_to_gnss_top: float = 4.0
    gnss_projection_above_opposite_surface: float = 2.4
    battery_rtc_inward_projection: float = 4.75

    @property
    def top_to_row2(self) -> float:
        return self.top_to_row1 + self.row_pitch

    @property
    def mating_face_to_gnss_top(self) -> float:
        return self.pcb_surface_to_mating_plane + self.socket_side_surface_to_gnss_top


DDA = DdaDimensions()
DDA_PIN1_TOP_SIDE_POSITION = "bottom-left"
DDA_PIN1_UNDERSIDE_POSITION = "bottom-right"
DDA_PIN1_TOP_EDGE_OFFSET_MM = DDA.top_to_row2

# Derived approved Z stack.
DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM = (
    J2_DDA_SOCKET_MATING_FACE_Z_MM + DDA.pcb_surface_to_mating_plane
)
DDA_OPPOSITE_PCB_SURFACE_Z_MM = DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM + DDA.pcb_thickness
DDA_GNSS_TOP_Z_MM = (
    DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM + DDA.socket_side_surface_to_gnss_top
)
DDA_BATTERY_INWARD_Z_MIN_MM = (
    DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM - DDA.battery_rtc_inward_projection
)

# Official upstream Compute Blade CAD anchors/bounds.
COMPUTE_BLADE_STEP_J3_REF_DIRECTION = (1.0, 0.0, 0.0)
COMPUTE_BLADE_STEP_BOUNDS_MM = (
    -0.500079991582, 250.016, 0.006, 42.505, -5.899999202452, 14.1,
)
COMPUTE_BLADE_PCB_BOUNDS_MM = (
    0.006, 250.016, 0.006, 42.505, -1.54631898, 0.0,
)
COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM = (
    COMPUTE_BLADE_PCB_BOUNDS_MM[0] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
    COMPUTE_BLADE_PCB_BOUNDS_MM[1] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[0],
    COMPUTE_BLADE_PCB_BOUNDS_MM[2] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
    COMPUTE_BLADE_PCB_BOUNDS_MM[3] - COMPUTE_BLADE_STEP_J3_ANCHOR_MM[1],
)

# Actual per-blade clearance derived from the retention-slit edges. Do not
# substitute slit centerline pitch or subtract the blade PCB thickness again.
BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM = 19.9317
BLADERUNNER_Z_SAFETY_MARGIN_MM = 1.0
BLADERUNNER_PER_BLADE_DESIGN_MAX_MM = (
    BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - BLADERUNNER_Z_SAFETY_MARGIN_MM
)

# The approved candidate was selected from the official STEP as clear of the
# J3-area component keepout. Exact B-Rep collision is additionally required in
# the assembly-generation CI stage.
BLADE_PCB_ENVELOPE = (-140.0, 116.9409, -18.3191, 24.1799, -1.55, 0.0)
NEARBY_BLADE_COMPONENT_KEEP_OUTS = (
    (-22.0, -4.5, -18.0, 18.0, 0.0, 10.5),
)
