#!/usr/bin/env python3
"""Regression tests for the measured DDA collision model."""

import unittest

from design_config import BLADERUNNER_CLEARANCE_Z, DDA
from mechanical_geometry import dda_boxes, relative_j2


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

    def test_rotated_alternative_is_distinct_and_currently_rejected(self):
        default_pcb = next(box for box in dda_boxes(False) if box.name == "dda_pcb")
        rotated_pcb = next(box for box in dda_boxes(True) if box.name == "dda_pcb")
        self.assertNotEqual((default_pcb.zmin, default_pcb.zmax), (rotated_pcb.zmin, rotated_pcb.zmax))
        self.assertLess(rotated_pcb.zmin, BLADERUNNER_CLEARANCE_Z[0])


if __name__ == "__main__":
    unittest.main()
