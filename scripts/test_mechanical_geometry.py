#!/usr/bin/env python3
"""Regression tests for the measured DDA collision model."""

import unittest

from design_config import (
    ADAPTER_Z_ABOVE_BLADE_MM,
    BLADERUNNER_CLEARANCE_Z,
    COMPUTE_BLADE_EXPOSED_POST_MM,
    COMPUTE_BLADE_HEADER_PIN_TIP_MM,
    COMPUTE_BLADE_HEADER_PLASTIC_TOP_MM,
    COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM,
    DDA,
    DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM,
    DDA_MIN_ACCEPTABLE_INSERTION_MM,
    DDA_PCB_ENVELOPE_MARGIN_MM,
    DDA_PIN1_TOP_EDGE_OFFSET_MM,
    DDA_PIN1_TOP_SIDE_POSITION,
    DDA_PIN1_UNDERSIDE_POSITION,
    DDA_ASSEMBLY_BASIS,
    J1_INSERTION_DEPTH_MIN_MM,
    J1_NOMINAL_STACK_HEIGHT_MM,
    J1_SEATING_GAP_MM,
    J1_SOCKET_BODY_HEIGHT_MM,
    J2_MATING_POST_LENGTH_MM,
    J2_MATING_DIRECTION,
    J2_PIN1_CENTER_Z_MM,
    J2_PIN1_IS_UPPER_MATING_ROW,
    J2_PIN2_CENTER_Z_MM,
    J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
    MAX_ASSEMBLED_Z_DEPTH_MM,
    DDA_PLACEMENT_Y_SIGN,
)
from mechanical_geometry import (
    Box,
    assembly_axis_vectors,
    axis_constraint_errors,
    connector_boxes,
    dda_boxes,
    dda_pcb_envelope_errors,
    relative_j2,
)


class MechanicalGeometryTests(unittest.TestCase):
    def test_supplied_dda_dimensions_are_preserved(self):
        pcb = next(box for box in dda_boxes(False) if box.name == "dda_pcb")
        self.assertAlmostEqual(DDA.pcb_width, pcb.size[0])
        self.assertAlmostEqual(DDA.pcb_thickness, pcb.size[1])
        self.assertAlmostEqual(DDA.pcb_height, pcb.size[2])
        self.assertAlmostEqual(6.04, DDA.top_to_row2)

    def test_default_dda_extends_toward_positive_y_and_fits_z_envelope(self):
        _, j2_y = relative_j2()
        for box in dda_boxes(False):
            self.assertGreater(box.ymin, j2_y)
            self.assertGreaterEqual(box.zmin, BLADERUNNER_CLEARANCE_Z[0])
            self.assertLessEqual(box.zmax, BLADERUNNER_CLEARANCE_Z[1])

    def test_axis_derived_transform_matches_authoritative_photo_constraints(self):
        self.assertEqual(
            ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            DDA_ASSEMBLY_BASIS,
        )
        self.assertEqual(1, DDA_PLACEMENT_Y_SIGN)
        self.assertEqual((0.0, 1.0, 0.0), J2_MATING_DIRECTION)
        self.assertEqual(
            {
                "dda_pcb_normal": (0.0, 1.0, 0.0),
                "dda_column_axis": (-1.0, 0.0, 0.0),
                "dda_socket_mating_axis": (0.0, 1.0, 0.0),
                "j2_column_axis": (-1.0, 0.0, 0.0),
                "j2_row1_to_row2": (0.0, 0.0, -1.0),
                "j2_mating_axis": (0.0, 1.0, 0.0),
                "j2_solder_tail_axis": (0.0, 0.0, 1.0),
            },
            assembly_axis_vectors(),
        )
        self.assertEqual([], axis_constraint_errors())

    def test_wrong_axis_and_wrong_direction_mutations_are_rejected(self):
        vectors = assembly_axis_vectors()
        vectors["dda_pcb_normal"] = (0.0, 0.0, 1.0)
        vectors["dda_socket_mating_axis"] = (0.0, -1.0, 0.0)
        vectors["j2_row1_to_row2"] = (0.0, -1.0, 0.0)
        errors = axis_constraint_errors(vectors)
        self.assertEqual(3, len(errors))
        self.assertTrue(any("dda_pcb_normal" in error for error in errors))
        self.assertTrue(any("dda_socket_mating_axis" in error for error in errors))
        self.assertTrue(any("j2_row1_to_row2" in error for error in errors))

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

    def test_dda_minimum_insertion_requirement_and_tsw_margin(self):
        self.assertEqual(3.40, DDA_MIN_ACCEPTABLE_INSERTION_MM)
        self.assertAlmostEqual(
            DDA_MIN_ACCEPTABLE_INSERTION_MM,
            COMPUTE_BLADE_EXPOSED_POST_MM - DDA_ACCEPTABLE_REMAINING_EXPOSED_POST_MM,
        )
        self.assertGreaterEqual(J2_MATING_POST_LENGTH_MM, DDA_MIN_ACCEPTABLE_INSERTION_MM)
        self.assertAlmostEqual(2.442, J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM)

    def test_tsw_minimum_insertion_and_simplified_body_elbow_clearance(self):
        socket = next(box for box in dda_boxes(False) if box.name == "dda_socket")
        body = next(box for box in connector_boxes() if box.name == "j2_body_elbow_keepout")
        posts = next(box for box in connector_boxes() if box.name == "j2_mating_posts")
        insertion = min(posts.ymax, socket.ymax) - max(posts.ymin, socket.ymin)
        self.assertAlmostEqual(DDA_MIN_ACCEPTABLE_INSERTION_MM, insertion)
        self.assertGreaterEqual(J2_MATING_POST_LENGTH_MM, insertion)
        self.assertFalse(socket.overlaps(body))
        self.assertAlmostEqual(
            J2_POST_LENGTH_MARGIN_AT_MIN_INSERTION_MM,
            socket.ymin - body.ymax,
        )

    def test_complete_dda_projection_fits_official_blade_pcb_with_margin(self):
        self.assertEqual(
            [],
            dda_pcb_envelope_errors(
                dda_boxes(False),
                COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM,
                DDA_PCB_ENVELOPE_MARGIN_MM,
            ),
        )

    def test_negative_y_placement_mutation_fails_pcb_envelope(self):
        _, j2_y = relative_j2()
        flipped = [
            Box(
                box.name,
                box.xmin,
                box.xmax,
                2 * j2_y - box.ymax,
                2 * j2_y - box.ymin,
                box.zmin,
                box.zmax,
            )
            for box in dda_boxes(False)
        ]
        errors = dda_pcb_envelope_errors(
            flipped,
            COMPUTE_BLADE_PCB_BOUNDS_RELATIVE_J3_MM,
            DDA_PCB_ENVELOPE_MARGIN_MM,
        )
        self.assertTrue(any("-Y edge" in error for error in errors))

    def test_corrected_assembly_z_depth_has_regression_limit(self):
        # Official blade z-min is -5.899999 mm; DDA z-max is the assembly max.
        zmin = -5.899999202452
        zmax = max(box.zmax for box in dda_boxes(False))
        self.assertAlmostEqual(34.792, zmax - zmin, places=3)
        self.assertLessEqual(zmax - zmin, MAX_ASSEMBLED_Z_DEPTH_MM)

    def test_rotated_alternative_is_distinct_and_currently_rejected(self):
        default_pcb = next(box for box in dda_boxes(False) if box.name == "dda_pcb")
        rotated_pcb = next(box for box in dda_boxes(True) if box.name == "dda_pcb")
        self.assertNotEqual((default_pcb.zmin, default_pcb.zmax), (rotated_pcb.zmin, rotated_pcb.zmax))
        self.assertLess(rotated_pcb.zmin, BLADERUNNER_CLEARANCE_Z[0])


if __name__ == "__main__":
    unittest.main()
