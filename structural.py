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

INTERNAL_INCONSISTENCY_PATTERN_NAMES = {
    "prn_scheduled_conflict",
    "prn_with_scheduled_frequency",
    "conflicting_sig",
}

DOSE_UNIT_FORMULATION_PATTERN_NAMES = {
    "dose_unit_formulation_inconsistency",
}

MINOR_OPTIMIZATION_PATTERN_NAMES = {
    "acute_use_chronic_quantity",
}

HIGH_RISK_AMBIGUITY_PATTERN_NAMES = {
    "non_daily_dosing_ambiguity",
    "event_based_use",
}


@dataclass(frozen=True)
class PriorityCandidate:
    source: str
    priority: int
    pattern_result: Optional[PatternResult] = None
    case_pattern: Optional[object] = None
    regimen_pattern: Optional[object] = None


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
    resolution_val = _normalize_resolution_label("🟢 NONE")
    return StructuralResult(
        structural_issue="No obvious structural issue detected.",
        affects="none",
        clarification="Unlikely",
        resolution=resolution_val,
        drug_recognition_status=recognition_status,
        drug_recognition_match=recognition_match,
        risk_severity="LOW",
        immediate_usability="YES",
        workflow_status="VERIFY AS ENTERED",
        structure_assessment="Structurally complete",
        pattern_assessment="Pattern not evaluated",
        pattern_issue="",
        pattern_context_supported=False,
        decision_tags=_build_decision_tags(resolution=resolution_val),
        pattern_confidence="NONE",
            therapy_type="UNKNOWN",
    )


def _build_pattern_questionable_result(
    recognition_status: str,
    recognition_match: Optional[str],
    pattern_issue: str,
    risk_severity: str,
    immediate_usability: str,
    workflow_status: str,
    resolution: str,
    therapy_type: str = "UNKNOWN",
) -> StructuralResult:
    norm_res = _normalize_resolution_label(resolution)
    return StructuralResult(
        structural_issue=f"Structurally complete, but pattern-questionable: {pattern_issue}",
        affects="pattern",
        clarification="Likely",
        resolution=norm_res,
        drug_recognition_status=recognition_status,
        drug_recognition_match=recognition_match,
        risk_severity=risk_severity,
        immediate_usability=immediate_usability,
        workflow_status="CLARIFY USE",
        structure_assessment="Structurally complete",
        pattern_assessment="Pattern-questionable",
        pattern_issue=pattern_issue,
        pattern_context_supported=True,
        decision_tags=_build_decision_tags(resolution=norm_res),
        pattern_confidence="LOW",
        therapy_type=therapy_type,
    )


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
    return min(candidates, key=lambda candidate: candidate.priority)


def detect_structural_issue(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> StructuralResult:
    from models import ParsedPrescription
    
    recognition_status, recognition_match = recognize_drug(drug)

    structure_pattern = classify_structure_pattern(sig)

    # Create a ParsedPrescription object for pattern detectors
    parsed = ParsedPrescription(
        raw_text="",
        drug=drug,
        sig=sig,
        quantity=quantity,
        frequency=frequency,
        structure_pattern=structure_pattern.pattern_name,
        structure_complete=structure_pattern.structurally_complete,
        structure_missing=structure_pattern.missing_elements,
    )

    specific_flag_pattern = run_specific_flag_bucket(parsed)
    generic_structural_pattern = run_generic_structural_bucket(parsed)
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    prioritized_candidates: list[PriorityCandidate] = []

    # Evaluate all specific detector outputs; do not short-circuit on first match.
    for detector in SPECIFIC_FLAG_RULE_DETECTORS:
        detected = detector(parsed)
        if not detected:
            continue
        if not _is_structural_trigger(detected.structural_issue, detected.affects):
            continue
        prioritized_candidates.append(
            PriorityCandidate(
                source="pattern",
                priority=_priority_for_pattern(detected.pattern_name, detected.structural_issue),
                pattern_result=detected,
            )
        )

    # Evaluate generic detector outputs; generic detectors may already internally prioritize,
    # but still participate in global priority selection.
    for detector in GENERIC_STRUCTURAL_RULE_DETECTORS:
        detected = detector(parsed)
        if not detected:
            continue
        if not _is_structural_trigger(detected.structural_issue, detected.affects):
            continue
        prioritized_candidates.append(
            PriorityCandidate(
                source="pattern",
                priority=_priority_for_pattern(detected.pattern_name, detected.structural_issue),
                pattern_result=detected,
            )
        )

    if pattern and _is_structural_trigger(pattern.structural_issue, pattern.affects):
        prioritized_candidates.append(
            PriorityCandidate(
                source="case",
                priority=_priority_for_pattern(pattern.name, pattern.structural_issue),
                case_pattern=pattern,
            )
        )

    winner = _choose_highest_priority_issue(prioritized_candidates)
    if winner is not None:
        if winner.source == "pattern" and winner.pattern_result is not None:
            classification = classify_pattern(winner.pattern_result)
            selected_priority = _priority_for_pattern(
                winner.pattern_result.pattern_name,
                winner.pattern_result.structural_issue,
            )
            workflow_status = _escalation_workflow_status(
                priority=selected_priority,
                pattern_name=winner.pattern_result.pattern_name,
                immediate_usability=classification.immediate_usability,
                pattern_assessment="Pattern not evaluated",
            )
            return StructuralResult(
                structural_issue=winner.pattern_result.structural_issue,
                affects=winner.pattern_result.affects,
                clarification=winner.pattern_result.clarification,
                resolution=_normalize_resolution_label(classification.resolution),
                drug_recognition_status=recognition_status,
                drug_recognition_match=recognition_match,
                risk_severity=classification.risk_severity,
                immediate_usability=classification.immediate_usability,
                workflow_status=workflow_status,
                structure_assessment="Structural concern",
                pattern_assessment="Pattern not evaluated",
                pattern_issue="",
                pattern_context_supported=False,
                decision_tags=_build_decision_tags(
                    resolution=_normalize_resolution_label(classification.resolution),
                    structural_issue=winner.pattern_result.structural_issue,
                    affects=winner.pattern_result.affects,
                    risk_severity=classification.risk_severity,
                    immediate_usability=classification.immediate_usability,
                    workflow_status=workflow_status,
                    structure_assessment="Structural concern",
                    pattern_assessment="Pattern not evaluated",
                    pattern_issue="",
                    pattern_context_supported=False,
                ),
                pattern_confidence="NONE",
            )

        if winner.source == "case" and winner.case_pattern is not None:
            resolution = get_resolution(winner.case_pattern.clarification, winner.case_pattern.affects)
            risk_severity = _derive_risk_severity_from_resolution(resolution)
            immediate_usability = _derive_immediate_usability_from_resolution(resolution)
            selected_priority = _priority_for_pattern(winner.case_pattern.name, winner.case_pattern.structural_issue)
            workflow_status = _escalation_workflow_status(
                priority=selected_priority,
                pattern_name=winner.case_pattern.name,
                immediate_usability=immediate_usability,
                pattern_assessment="Pattern not evaluated",
            )
            return StructuralResult(
                structural_issue=winner.case_pattern.structural_issue,
                affects=winner.case_pattern.affects,
                clarification=winner.case_pattern.clarification,
                resolution=resolution,
                drug_recognition_status=recognition_status,
                drug_recognition_match=recognition_match,
                risk_severity=risk_severity,
                immediate_usability=immediate_usability,
                workflow_status=workflow_status,
                structure_assessment="Structural concern",
                pattern_assessment="Pattern not evaluated",
                pattern_issue="",
                pattern_context_supported=False,
                decision_tags=_build_decision_tags(
                    resolution=resolution,
                    structural_issue=winner.case_pattern.structural_issue,
                    affects=winner.case_pattern.affects,
                    risk_severity=risk_severity,
                    immediate_usability=immediate_usability,
                    workflow_status=workflow_status,
                    structure_assessment="Structural concern",
                    pattern_assessment="Pattern not evaluated",
                    pattern_issue="",
                    pattern_context_supported=False,
                ),
                pattern_confidence="NONE",
            )

    # Pattern-aware clinical reasoning layer runs only after structural checks are clear.
    # "No issue" requires both structural validity and no pattern concern.
    regimen_pattern = evaluate_regimen_pattern(drug, sig, quantity, frequency)
    if regimen_pattern.pattern_context_supported and regimen_pattern.pattern_assessment == "Pattern-questionable":
        workflow_status = _escalation_workflow_status(
            priority=5,
            pattern_name="pattern_questionable",
            immediate_usability=regimen_pattern.immediate_usability,
            pattern_assessment="Pattern-questionable",
            pattern_dispensing_risk=bool(getattr(regimen_pattern, "pattern_dispensing_risk", False)),
        )
        return _build_pattern_questionable_result(
            recognition_status=recognition_status,
            recognition_match=recognition_match,
            pattern_issue=regimen_pattern.pattern_issue,
            risk_severity=regimen_pattern.risk_severity,
            immediate_usability=regimen_pattern.immediate_usability,
            workflow_status=workflow_status,
            resolution=regimen_pattern.resolution,
            therapy_type=(getattr(regimen_pattern, "therapy_type", None) or "UNKNOWN"),
        )

    if is_verify_as_entered_bucket(
        parsed,
        specific_flag_pattern,
        generic_structural_pattern,
        pattern,
    ):
        if regimen_pattern.pattern_context_supported:
            no_issue = _build_no_issue_result(recognition_status, recognition_match)
            no_issue.pattern_assessment = regimen_pattern.pattern_assessment
            no_issue.pattern_context_supported = True
            no_issue.therapy_type = getattr(regimen_pattern, "therapy_type", "UNKNOWN")
            # decision_tags already set in _build_no_issue_result
            return no_issue

    return _build_no_issue_result(recognition_status, recognition_match)