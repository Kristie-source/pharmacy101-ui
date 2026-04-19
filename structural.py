from typing import Optional

from models import StructuralResult
from case_library import match_case_pattern, recognize_drug
from patterns import detect_pattern_families
from classifier import classify_pattern

# Product scope guardrails:
# Pharmacy101 detects structural ambiguity in prescription directions.
# It is intentionally NOT a DUR engine. DUR-style checks (drug-drug interactions,
# duplicate therapy, renal/hepatic dose adjustments, allergy checks) are excluded
# as primary triggers to prevent alert fatigue and avoid redundancy with existing
# pharmacy DUR systems.
ALLOWED_STRUCTURAL_AFFECTS = {"instructions", "duration", "frequency"}
DUR_EXCLUSION_KEYWORDS = (
    "drug-drug interaction",
    "interaction",
    "duplicate therapy",
    "duplicate therapeutic",
    "renal",
    "hepatic",
    "allergy",
)


def _normalize_resolution_label(value: str) -> str:
    normalized = str(value).upper()
    if "CLARIFY USE" in normalized:
        return "🟠 CLARIFY USE"
    if "COMPLETE" in normalized:
        return "🟡 COMPLETE"
    if "NONE" in normalized:
        return "🟢 NONE"
    return "🔴 CHALLENGE"


def get_resolution(clarification: str, affects: str) -> str:
    if clarification == "Context-dependent":
        if affects == "instructions":
            return _normalize_resolution_label("🟠 CLARIFY USE")
        else:
            return _normalize_resolution_label("🔴 CHALLENGE")
    elif clarification == "Likely":
        if affects in ["duration", "frequency"]:
            return _normalize_resolution_label("🔴 CHALLENGE")
        elif affects == "instructions":
            return _normalize_resolution_label("🟡 COMPLETE")
    else:
        return _normalize_resolution_label("🟢 NONE")


def _is_structural_trigger(structural_issue: str, affects: str) -> bool:
    affects_value = str(affects or "").strip().lower()
    if affects_value not in ALLOWED_STRUCTURAL_AFFECTS:
        return False

    issue_text = str(structural_issue or "").strip().lower()
    if not issue_text or issue_text.startswith("no obvious structural issue"):
        return False

    # Hard exclusion: DUR domains cannot independently trigger a case.
    if any(keyword in issue_text for keyword in DUR_EXCLUSION_KEYWORDS):
        return False

    return True


def _build_no_issue_result(recognition_status: str, recognition_match: Optional[str]) -> StructuralResult:
    return StructuralResult(
        structural_issue="No obvious structural issue detected.",
        affects="none",
        clarification="Unlikely",
        resolution=_normalize_resolution_label("🟢 NONE"),
        drug_recognition_status=recognition_status,
        drug_recognition_match=recognition_match,
    )


def detect_structural_issue(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> StructuralResult:
    from models import ParsedPrescription
    
    recognition_status, recognition_match = recognize_drug(drug)

    # Create a ParsedPrescription object for pattern detectors
    parsed = ParsedPrescription(
        raw_text="",
        drug=drug,
        sig=sig,
        quantity=quantity,
        frequency=frequency
    )

    # New decision-tree branch: detect explicit pattern families first.
    family_pattern = detect_pattern_families(parsed)
    if family_pattern:
        if not _is_structural_trigger(family_pattern.structural_issue, family_pattern.affects):
            return _build_no_issue_result(recognition_status, recognition_match)

        classification = classify_pattern(family_pattern)
        return StructuralResult(
            structural_issue=family_pattern.structural_issue,
            affects=family_pattern.affects,
            clarification=family_pattern.clarification,
            resolution=_normalize_resolution_label(classification.resolution),
            drug_recognition_status=recognition_status,
            drug_recognition_match=recognition_match,
        )

    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        if not _is_structural_trigger(pattern.structural_issue, pattern.affects):
            return _build_no_issue_result(recognition_status, recognition_match)

        resolution = get_resolution(pattern.clarification, pattern.affects)
        return StructuralResult(
            structural_issue=pattern.structural_issue,
            affects=pattern.affects,
            clarification=pattern.clarification,
            resolution=resolution,
            drug_recognition_status=recognition_status,
            drug_recognition_match=recognition_match,
        )

    return _build_no_issue_result(recognition_status, recognition_match)