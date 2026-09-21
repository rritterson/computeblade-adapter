#!/usr/bin/env python3
"""Focused regression tests for the independent connectivity rules."""

import copy
import unittest

import verify_connectivity as verifier


class ConnectivityVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = verifier.schematic_pin_nets(verifier.SCH_PATH)

    def test_generated_schematic_passes(self):
        self.assertEqual([], verifier.validate(self.good, "test"))

    def test_generated_pcb_routes_reach_transformed_pads(self):
        self.assertEqual([], verifier.validate_pcb_routing(verifier.PCB_PATH))

    def test_bottom_j1_uses_explicit_standard_socket_coordinates(self):
        tree = verifier.parse_sexpr(verifier.PCB_PATH.read_text(encoding="utf-8"))
        j1 = next(
            footprint for footprint in verifier.children(tree, "footprint")
            if verifier.properties(footprint).get("Reference") == "J1"
        )
        pad2 = next(pad for pad in verifier.children(j1, "pad") if pad[1] == "2")
        self.assertEqual((97.46, 60.16), verifier.transformed_pad(j1, pad2))

    def test_j2_is_explicit_right_angle_footprint_pointing_plus_x(self):
        tree = verifier.parse_sexpr(verifier.PCB_PATH.read_text(encoding="utf-8"))
        j2 = next(
            footprint for footprint in verifier.children(tree, "footprint")
            if verifier.properties(footprint).get("Reference") == "J2"
        )
        self.assertEqual(
            "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Horizontal",
            j2[1],
        )
        self.assertEqual("0", verifier.child(j2, "at")[3])

    def test_power_short_is_rejected(self):
        bad = copy.deepcopy(self.good)
        bad["J1.1"] = bad["J2.1"] = bad["J1.2"]
        errors = verifier.validate(bad, "test")
        self.assertTrue(any("shorted" in error or "improperly merges" in error for error in errors))

    def test_gpio_to_power_is_rejected(self):
        bad = copy.deepcopy(self.good)
        bad["J1.3"] = bad["J2.3"] = bad["J1.1"]
        errors = verifier.validate(bad, "test")
        self.assertTrue(any("GPIO pin" in error for error in errors))

    def test_j2_pin_11_must_be_nc(self):
        bad = copy.deepcopy(self.good)
        bad["J2.11"] = "RTC_INT"
        errors = verifier.validate(bad, "test")
        self.assertTrue(any("J2.11 must be NC" in error for error in errors))

    def test_pps_three_pin_net_is_required(self):
        bad = copy.deepcopy(self.good)
        bad["J2.12"] = "WRONG"
        errors = verifier.validate(bad, "test")
        self.assertTrue(any("J1.7" in error and "J2.12" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
