#!/usr/bin/env python3
"""Regression tests for the measured DDA collision model."""

import unittest

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_CLEARANCE_Z,
    COMPUTE_BLADE_EXPOSED_POST_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    DDA,
    DDA_PIN1_TOP_EDGE_OFFSET_MM,
    DDA_PIN1_TOP_SIDE_POSITION,
    DDA_PIN1_UNDERSIDE_POSITION,
    J1_INSERTION_DEPTH_MIN_MM,
    J1_NOMINAL_STACK_HEIGHT_MM,
    J1_SEATING_GAP_MM,
    J1_SOCKET_BODY_HEIGHT_MM,
    J2_DDA_INSERTION_DEPTH_ASSUMPTION_MM,
    J2_MATING_POST_LENGTH_MM,
    J2_PIN1_CENTER_Z_MM,
    J2_PIN1_IS_UPPER_MATING_ROW,
    J2_PIN2_CENTER_Z_MM,
)
from mechanical_geometry import connector_boxes, dda_boxes, relative_j2


class MechanicalGeometryTests(unittest.TestCase):
    def test_supplied_dda_dimensions_are_preserved(self):
        pcb = next(box for box in dda_boxes(False) if box.name == "dda_pcb")
        self.assertAlmostEqual(DDA.pcb_thickness, pcb.size[0])
        self.assertAlmostEqual(DDA.pcb_width, pcb.size[1])
        self.assertAlmostEqual(DDA.pcb_height, pcb.size[2])
        self.assertAlmostEqual(6.04, DDA.top_to_row2)

    def test_default_dda_extends_right_and_fits_z_envelope(self):
        j2_x, _ = relative_j2()
        for box in dda_boxes(False):
            self.assertGreater(box.xmin, j2_x)
            self.assertGreaterEqual(box.zmin, BLADERUNNER_CLEARANCE_Z[0])
            self.assertLessEqual(box.zmax, BLADERUNNER_CLEARANCE_Z[1])

    def test_measured_compute_blade_post_meets_slw_minimum_insertion(self):
        self.assertAlmostEqual(
            COMPUTE_BLADE_EXPOSED_POST_MM,
            COMPUTE_BLADE_HEADER_PIN_TIP_MM - COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
        )
        self.assertGreaterEqual(COMPUTE_BLADE_EXPOSED_POST_MM, J1_INSERTION_DEPTH_MIN_MM)

    def test_nominal_j1_stack_keeps_seating_gap_explicit(self):
        self.assertAlmostEqual(
            J1_NOMINAL_STACK_HEIGHT_MM,
            COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM + J1_SOCKET_BODY_HEIGHT_MM,
        )
        self.assertAlmostEqual(
            ADAPTER_Z_ABOVE_BLADE_MM,
            J1_NOMINAL_STACK_HEIGHT_MM + J1_SEATING_GAP_MM,
        )
        self.assertEqual(0.0, J1_SEATING_GAP_MM)

    def test_confirmed_dda_pin1_maps_to_tsw_physical_pin1(self):
        self.assertTrue(J2_PIN1_IS_UPPER_MATING_ROW)
        self.assertGreater(J2_PIN1_CENTER_Z_MM, J2_PIN2_CENTER_Z_MM)
        self.assertEqual("bottom-left", DDA_PIN1_TOP_SIDE_POSITION)
        self.assertEqual("bottom-right", DDA_PIN1_UNDERSIDE_POSITION)
        self.assertAlmostEqual(DDA.top_to_row2, DDA_PIN1_TOP_EDGE_OFFSET_MM)
        pcb = next(box for box in dda_boxes(False) if box.name == "dda_pcb")
        self.assertAlmostEqual(J2_PIN1_CENTER_Z_MM, pcb.zmin + DDA_PIN1_TOP_EDGE_OFFSET_MM)

    def test_tsw_post_insertion_and_simplified_body_clearance(self):
        socket = next(box for box in dda_boxes(False) if box.name == "dda_socket")
        body = next(box for box in connector_boxes() if box.name == "j2_right_angle_body")
        posts = next(box for box in connector_boxes() if box.name == "j2_mating_posts")
        insertion = min(posts.xmax, socket.xmax) - max(posts.xmin, socket.xmin)
        self.assertAlmostEqual(J2_DDA_INSERTION_DEPTH_ASSUMPTION_MM, insertion)
        self.assertGreaterEqual(J2_MATING_POST_LENGTH_MM, insertion)
        self.assertFalse(socket.overlaps(body))

    def test_rotated_alternative_is_distinct_and_currently_rejected(self):
        default_pcb = next(box for box in dda_boxes(False) if box.name == "dda_pcb")
        rotated_pcb = next(box for box in dda_boxes(True) if box.name == "dda_pcb")
        self.assertNotEqual((default_pcb.zmin, default_pcb.zmax), (rotated_pcb.zmin, rotated_pcb.zmax))
        self.assertLess(rotated_pcb.zmin, BLADERUNNER_CLEARANCE_Z[0])


if __name__ == "__main__":
    unittest.main()
