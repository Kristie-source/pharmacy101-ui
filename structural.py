def map_patient_interpretability(
    pattern_assessment: str,
    structural_issue: str,
    clarification: str,
    structure_assessment: str
) -> str:
    """
    Maps existing structural signals into patient-facing execution clarity.

    HIGH = patient can execute without guessing
    MEDIUM = borderline or incomplete confidence
    LOW = patient likely must guess about use, stopping point, frequency, or max use
    """

    if clarification == "Unlikely" and structure_assessment == "Structurally complete":
        return "HIGH"

    if clarification == "Likely":
        return "LOW"

    return "MEDIUM"
def _build_decision_tags(
    resolution=None,
    structural_issue=None,
    affects=None,
    risk_severity=None,
    immediate_usability=None,
    workflow_status=None,
    structure_assessment=None,
    pattern_assessment=None,
    pattern_issue=None,
    pattern_context_supported=None,
):
    if resolution is not None:
        res = str(resolution).upper()
        if "NONE" in res or "SAFE" in res:
            return {
                "patient_interpretability": "HIGH",
                "outcome_risk": "LOW",
                "pharmacist_hesitation": "LOW",
                "pattern_familiarity": "HIGH",
                "structural_integrity": "INTACT",
            }
        if "CLARIFY" in res:
            return {
                "patient_interpretability": "LOW",
                "outcome_risk": "MODERATE",
                "pharmacist_hesitation": "HIGH",
                "pattern_familiarity": "MEDIUM",
                "structural_integrity": "SOFT_GAP",
            }
        if "CHALLENGE" in res:
            return {
                "patient_interpretability": "LOW",
                "outcome_risk": "HIGH",
                "pharmacist_hesitation": "HIGH",
                "pattern_familiarity": "LOW",
                "structural_integrity": "HARD_GAP",
            }

    return {
        "patient_interpretability": "UNKNOWN",
        "outcome_risk": "UNKNOWN",
        "pharmacist_hesitation": "UNKNOWN",
        "pattern_familiarity": "UNKNOWN",
        "structural_integrity": "UNKNOWN",
    }
from dataclasses import dataclass
from typing import Optional

from models import PatternResult, StructuralResult
from case_library import match_case_pattern, recognize_drug
from classifier import classify_pattern
from drug_context import evaluate_regimen_pattern
from structure_patterns import classify_structure_pattern
from validation_buckets import (
    GENERIC_STRUCTURAL_RULE_DETECTORS,
    SPECIFIC_FLAG_RULE_DETECTORS,
    is_verify_as_entered_bucket,
    run_generic_structural_bucket,
    run_specific_flag_bucket,
)

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

# --- Restored missing definitions ---
from dataclasses import dataclass

@dataclass
class PriorityCandidate:
    source: str
    priority: int
    pattern_result: Optional[PatternResult] = None
    case_pattern: Optional[object] = None

INTERNAL_INCONSISTENCY_PATTERN_NAMES = {
    "internal_inconsistency",
    "conflicting_directions",
}

DOSE_UNIT_FORMULATION_PATTERN_NAMES = {
    "dose_unit_formulation_mismatch",
    "dose_form_mismatch",
}

MINOR_OPTIMIZATION_PATTERN_NAMES = {
    "minor_optimization",
}

HIGH_RISK_AMBIGUITY_PATTERN_NAMES = {
    "non_daily_dosing_ambiguity",
    "event_based_use",
}



def _derive_risk_severity_from_resolution(resolution: str) -> str:
    normalized = str(resolution or "").upper()
    if "CLARIFY USE" in normalized or "COMPLETE" in normalized:
        return "HIGH"
    if "CHALLENGE" in normalized:
        return "MODERATE"
    return "LOW"


def _derive_immediate_usability_from_resolution(resolution: str) -> str:
    normalized = str(resolution or "").upper()
    if "CLARIFY USE" in normalized or "COMPLETE" in normalized:
        return "NO"
    return "YES"


def _derive_workflow_status(risk_severity: str, immediate_usability: str) -> str:
    if str(immediate_usability or "").upper() == "NO":
        return "HOLD NOW"
    if str(risk_severity or "").upper() in {"MODERATE", "HIGH"}:
        return "Verified — Needs Follow-up"
    return "Resolved"


def _is_internal_inconsistency(pattern_name: str, issue_text: str) -> bool:
    normalized_name = str(pattern_name or "").strip().lower()
    lower_issue = str(issue_text or "").strip().lower()
    if normalized_name in INTERNAL_INCONSISTENCY_PATTERN_NAMES:
        return True

    contradiction_markers = (
        "conflict",
        "contradict",
        "inconsistent directions",
        "unclear whether",
        "combined with",
    )
    return any(marker in lower_issue for marker in contradiction_markers)


    def map_patient_interpretability(
        pattern_assessment: str,
        structural_issue: str,
        clarification: str,
        structure_assessment: str
    ) -> str:
        """
        Maps existing structural signals into patient-facing execution clarity.

        HIGH = patient can execute without guessing
        MEDIUM = borderline or incomplete confidence
        LOW = patient likely must guess about use, stopping point, frequency, or max use
        """

        if clarification == "Unlikely" and structure_assessment == "Structurally complete":
            return "HIGH"

        if clarification == "Likely":
            return "LOW"

        return "MEDIUM"

def _priority_for_pattern(pattern_name: str, issue_text: str) -> int:
    normalized_name = str(pattern_name or "").strip().lower()
    lower_issue = str(issue_text or "").strip().lower()

    # Priority ladder:
    # 1 Parse failure (handled in INVALID bucket before this function)
    # 2 Internal inconsistency / contradiction
    # 3 Dose / unit / formulation mismatch
    # 4 Structural pattern failure
    # 5 Pattern-backed clinical concern
    # 6 Minor optimization issues
    # 7 None
    if _is_internal_inconsistency(normalized_name, lower_issue):
        return 2
    if normalized_name in DOSE_UNIT_FORMULATION_PATTERN_NAMES or "dose / unit / formulation inconsistency" in lower_issue:
        return 3
    if normalized_name in MINOR_OPTIMIZATION_PATTERN_NAMES:
        return 6
    return 4


def _escalation_workflow_status(
    *,
    priority: int,
    pattern_name: str,
    immediate_usability: str,
    pattern_assessment: str,
    pattern_dispensing_risk: bool = False,
) -> str:
    """Map selected issue to workflow lane.

    Escalation mapping:
    - HOLD NOW: contradictions, internal inconsistency, dose/unit mismatch,
      or explicitly high-risk ambiguity affecting dispensing.
    - Verified — Needs Follow-up: structurally complete but pattern-questionable,
      unclear intent with safe-to-proceed context.
    - ADDRESS DURING WORKFLOW: lower-impact structural issues / non-critical ambiguity.
    - VERIFY AS ENTERED: valid structure with no meaningful issue.
    """
    normalized_name = str(pattern_name or "").strip().lower()
    usability = str(immediate_usability or "YES").upper()

    if priority >= 7:
        return "VERIFY AS ENTERED"

    if pattern_assessment == "Pattern-questionable":
        if pattern_dispensing_risk:
            return "HOLD NOW"
        return "Verified — Needs Follow-up"

    if priority in {2, 3}:
        return "HOLD NOW"

    if normalized_name in HIGH_RISK_AMBIGUITY_PATTERN_NAMES and usability == "NO":
        return "HOLD NOW"

    if priority == 6:
        return "ADDRESS DURING WORKFLOW"

    if usability == "NO":
        return "HOLD NOW"

    if priority in {4, 5}:
        return "ADDRESS DURING WORKFLOW" if priority == 4 else "Verified — Needs Follow-up"

    return "VERIFY AS ENTERED"


def _choose_highest_priority_issue(candidates: list[PriorityCandidate]) -> Optional[PriorityCandidate]:
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.priority)
