#!/usr/bin/env python3
"""Regression tests for the approved parallel-DDA architecture."""

import unittest

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_PER_BLADE_DESIGN_MAX_MM,
    BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM,
    BLADERUNNER_PHYSICAL_CLEARANCE_MIN_MM,
    BLADERUNNER_MARGIN_AFTER_RESERVE_MIN_MM,
    BOARD_THICKNESS_MM,
    COMPUTE_BLADE_EXPOSED_POST_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM,
    DDA,
    DDA_ASSEMBLY_BASIS,
    DDA_GNSS_TOP_Z_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    DDA_OPPOSITE_PCB_SURFACE_Z_MM,
    DDA_PCB_ENVELOPE_MARGIN_MM,
    DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM,
    J1_BOTTOM_ENTRY_CONTACT_MIN_MM,
    J1_INSERTION_DEPTH_MIN_MM,
    J1_SEATING_GAP_CANDIDATES_MM,
    J1_SEATING_GAP_MM,
    J2_DDA_SOCKET_MATING_FACE_Z_MM,
    J2_LOWER_TIP_Z_MM,
    J2_TAIL_CLEARANCE_TO_COMPUTE_BLADE_MIN_MM,
    J2_MATING_POST_LENGTH_MM,
    J2_OAL_MM,
    J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
    J2_USES_DESIGNATED_MATING_END,
    J2_UPPER_TIP_Z_MM,
)
from mechanical_geometry import (
    Box,
    assembly_axis_vectors,
    axis_constraint_errors,
    connector_boxes,
    dda_boxes,
    dda_pcb_envelope_errors,
    dda_projected_bounds,
    evaluate_seating_gap,
)


class MechanicalGeometryTests(unittest.TestCase):
    def test_supplied_dda_dimensions_and_non_double_counted_height(self):
        pcb = next(box for box in dda_boxes() if box.name == "dda_pcb")
        gnss = next(box for box in dda_boxes() if box.name == "dda_gnss_envelope")
        self.assertAlmostEqual(16.5, pcb.size[0])
        self.assertAlmostEqual(22.5, pcb.size[1])
        self.assertAlmostEqual(1.6, pcb.size[2])
        self.assertAlmostEqual(2.4, gnss.size[2])
        self.assertAlmostEqual(4.0, DDA_GNSS_TOP_Z_MM - DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM)
        self.assertAlmostEqual(12.3, DDA.mating_face_to_gnss_top)
        self.assertAlmostEqual(1.6, DDA_OPPOSITE_PCB_SURFACE_Z_MM - DDA_SOCKET_SIDE_PCB_SURFACE_Z_MM)

    def test_parallel_axis_contract(self):
        self.assertEqual(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), DDA_ASSEMBLY_BASIS)
        self.assertEqual(
            {
                "dda_pcb_normal": (0.0, 0.0, 1.0),
                "dda_column_axis": (1.0, 0.0, 0.0),
                "dda_top_to_bottom_axis": (0.0, 1.0, 0.0),
                "dda_socket_mating_axis": (0.0, 0.0, -1.0),
                "j2_column_axis": (1.0, 0.0, 0.0),
                "j2_row1_to_row2": (0.0, -1.0, 0.0),
                "j2_mating_axis": (0.0, 0.0, 1.0),
                "j2_solder_tail_axis": (0.0, 0.0, -1.0),
            },
            assembly_axis_vectors(),
        )
        self.assertEqual([], axis_constraint_errors())

    def test_wrong_orientation_vectors_are_rejected(self):
        vectors = assembly_axis_vectors()
        vectors["dda_pcb_normal"] = (0.0, 1.0, 0.0)
        vectors["dda_socket_mating_axis"] = (0.0, 0.0, 1.0)
        self.assertEqual(2, len(axis_constraint_errors(vectors)))

    def test_hle_bottom_entry_reach_and_open_pass_through(self):
        self.assertAlmostEqual(6.5, COMPUTE_BLADE_HEADER_PIN_TIP_MM - COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM)
        self.assertEqual(COMPUTE_BLADE_EXPOSED_POST_MM, 6.5)
        self.assertAlmostEqual(0.35, J1_SEATING_GAP_MM)
        self.assertAlmostEqual(
            J1_BOTTOM_ENTRY_CONTACT_MIN_MM + BOARD_THICKNESS_MM + J1_SEATING_GAP_MM,
            J1_INSERTION_DEPTH_MIN_MM,
        )
        self.assertGreaterEqual(COMPUTE_BLADE_EXPOSED_POST_MM, J1_INSERTION_DEPTH_MIN_MM)
        self.assertAlmostEqual(2.85, ADAPTER_Z_ABOVE_BLADE_MM)

    def test_conventional_mtlw_geometry_and_insertion(self):
        self.assertTrue(J2_USES_DESIGNATED_MATING_END)
        self.assertAlmostEqual(3.556, J2_MATING_POST_LENGTH_MM)
        self.assertAlmostEqual(8.510, J2_OAL_MM)
        self.assertAlmostEqual(3.400, J2_UPPER_TIP_Z_MM - J2_DDA_SOCKET_MATING_FACE_Z_MM)
        self.assertAlmostEqual(DDA_MIN_ACCEPTABLE_INSERTION_MM, 3.400)
        self.assertAlmostEqual(0.156, J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM)
        self.assertGreaterEqual(J2_LOWER_TIP_Z_MM, J2_TAIL_CLEARANCE_TO_COMPUTE_BLADE_MIN_MM)

    def test_approved_z_stack_and_bladerunner_margins(self):
        self.assertAlmostEqual(5.526, J2_DDA_SOCKET_MATING_FACE_Z_MM)
        self.assertAlmostEqual(17.826, DDA_GNSS_TOP_Z_MM)
        self.assertAlmostEqual(2.1057, BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - DDA_GNSS_TOP_Z_MM)
        self.assertAlmostEqual(1.1057, BLADERUNNER_PER_BLADE_DESIGN_MAX_MM - DDA_GNSS_TOP_Z_MM)
        self.assertGreaterEqual(
            BLADERUNNER_PER_BLADE_PHYSICAL_CLEARANCE_MM - DDA_GNSS_TOP_Z_MM,
            BLADERUNNER_PHYSICAL_CLEARANCE_MIN_MM,
        )
        self.assertGreaterEqual(
            BLADERUNNER_PER_BLADE_DESIGN_MAX_MM - DDA_GNSS_TOP_Z_MM,
            BLADERUNNER_MARGIN_AFTER_RESERVE_MIN_MM,
        )
        self.assertLessEqual(DDA_GNSS_TOP_Z_MM, BLADERUNNER_PER_BLADE_DESIGN_MAX_MM)

    def test_seating_gap_candidates_use_shared_exact_z_chain(self):
        expected = {
            0.30: (2.800, 3.890, 2.610, 0.366, 17.776, 2.1557, 1.1557),
            0.35: (2.850, 3.940, 2.560, 0.416, 17.826, 2.1057, 1.1057),
            0.40: (2.900, 3.990, 2.510, 0.466, 17.876, 2.0557, 1.0557),
        }
        self.assertEqual((0.30, 0.35, 0.40), J1_SEATING_GAP_CANDIDATES_MM)
        for gap, values in expected.items():
            result = evaluate_seating_gap(gap)
            actual = (
                result.adapter_underside_mm,
                result.j1_required_reach_mm,
                result.j1_engagement_surplus_mm,
                result.j2_tail_clearance_mm,
                result.outward_stack_mm,
                result.physical_clearance_mm,
                result.margin_after_reserve_mm,
            )
            for expected_value, actual_value in zip(values, actual):
                self.assertAlmostEqual(expected_value, actual_value)

    def test_dda_xy_bounds_and_keepin(self):
        boxes = dda_boxes()
        self.assertEqual([], dda_pcb_envelope_errors(boxes, COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM, DDA_PCB_ENVELOPE_MARGIN_MM))
        bounds = dda_projected_bounds(boxes)
        self.assertAlmostEqual(16.5, bounds[1] - bounds[0])
        self.assertAlmostEqual(22.5, bounds[3] - bounds[2])

    def test_outward_face_is_gnss_and_inward_face_clears_adapter(self):
        boxes = {box.name: box for box in dda_boxes()}
        self.assertGreater(boxes["dda_gnss_envelope"].zmin, boxes["dda_pcb"].zmin)
        self.assertLess(boxes["dda_battery_rtc_inward_envelope"].zmin, boxes["dda_pcb"].zmin)
        self.assertGreater(boxes["dda_battery_rtc_inward_envelope"].zmin, ADAPTER_Z_ABOVE_BLADE_MM + BOARD_THICKNESS_MM)

    def test_lower_j2_geometry_stays_above_blade_plane(self):
        lower = next(box for box in connector_boxes() if box.name == "j2_lower_posts")
        self.assertAlmostEqual(J2_LOWER_TIP_Z_MM, lower.zmin)
        self.assertGreaterEqual(lower.zmin, J2_TAIL_CLEARANCE_TO_COMPUTE_BLADE_MIN_MM)

    def test_deliberate_excess_height_fails_design_limit(self):
        bad = DDA_GNSS_TOP_Z_MM + 3.0
        self.assertGreater(bad, BLADERUNNER_PER_BLADE_DESIGN_MAX_MM)


if __name__ == "__main__":
    unittest.main()
