#!/usr/bin/env python3
"""Single-source mechanical and PCB configuration for the adapter."""

from __future__ import annotations

from dataclasses import dataclass


# KiCad board coordinates. Positive X is the Compute Blade's USB-C/right side.
PITCH_MM = 2.54
J1_ORIGIN_MM = (100.0, 60.16)
J2_CENTERLINE_OFFSET_MM = 10.0
J2_ORIGIN_MM = (J1_ORIGIN_MM[0] + J2_CENTERLINE_OFFSET_MM, J1_ORIGIN_MM[1])

# The official KiCad horizontal-header footprint points its mating pins toward
# local +X. Zero degrees therefore points the DDA toward board/global +X.
J2_FOOTPRINT_ROTATION_DEG = 0.0

# This is intentionally independent of electrical pin numbering. False is the
# default assembled orientation; True rotates the DDA envelope 180 degrees
# around J2's +X mating axis for an explicit alternative geometry check.
DDA_ROTATION_180 = False

BOARD_THICKNESS_MM = 0.8
SIGNAL_TRACE_WIDTH_MM = 0.25
POWER_TRACE_WIDTH_MM = 0.50

# Standard KiCad 10.0.5 footprint/model identifiers.
J1_FOOTPRINT = "Connector_PinSocket_2.54mm:PinSocket_2x05_P2.54mm_Vertical"
J2_FOOTPRINT = "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Horizontal"
J1_MODEL = "${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_2x05_P2.54mm_Vertical.step"
J2_MODEL = "${KICAD10_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_2x06_P2.54mm_Horizontal.step"
J1_CANDIDATE_PART = "Samtec SLW-105-01-G-D"
J2_CANDIDATE_PART = "Samtec TSW-106-08-G-D-RA"

# Physically measured Compute Blade v1.0-mk4 extension-header dimensions.
COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM = 2.5
COMPUTE_BLADE_HEADER_PIN_TIP_MM = 9.0
COMPUTE_BLADE_EXPOSED_POST_MM = 6.5

# Manufacturer-controlled dimensions from the Samtec SLW series print.
J1_SOCKET_BODY_HEIGHT_MM = 4.572  # 0.180 inch
J1_INSERTION_DEPTH_MIN_MM = 2.16  # 0.085 inch
J1_INSERTION_DEPTH_MAX_MM = 2.92  # 0.115 inch

# A possible non-bottoming gap is kept separate from the nominal stack.
J1_SEATING_GAP_MM = 0.0
J1_NOMINAL_STACK_HEIGHT_MM = (
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM + J1_SOCKET_BODY_HEIGHT_MM
)
ADAPTER_Z_ABOVE_BLADE_MM = J1_NOMINAL_STACK_HEIGHT_MM + J1_SEATING_GAP_MM

# Manufacturer-controlled dimensions from the Samtec TSW series print for
# TSW-106-08-G-D-RA. The drawing identifies pin 1 as the upper RA mating row.
J2_MATING_POST_LENGTH_MM = 5.842  # 0.230 inch nominal
J2_BODY_HEIGHT_MM = 5.56  # 0.219 inch reference
J2_PIN1_CENTER_BELOW_BODY_TOP_MM = 1.0  # 0.040 inch reference
J2_PIN1_IS_UPPER_MATING_ROW = True

# User-defined acceptance requirement. The DDA socket is physically known to
# accept the Compute Blade's full 6.5 mm exposed post. Strong seating is deemed
# acceptable when no more than 3.1 mm remains exposed: 6.5 - 3.1 = 3.4 mm.
DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM = 3.1
DDA_MIN_ACCEPTABLE_INSERTION_MM = 3.40
J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM = (
    round(J2_MATING_POST_LENGTH_MM - DDA_MIN_ACCEPTABLE_INSERTION_MM, 3)
)

# The standard KiCad horizontal-header model has its plastic mating face here.
# The exact TSW post then projects in local +X by J2_MATING_POST_LENGTH_MM.
J2_HEADER_PLASTIC_FACE_LOCAL_X_MM = 6.69
J2_POST_TIP_LOCAL_X_MM = (
    J2_HEADER_PLASTIC_FACE_LOCAL_X_MM + J2_MATING_POST_LENGTH_MM
)
J2_DDA_SOCKET_MATING_FACE_LOCAL_X_MM = (
    J2_POST_TIP_LOCAL_X_MM - DDA_MIN_ACCEPTABLE_INSERTION_MM
)


@dataclass(frozen=True)
class DdaDimensions:
    pcb_width: float = 16.5
    pcb_height: float = 22.5
    pcb_thickness: float = 1.7
    socket_body_length: float = 15.6
    socket_body_depth: float = 5.0
    top_to_socket_near_edge: float = 2.5
    top_to_row1: float = 3.5
    row_pitch: float = 2.54
    first_column_from_left: float = 1.90
    pcb_surface_to_mating_plane: float = 8.3
    battery_rtc_envelope: float = 4.75
    gnss_envelope: float = 4.0

    @property
    def top_to_row2(self) -> float:
        return self.top_to_row1 + self.row_pitch


DDA = DdaDimensions()

# Simplified assembly frame, relative to J1 pin 1. The adapter is parallel to
# the blade XY plane. J2 mates along +X and the upright DDA lies in a YZ plane.
# The confirmed DDA top/component-side view has physical pin 1 at bottom-left;
# from the underside it is bottom-right. Therefore DDA physical pin 1 is the
# geometric row farther from the measured top PCB edge (6.04 mm), and it mates
# to the TSW's upper physical-pin-1 row. Pin numbering is never inferred from
# this geometry.
DDA_PIN1_TOP_SIDE_POSITION = "bottom-left"
DDA_PIN1_UNDERSIDE_POSITION = "bottom-right"
DDA_PIN1_TOP_EDGE_OFFSET_MM = DDA.top_to_row2
J2_PIN1_CENTER_Z_MM = (
    ADAPTER_Z_ABOVE_BLADE_MM
    + BOARD_THICKNESS_MM
    + J2_BODY_HEIGHT_MM
    - J2_PIN1_CENTER_BELOW_BODY_TOP_MM
)
J2_PIN2_CENTER_Z_MM = J2_PIN1_CENTER_Z_MM - PITCH_MM

# J3 is the Compute Blade extension-header product in the pinned official STEP.
# Its placement and +X reference direction are parsed and checked in CI.
COMPUTE_BLADE_STEP_J3_ANCHOR_MM = (133.07507717394, 18.325064806914, 0.0)
COMPUTE_BLADE_STEP_J3_REF_DIRECTION = (1.0, 0.0, 0.0)

# Conservative validation envelopes. These are deliberately kept separate
# from the upstream CAD hashes: they define the documented alignment from the
# extension-port frame into the large official assemblies.
BLADE_PCB_ENVELOPE = (-140.0, 0.0, -45.0, 45.0, -1.6, 0.0)
BLADE_PORT_KEEPIN = (-4.5, 4.5, -8.0, 14.0, -2.0, 16.0)
NEARBY_BLADE_COMPONENT_KEEP_OUTS = (
    (-22.0, -4.5, -18.0, 18.0, 0.0, 10.5),
)

# The official half-body mesh is 46.5 mm high. A 1.5 mm margin is reserved at
# each end, yielding the conservative usable Z interval below.
BLADERUNNER_CLEARANCE_Z = (-1.5, 45.0)
BLADERUNNER_CLEARANCE_Y = (-42.0, 42.0)
