import unittest

from api import PrescriptionInput, analyze
from app import get_follow_up_need, get_override_risk, get_safe_to_verify
from parser import parse_prescription_line
from structural import detect_structural_issue


class PatternQuestionableTests(unittest.TestCase):
    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = str(value or "").lower()
        collapsed = " ".join(lowered.split())
        return "".join(ch for ch in collapsed if ch.isalnum() or ch.isspace()).strip()

    def test_fluconazole_daily_qty4_is_pattern_questionable(self) -> None:
        parsed = parse_prescription_line(
            "Fluconazole 150 mg - take 1 tablet by mouth daily (qty 4)"
        )

        structural = detect_structural_issue(
            parsed.drug,
            parsed.sig,
            parsed.quantity,
            parsed.frequency,
        )

        self.assertEqual(structural.structure_assessment, "Structurally complete")
        self.assertEqual(structural.pattern_assessment, "Pattern-questionable")
        self.assertTrue(structural.pattern_context_supported)
        self.assertNotEqual(structural.resolution, "🟢 NONE")
        self.assertEqual(structural.workflow_status, "Verified — Needs Follow-up")
        self.assertNotEqual(structural.workflow_status, "HOLD NOW")
        self.assertEqual(get_safe_to_verify(structural), "🟡 SAFE WITH GUIDANCE")
        self.assertEqual(get_follow_up_need(structural), "🟡 MESSAGE RECOMMENDED")
        self.assertIn("intended treatment plan may be unclear", structural.pattern_issue.lower())
        self.assertIn(
            "use pattern remains unclear",
            get_override_risk(structural, parsed.drug, parsed.sig, parsed).lower(),
        )

    def test_unknown_drug_does_not_bluff_pattern_concern(self) -> None:
        parsed = parse_prescription_line(
            "Mysterydrug 100 mg - take 1 tablet by mouth daily (qty 4)"
        )

        structural = detect_structural_issue(
            parsed.drug,
            parsed.sig,
            parsed.quantity,
            parsed.frequency,
        )

        self.assertFalse(structural.pattern_context_supported)
        self.assertEqual(structural.pattern_assessment, "Pattern not evaluated")
        self.assertEqual(structural.resolution, "🟢 NONE")

    def test_fluconazole_single_dose_pattern_consistent_is_verify_as_entered(self) -> None:
        parsed = parse_prescription_line(
            "Fluconazole 150 mg - take 1 tablet by mouth for one dose (qty 1)"
        )

        structural = detect_structural_issue(
            parsed.drug,
            parsed.sig,
            parsed.quantity,
            parsed.frequency,
        )

        self.assertEqual(structural.pattern_assessment, "Pattern-consistent")
        self.assertTrue(structural.pattern_context_supported)
        self.assertEqual(structural.resolution, "🟢 NONE")
        self.assertEqual(structural.workflow_status, "VERIFY AS ENTERED")

    def test_api_output_uses_follow_up_wording_not_duration_hold(self) -> None:
        result = analyze(
            PrescriptionInput(
                raw_text="Fluconazole 150 mg - take 1 tablet by mouth daily (qty 4)"
            )
        )

        self.assertEqual(result["pattern_assessment"], "Pattern-questionable")
        self.assertEqual(result["workflow_status"], "Verified — Needs Follow-up")
        self.assertNotEqual(result["workflow_status"], "HOLD NOW")
        self.assertEqual(result["action_line"], "Clarify intended use or treatment plan with prescriber")
        self.assertNotIn("hold", result["action_line"].lower())
        self.assertNotIn("duration", result["action_line"].lower())
        self.assertIn("intended use pattern is unclear", result["issue_line"].lower())
        self.assertIn("does not map cleanly", result["why_this_matters"].lower())
        self.assertIn("use pattern remains unclear", result["override_risk"].lower())
        deviation_lines = [line for line in result["refresh_points"] if "why this stands out:" in line.lower()]
        self.assertEqual(len(deviation_lines), 1)
        self.assertIn("does not clearly match", deviation_lines[0].lower())

    def test_api_sections_are_non_redundant(self) -> None:
        result = analyze(
            PrescriptionInput(
                raw_text="Fluconazole 150 mg - take 1 tablet by mouth daily (qty 4)"
            )
        )

        clinical_check = result.get("clinical_check", "")
        deviation = result.get("deviation", "")
        risk = result.get("risk", "")

        self.assertTrue(clinical_check)
        self.assertTrue(deviation)
        self.assertTrue(risk)

        normalized = {
            self._normalize_text(clinical_check),
            self._normalize_text(deviation),
            self._normalize_text(risk),
        }
        self.assertEqual(len(normalized), 3)


if __name__ == "__main__":
    unittest.main()