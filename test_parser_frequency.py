import unittest

from parser import parse_frequency, parse_prescription_line


class ParserFrequencyTests(unittest.TestCase):
    def test_once_maps_to_single_dose(self) -> None:
        sig = "take 1 tablet once"
        self.assertEqual(parse_frequency(sig), "single dose")

    def test_for_one_dose_maps_to_single_dose(self) -> None:
        sig = "take 1 tablet for one dose"
        self.assertEqual(parse_frequency(sig), "single dose")

    def test_x1_maps_to_single_dose(self) -> None:
        sig = "take 2 tablets x1"
        self.assertEqual(parse_frequency(sig), "single dose")

    def test_single_dose_phrase_maps_to_single_dose(self) -> None:
        sig = "take 1 tablet single dose"
        self.assertEqual(parse_frequency(sig), "single dose")

    def test_no_schedule_wording_still_fails(self) -> None:
        self.assertIsNone(parse_frequency("take 1 tablet by mouth"))
        with self.assertRaisesRegex(ValueError, "Missing usable SIG frequency"):
            parse_prescription_line(
                "Ibuprofen 200 mg - take 1 tablet by mouth (qty 30)"
            )


if __name__ == "__main__":
    unittest.main()