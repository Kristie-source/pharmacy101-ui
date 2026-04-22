import unittest

from parser import parse_prescription_line


class StructurePatternLayerTests(unittest.TestCase):
    def _parse(self, sig: str, qty: int = 30):
        return parse_prescription_line(f"Ibuprofen 200 mg - {sig} (qty {qty})")

    def test_single_dose_pattern(self) -> None:
        parsed = self._parse("take 1 tablet once", qty=1)
        self.assertEqual(parsed.structure_pattern, "single_dose")
        self.assertTrue(parsed.structure_complete)

    def test_fixed_duration_scheduled_pattern(self) -> None:
        parsed = self._parse("take 1 tablet twice daily for 7 days", qty=14)
        self.assertEqual(parsed.structure_pattern, "fixed_duration_scheduled")
        self.assertTrue(parsed.structure_complete)

    def test_ongoing_scheduled_pattern(self) -> None:
        parsed = self._parse("take 1 tablet daily", qty=30)
        self.assertEqual(parsed.structure_pattern, "ongoing_scheduled")
        self.assertTrue(parsed.structure_complete)

    def test_prn_bounded_pattern(self) -> None:
        parsed = self._parse("take 1 tablet as needed every 8 hours max 3 tablets daily", qty=30)
        self.assertEqual(parsed.structure_pattern, "prn_bounded")
        self.assertTrue(parsed.structure_complete)

    def test_prn_unbounded_pattern(self) -> None:
        parsed = self._parse("take 1 tablet as needed", qty=30)
        self.assertEqual(parsed.structure_pattern, "prn_unbounded")
        self.assertFalse(parsed.structure_complete)
        self.assertIn("prn_bounds", parsed.structure_missing)

    def test_episode_based_prn_pattern(self) -> None:
        parsed = self._parse("take 1 tablet as needed at onset every 8 hours max 2 doses", qty=10)
        self.assertEqual(parsed.structure_pattern, "episode_based_prn")
        self.assertTrue(parsed.structure_complete)

    def test_taper_pattern(self) -> None:
        parsed = self._parse("take 2 tablets daily for 3 days then 1 tablet daily for 3 days", qty=9)
        self.assertEqual(parsed.structure_pattern, "taper")
        self.assertTrue(parsed.structure_complete)

    def test_weekly_variable_day_pattern(self) -> None:
        parsed = self._parse("take 1 tablet on monday and thursday", qty=8)
        self.assertEqual(parsed.structure_pattern, "weekly_variable_day")
        self.assertTrue(parsed.structure_complete)


if __name__ == "__main__":
    unittest.main()