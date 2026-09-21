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
