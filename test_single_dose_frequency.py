import unittest

from api import PrescriptionInput, analyze
from parser import parse_prescription_line
from structural import detect_structural_issue


class SingleDoseFrequencyTests(unittest.TestCase):
        def test_lisinopril_daily_30_no_issue(self) -> None:
            # Lisinopril 20 mg daily, qty 30: should not be flagged
            result = analyze(
                PrescriptionInput(
                    raw_text="Lisinopril 20 mg - take 1 tablet by mouth daily (qty 30)"
                )
            )
            self.assertTrue(result["status"] == "OK" or result["resolution"] == "🟢 NONE")
            self.assertNotIn("quantity mismatch", str(result).lower())
            self.assertNotIn("course length", str(result).lower())

        def test_metformin_bidx2_60_no_issue(self) -> None:
            # Metformin 500 mg BID, qty 60: should not be flagged
            result = analyze(
                PrescriptionInput(
                    raw_text="Metformin 500 mg - take 1 tablet by mouth twice daily (qty 60)"
                )
            )
            self.assertTrue(result["status"] == "OK" or result["resolution"] == "🟢 NONE")
            self.assertNotIn("quantity mismatch", str(result).lower())
            self.assertNotIn("course length", str(result).lower())

import unittest

from api import PrescriptionInput, analyze
from parser import parse_prescription_line
from structural import detect_structural_issue


class SingleDoseFrequencyTests(unittest.TestCase):
    def test_single_dose_quantity_mismatch(self) -> None:
        # Single-dose, quantity exceeds written dose
        result = analyze(
            PrescriptionInput(
                raw_text="Azithromycin 500 mg - take 2 tablets once (qty 4)"
            )
        )
        self.assertIn("quantity mismatch", result["structural_issue"].lower())
        self.assertIn("single-dose", result["structural_issue"].lower())
        self.assertEqual(result["resolution"], "🔴 HOLD NOW / CHALLENGE")

    def test_taper_pattern_quantity_match(self) -> None:
        # Taper, correct total quantity
        result = analyze(
            PrescriptionInput(
                raw_text="Prednisone 10 mg - take 4 tablets daily for 3 days then 3 tablets daily for 3 days then 2 tablets daily for 3 days then 1 tablet daily for 3 days (qty 30)"
            )
        )
        print("DEBUG: taper match result=", result)
        # If result is OK, no structural_issue key
        if result.get("status") == "OK":
            self.assertEqual(result["resolution"], "🟢 SAFE / NONE")
        else:
            self.assertNotIn("quantity mismatch", result.get("structural_issue", "").lower())

    def test_taper_pattern_quantity_mismatch(self) -> None:
        # Taper, incorrect total quantity
        result = analyze(
            PrescriptionInput(
                raw_text="Prednisone 10 mg - take 4 tablets daily for 3 days then 3 tablets daily for 3 days then 2 tablets daily for 3 days then 1 tablet daily for 3 days (qty 28)"
            )
        )
        self.assertIn("quantity mismatch", result["structural_issue"].lower())
        self.assertIn("taper", result["structural_issue"].lower())
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")

    def test_fixed_duration_quantity_match(self) -> None:
        # Fixed-duration, correct quantity
        result = analyze(
            PrescriptionInput(
                raw_text="Amoxicillin 500 mg - take 1 tablet three times daily for 7 days (qty 21)"
            )
        )
        self.assertNotIn("quantity mismatch", result["structural_issue"].lower())
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")

    def test_fixed_duration_quantity_mismatch(self) -> None:
        # Fixed-duration, incorrect quantity
        result = analyze(
            PrescriptionInput(
                raw_text="Amoxicillin 500 mg - take 1 tablet three times daily for 7 days (qty 18)"
            )
        )
        self.assertIn("quantity mismatch", result["structural_issue"].lower())
        self.assertIn("fixed-duration", result["structural_issue"].lower())
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")

    def test_weekly_variable_day_pattern_no_quantity_mismatch(self) -> None:
        # Weekly/variable-day, should not flag strict daily math
        result = analyze(
            PrescriptionInput(
                raw_text="Alendronate 70 mg - take 1 tablet by mouth every monday (qty 4)"
            )
        )
        # If result is OK, no structural_issue key
        if result.get("status") == "OK":
            self.assertEqual(result["resolution"], "🟢 SAFE / NONE")
        else:
            self.assertNotIn("quantity mismatch", result.get("structural_issue", "").lower())

    def test_fluconazole_one_dose_is_not_missing_frequency(self) -> None:
        parsed = parse_prescription_line(
            "Fluconazole 150 mg - take 1 tablet by mouth for one dose (qty 1)"
        )
        self.assertEqual(parsed.frequency, "single dose")

        structural = detect_structural_issue(
            parsed.drug,
            parsed.sig,
            parsed.quantity,
            parsed.frequency,
        )
        self.assertEqual(structural.structure_assessment, "Structurally complete")
        self.assertEqual(structural.resolution, "🟢 NONE")

        result = analyze(
            PrescriptionInput(
                raw_text="Fluconazole 150 mg - take 1 tablet by mouth for one dose (qty 1)"
            )
        )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")
        self.assertNotIn("missing usable sig frequency", str(result).lower())
        self.assertNotIn("duration missing", str(result).lower())

    def test_take_two_tablets_once_is_valid_single_dose_frequency(self) -> None:
        parsed = parse_prescription_line(
            "Ibuprofen 200 mg - take 2 tablets once (qty 2)"
        )
        self.assertEqual(parsed.frequency, "single dose")

        result = analyze(
            PrescriptionInput(
                raw_text="Ibuprofen 200 mg - take 2 tablets once (qty 2)"
            )
        )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")
        self.assertNotIn("missing usable sig frequency", str(result).lower())
        self.assertNotIn("duration missing", str(result).lower())

    def test_take_two_tablets_x1_is_valid_single_dose_frequency(self) -> None:
        parsed = parse_prescription_line(
            "Ibuprofen 200 mg - take 2 tablets x1 (qty 2)"
        )
        self.assertEqual(parsed.frequency, "single dose")

        result = analyze(
            PrescriptionInput(
                raw_text="Ibuprofen 200 mg - take 2 tablets x1 (qty 2)"
            )
        )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")
        self.assertNotIn("missing usable sig frequency", str(result).lower())
        self.assertNotIn("duration missing", str(result).lower())

    def test_azithromycin_single_dose_flags_dose_unit_formulation_inconsistency(self) -> None:
        result = analyze(
            PrescriptionInput(
                raw_text="Azithromycin 1 g - take 2 tablets once (qty 2)"
            )
        )

        self.assertEqual(result["status"], "OK")
        self.assertNotIn("missing usable sig frequency", str(result).lower())
        self.assertNotIn("duration missing", result["structural_issue"].lower())
        self.assertIn("dose / unit / formulation inconsistency", result["structural_issue"].lower())
        self.assertIn("implied total per administration is 2000 mg", result["structural_issue"].lower())
        self.assertEqual(result.get("issue_type"), "DOSE_UNIT_FORMULATION_INCONSISTENCY")
        self.assertEqual(result["resolution"], "🟢 SAFE / NONE")
        self.assertEqual(result["workflow_status"], "SAFE / NONE")
        self.assertIn("safe", result.get("action_badge", "").lower())
        self.assertNotIn("address during workflow", result.get("action_badge", "").lower())

    def test_priority_prefers_mismatch_over_missing_duration_for_azithromycin(self) -> None:
        result = analyze(
            PrescriptionInput(
                raw_text="Azithromycin 1 g - take 2 tablets once (qty 2)"
            )
        )

        structural_issue = str(result.get("structural_issue", "")).lower()
        self.assertIn("dose / unit / formulation inconsistency", structural_issue)
        self.assertNotIn("duration missing", structural_issue)

    def test_mg_tablet_expression_does_not_trigger_formulation_mismatch(self) -> None:
        result = analyze(
            PrescriptionInput(
                raw_text="Amoxicillin 500 mg - take 2 tablets once (qty 2)"
            )
        )

        self.assertEqual(result["status"], "OK")
        self.assertNotIn("dose / unit / formulation inconsistency", result["structural_issue"].lower())

    def test_ongoing_daily_pattern_does_not_require_duration(self) -> None:
        parsed = parse_prescription_line(
            "Valacyclovir 500 mg - take 1 tablet daily (qty 7)"
        )
        self.assertEqual(parsed.structure_pattern, "ongoing_scheduled")
        self.assertTrue(parsed.structure_complete)
        structural = detect_structural_issue(
            parsed.drug,
            parsed.sig,
            parsed.quantity,
            parsed.frequency,
        )
        self.assertNotIn("duration missing", structural.structural_issue.lower())

    def test_weekly_variable_day_pattern_does_not_require_frequency_token(self) -> None:
        parsed = parse_prescription_line(
            "Ibuprofen 200 mg - take 1 tablet on monday and thursday (qty 8)"
        )
        self.assertEqual(parsed.structure_pattern, "weekly_variable_day")
        self.assertTrue(parsed.structure_complete)

        result = analyze(
            PrescriptionInput(
                raw_text="Ibuprofen 200 mg - take 1 tablet on monday and thursday (qty 8)"
            )
        )
        self.assertEqual(result["status"], "OK")
        self.assertNotIn("missing usable sig frequency", str(result).lower())

    def test_lisinopril_daily_30_no_issue(self) -> None:
        # Lisinopril 20 mg daily, qty 30: should not be flagged
        result = analyze(
            PrescriptionInput(
                raw_text="Lisinopril 20 mg - take 1 tablet by mouth daily (qty 30)"
            )
        )
        self.assertTrue(result["status"] == "OK" or result["resolution"] == "🟢 NONE")
        self.assertNotIn("quantity mismatch", str(result).lower())
        self.assertNotIn("course length", str(result).lower())

    def test_metformin_bidx2_60_no_issue(self) -> None:
        # Metformin 500 mg BID, qty 60: should not be flagged
        result = analyze(
            PrescriptionInput(
                raw_text="Metformin 500 mg - take 1 tablet by mouth twice daily (qty 60)"
            )
        )
        self.assertTrue(result["status"] == "OK" or result["resolution"] == "🟢 NONE")
        self.assertNotIn("quantity mismatch", str(result).lower())
        self.assertNotIn("course length", str(result).lower())

    def test_amoxicillin_tid_7d_21_no_issue(self) -> None:
        # Amoxicillin 500 mg TID for 7 days, qty 21: should not be flagged
        result = analyze(
            PrescriptionInput(
                raw_text="Amoxicillin 500 mg - take 1 tablet by mouth three times daily for 7 days (qty 21)"
            )
        )
        self.assertTrue(result["status"] == "OK" or result["resolution"] == "🟢 NONE")
        self.assertNotIn("quantity mismatch", str(result).lower())
        self.assertNotIn("course length", str(result).lower())


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()