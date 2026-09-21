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
J1_SOCKET_BODY_HEIGHT_MM = 4.572  # Samtec's published 0.180 inch body height.
J2_MATING_POST_LENGTH_MM = 5.842  # Samtec's published 0.230 inch post length.


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
ADAPTER_Z_ABOVE_BLADE_MM = 8.5
J2_MATING_FACE_LOCAL_X_MM = 12.58
J2_ROW1_CENTER_Z_MM = ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM + 4.0

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
