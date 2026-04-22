"""
ui_helpers.py

UI-facing language helpers for Pharmacy101.

Purpose:
- Generate short, pharmacist-trust output strings for the frontend
- Keep action-first hierarchy consistent
- Avoid vague/compliance-bot wording

Primary fields produced:
- action_badge
- issue_line
- why_this_matters
- action_line
- known_pattern_message
"""

from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Issue-type language map
# ---------------------------------------------------------------------------

ISSUE_COPY = {
    "DOSE_UNIT_FORMULATION_INCONSISTENCY": {
        "issue_line": "Dose, unit, and formulation do not reconcile cleanly",
        "why_this_matters": "The strength expression and dosage unit imply a total administration amount that may not match intended formulation use.",
        "action_line": "Confirm intended formulation and per-administration dose with prescriber before dispensing",
        "default_badge": "🔴 CHALLENGE",
    },
    "DOSE_STRENGTH_CONSISTENCY": {
        "issue_line": "Strength and tablet count create an inconsistent total dose",
        "why_this_matters": "The implied dose per administration is higher than expected for common use patterns and may not reflect intended prescribing intent.",
        "action_line": "Confirm intended total dose per administration with prescriber before dispensing",
        "default_badge": "🔴 CHALLENGE",
    },
    "PATTERN_QUESTIONABLE": {
        "issue_line": "Regimen is complete but intended use pattern is unclear",
        "why_this_matters": "The entered schedule does not map cleanly to a common low-ambiguity treatment pattern for this medication.",
        "action_line": "Clarify intended use or treatment plan with prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "FREQUENCY_MISMATCH": {
        "issue_line": "Frequency mismatch between product and schedule",
        "why_this_matters": "Immediate-release metoprolol is typically dosed more than once daily; once-daily dosing may not provide full-day coverage.",
        "action_line": "Confirm intended dosing frequency with prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "PRN_SCHEDULED_CONFLICT": {
        "issue_line": "PRN use is mixed with scheduled dosing",
        "why_this_matters": "Patient may not know whether to take this only during episodes or as an ongoing scheduled medication.",
        "action_line": "Clarify intended use pattern with prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "PRN_WITHOUT_DURATION": {
        "issue_line": "Duration not defined for PRN use",
        "why_this_matters": "Patient may not know how long to take this, and quantity suggests multiple days of use.",
        "action_line": "Clarify intended duration with prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "PRN_WITHOUT_MAX_DAILY_USE": {
        "issue_line": "Maximum daily use is not stated",
        "why_this_matters": "Patient may take too much without a clear daily limit.",
        "action_line": "Confirm maximum daily use with prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "SHORT_ACTING_DAILY": {
        "issue_line": "Short-acting metoprolol written once daily",
        "why_this_matters": "May not provide full-day coverage.",
        "action_line": "Confirm dosing schedule",
        "default_badge": "🟠 CLARIFY USE",
    },
    "ACUTE_DRUG_CHRONIC_QTY": {
        "issue_line": "Quantity suggests extended use for an acute medication",
        "why_this_matters": "Typical courses are short-duration.",
        "action_line": "Clarify intended treatment length before dispensing",
        "default_badge": "🔴 CHALLENGE",
    },
    "PRN_WITHOUT_INDICATION": {
        "issue_line": "Use is PRN, but indication is not clear",
        "why_this_matters": "Patient may not know when to use this medication.",
        "action_line": "Clarify intended use with prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "MISSING_DURATION": {
        "issue_line": "Duration is not stated",
        "why_this_matters": "Patient may not know how long to continue treatment.",
        "action_line": "Clarify duration before dispensing",
        "default_badge": "🟠 CLARIFY USE",
    },
    "CONFLICTING_SIG": {
        "issue_line": "Directions include conflicting use instructions",
        "why_this_matters": "Patient could follow the wrong dosing pattern.",
        "action_line": "Clarify intended directions with prescriber",
        "default_badge": "🔴 CHALLENGE",
    },
    "MISSING_STRENGTH": {
        "issue_line": "Strength is not specified clearly",
        "why_this_matters": "Dose cannot be verified confidently without strength.",
        "action_line": "Confirm strength before dispensing",
        "default_badge": "🔴 CHALLENGE",
    },
    "HIGH_FREQUENCY_PRN": {
        "issue_line": "PRN frequency may allow excessive daily use",
        "why_this_matters": "Patient could exceed a reasonable daily amount without clear limits.",
        "action_line": "Clarify PRN frequency and daily limit",
        "default_badge": "🔴 CHALLENGE",
    },
    "MISSING_DOSE_FORM": {
        "issue_line": "Dose form is not specified",
        "why_this_matters": "Use may be unclear without knowing the intended form.",
        "action_line": "Obtain dose form from prescriber",
        "default_badge": "🟠 CLARIFY USE",
    },
    "QUANTITY_MISMATCH": {
        "issue_line": "Quantity may not align with the written directions",
        "why_this_matters": "Supply may not match the intended course or dosing pattern.",
        "action_line": "Review quantity with prescriber before dispensing",
        "default_badge": "🟠 CLARIFY USE",
    },
    "HIGH_DAILY_DOSE": {
        "issue_line": "Daily dose appears high",
        "why_this_matters": "Dose may exceed what the patient is expected to use safely.",
        "action_line": "Review dose with prescriber before dispensing",
        "default_badge": "🔴 CHALLENGE",
    },
    "LOW_REFILL_FREQUENCY": {
        "issue_line": "Refill frequency appears lower than expected",
        "why_this_matters": "Pattern may not match intended ongoing use.",
        "action_line": "Review refill pattern before dispensing",
        "default_badge": "🟠 CLARIFY USE",
    },
}


def normalize_issue_type(raw_issue_text: str) -> str:
    """
    Map free-text structural issue text to internal UI issue codes.

        Scope note:
        - Only structural ambiguity text should map to an actionable issue code.
        - Non-structural or no-issue text must return empty to prevent DUR-style
            escalation in this product surface.
    """
    text = str(raw_issue_text or "").strip()
    if not text:
        return ""

    if text.lower().startswith("no obvious structural issue"):
        return ""

    upper_text = text.upper()
    if upper_text in ISSUE_COPY:
        return upper_text

    lower_text = text.lower()

    if (
        "prn" in lower_text
        and "three times daily" in lower_text
        and "unclear whether" in lower_text
    ):
        return "PRN_SCHEDULED_CONFLICT"

    if "duration" in lower_text and "prn" in lower_text:
        return "PRN_WITHOUT_DURATION"

    if "maximum daily" in lower_text or "max daily" in lower_text:
        return "PRN_WITHOUT_MAX_DAILY_USE"

    if "short-acting" in lower_text and "once daily" in lower_text:
        return "SHORT_ACTING_DAILY"

    if "frequency mismatch" in lower_text and "metoprolol" in lower_text:
        return "FREQUENCY_MISMATCH"

    if "immediate-release metoprolol" in lower_text and "once-daily" in lower_text:
        return "FREQUENCY_MISMATCH"

    if "acute" in lower_text and "quantity" in lower_text:
        return "ACUTE_DRUG_CHRONIC_QTY"

    if "dose / unit / formulation inconsistency" in lower_text:
        return "DOSE_UNIT_FORMULATION_INCONSISTENCY"

    if "dose/strength consistency concern" in lower_text or ("strength" in lower_text and "total dose" in lower_text):
        return "DOSE_STRENGTH_CONSISTENCY"

    if "pattern-questionable" in lower_text or "intended treatment plan may be unclear" in lower_text:
        return "PATTERN_QUESTIONABLE"

    return text


# ---------------------------------------------------------------------------
# Badge helpers
# ---------------------------------------------------------------------------

def _badge_from_context(
    lane: Optional[str],
    issue_type: Optional[str],
    history_match_type: Optional[str],
) -> str:
    """
    Returns final action badge string.

    Rules:
    - Same Rx resolved -> KNOWN PATTERN
    - No issue -> NO ISSUE
    - Otherwise use issue-type default badge
    """
    if history_match_type == "SAME_RX_REFILL_RESOLUTION" or lane == "PASSIVE":
        return "⚪ KNOWN PATTERN"

    if not issue_type or lane == "NONE":
        return "🟢 NO ISSUE"

    issue_cfg = ISSUE_COPY.get(issue_type, {})
    return issue_cfg.get("default_badge", "🟠 CLARIFY USE")


# ---------------------------------------------------------------------------
# Fallback language helpers
# ---------------------------------------------------------------------------

def _humanize_issue_type(issue_type: Optional[str]) -> str:
    if not issue_type:
        return "Issue needs review"
    text = issue_type.replace("_", " ").strip().lower()
    if not text:
        return "Issue needs review"
    return text[0].upper() + text[1:]


def _fallback_issue_line(issue_type: Optional[str]) -> str:
    if not issue_type:
        return "No issue identified"
    custom = {
        "DOSE_UNIT_FORMULATION_INCONSISTENCY": "Dose, unit, and formulation do not reconcile cleanly",
        "DOSE_STRENGTH_CONSISTENCY": "Strength and tablet count create an inconsistent total dose",
        "PATTERN_QUESTIONABLE": "Regimen is complete but intended use pattern is unclear",
        "MISSING_DOSE_FORM": "Dose form is not specified",
        "QUANTITY_MISMATCH": "Quantity may not align with the written directions",
        "HIGH_DAILY_DOSE": "Daily dose appears high",
        "LOW_REFILL_FREQUENCY": "Refill frequency appears lower than expected",
    }
    if issue_type in custom:
        return custom[issue_type]
    return _humanize_issue_type(issue_type)


def _fallback_why_this_matters(issue_type: Optional[str]) -> Optional[str]:
    if not issue_type:
        return None
    custom = {
        "DOSE_UNIT_FORMULATION_INCONSISTENCY": "The strength expression and dosage unit imply a per-administration total that may not match intended formulation use.",
        "DOSE_STRENGTH_CONSISTENCY": "The implied per-administration dose is higher than expected and may represent an unintended total dose.",
        "PATTERN_QUESTIONABLE": "The entered schedule does not match a common low-ambiguity treatment pattern for this medication.",
        "MISSING_DOSE_FORM": "Use may be unclear without knowing the intended form.",
        "QUANTITY_MISMATCH": "Supply may not match the intended course or dosing pattern.",
        "HIGH_DAILY_DOSE": "Dose may exceed what the patient is expected to use safely.",
        "LOW_REFILL_FREQUENCY": "Pattern may not match intended ongoing use.",
    }
    if issue_type in custom:
        return custom[issue_type]
    return "This may affect how the medication is used or interpreted."


def _fallback_action_line(issue_type: Optional[str], lane: Optional[str]) -> str:
    if lane == "PASSIVE":
        return "No further action needed"
    custom = {
        "DOSE_UNIT_FORMULATION_INCONSISTENCY": "Confirm intended formulation and per-administration dose with prescriber before dispensing",
        "DOSE_STRENGTH_CONSISTENCY": "Confirm intended total dose per administration with prescriber before dispensing",
        "PATTERN_QUESTIONABLE": "Clarify intended use or treatment plan with prescriber",
        "MISSING_DOSE_FORM": "Obtain dose form from prescriber",
        "QUANTITY_MISMATCH": "Review quantity with prescriber before dispensing",
        "HIGH_DAILY_DOSE": "Review dose with prescriber before dispensing",
        "LOW_REFILL_FREQUENCY": "Review refill pattern before dispensing",
    }
    if issue_type in custom:
        return custom[issue_type]
    return "Review with prescriber before dispensing"


# ---------------------------------------------------------------------------
# Main field builders
# ---------------------------------------------------------------------------

def get_issue_line(issue_type: Optional[str]) -> str:
    cfg = ISSUE_COPY.get(issue_type or "", {})
    return cfg.get("issue_line") or _fallback_issue_line(issue_type)


def get_why_this_matters(issue_type: Optional[str], lane: Optional[str]) -> Optional[str]:
    if lane == "PASSIVE":
        return None
    cfg = ISSUE_COPY.get(issue_type or "", {})
    return cfg.get("why_this_matters") or _fallback_why_this_matters(issue_type)


def get_action_line(
    issue_type: Optional[str],
    lane: Optional[str],
    history_match_type: Optional[str],
) -> str:
    if history_match_type == "SAME_RX_REFILL_RESOLUTION" or lane == "PASSIVE":
        return "No further action needed"
    cfg = ISSUE_COPY.get(issue_type or "", {})
    return cfg.get("action_line") or _fallback_action_line(issue_type, lane)


def get_known_pattern_message(
    lane: Optional[str],
    history_match_type: Optional[str],
) -> Optional[str]:
    """
    Only use for SAME Rx passive state.
    Do not use for prior-Rx context to avoid duplicate messaging.
    """
    if history_match_type == "SAME_RX_REFILL_RESOLUTION" or lane == "PASSIVE":
        return "Previously clarified on this prescription"
    return None


def build_ui_fields(
    issue_type: Optional[str],
    lane: Optional[str],
    history_match_type: Optional[str] = "NONE",
) -> Dict[str, Optional[str]]:
    """
    Returns the UI-facing fields expected by the frontend.
    """
    action_badge = _badge_from_context(lane, issue_type, history_match_type)
    issue_line = (
        "No action needed"
        if action_badge == "🟢 NO ISSUE"
        else get_issue_line(issue_type)
    )
    why_this_matters = get_why_this_matters(issue_type, lane)
    action_line = get_action_line(issue_type, lane, history_match_type)
    known_pattern_message = get_known_pattern_message(lane, history_match_type)

    return {
        "action_badge": action_badge,
        "issue_line": issue_line,
        "why_this_matters": why_this_matters,
        "action_line": action_line,
        "known_pattern_message": known_pattern_message,
    }


def merge_ui_fields(response_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience helper: merges UI fields into an existing response dict.

    Expects:
    - issue_type
    - lane
    - history_match_type
    """
    ui_fields = build_ui_fields(
        issue_type=response_payload.get("issue_type"),
        lane=response_payload.get("lane"),
        history_match_type=response_payload.get("history_match_type", "NONE"),
    )
    merged = dict(response_payload)
    merged.update(ui_fields)
    return merged