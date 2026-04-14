from models import ClassificationResult, PatternResult


def _normalize_resolution_label(value: str) -> str:
    """Keep external lane labels stable while normalizing internal mapping values."""
    normalized = str(value).upper()
    if "CLARIFY USE" in normalized:
        return "🟠 CLARIFY USE"
    if "COMPLETE" in normalized:
        return "🟡 COMPLETE"
    if "NONE" in normalized:
        return "🟢 NONE"
    return "🔴 CHALLENGE"


def classify_pattern(pattern: PatternResult) -> ClassificationResult:
    mapping = {
        "non_daily_dosing_ambiguity": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🔴 UNSAFE",
            "follow_up_need": "🔴 REQUIRED BEFORE VERIFY",
            "action": "Clarify patient use",
            "severity": "🟡 MODERATE",
            "risk_score": 88,
            "ui_priority": "🔴 STOP",
            "override_risk": (
                "Non-daily dosing ambiguity may lead to misinterpretation of frequency and total exposure."
            ),
        },
        "prn_scheduled_conflict": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🔴 UNSAFE",
            "follow_up_need": "🔴 REQUIRED BEFORE VERIFY",
            "action": "Clarify patient use",
            "severity": "🔴 HIGH",
            "risk_score": 95,
            "ui_priority": "🔴 STOP",
            "override_risk": (
                "Patient may interpret the medication as ongoing scheduled use when episodic use was intended."
            ),
        },
        "extended_course_no_duration": {
            "resolution": "🔴 CHALLENGE",
            "safe_to_verify": "🟡 SAFE WITH GUIDANCE",
            "follow_up_need": "🟡 MESSAGE RECOMMENDED",
            "action": "Question duration expectation",
            "severity": "🟡 MODERATE",
            "risk_score": 72,
            "ui_priority": "🟡 CLARIFY",
            "override_risk": (
                "Entered directions and quantity create uncertainty about the intended course structure; verify intended duration before dispensing."
            ),
        },
        "event_based_use": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🔴 UNSAFE",
            "follow_up_need": "🔴 REQUIRED BEFORE VERIFY",
            "action": "Clarify patient use",
            "severity": "🔴 HIGH",
            "risk_score": 95,
            "ui_priority": "🔴 STOP",
            "override_risk": (
                "Medication may be used repeatedly without a clearly defined use pattern. "
                "Unclear event-based instructions may lead to inconsistent or unintended repeated use."
            ),
        },
        "regimen_transformation_ambiguity": {
            "resolution": "🔴 CHALLENGE",
            "safe_to_verify": "🟡 SAFE WITH GUIDANCE",
            "follow_up_need": "🟡 MESSAGE RECOMMENDED",
            "action": "Question duration expectation",
            "severity": "🟡 MODERATE",
            "risk_score": 72,
            "ui_priority": "🟡 CLARIFY",
            "override_risk": (
                "Entered directions and quantity create uncertainty about the intended course structure; verify intended duration before dispensing."
            ),
        },
    }

    defaults = {
        "resolution": "🔴 CHALLENGE",
        "safe_to_verify": "🟢 SAFE",
        "follow_up_need": "🟡 MESSAGE RECOMMENDED",
        "action": "Question pattern",
        "severity": "🟡 MODERATE",
        "risk_score": 48,
        "ui_priority": "🟡 CLARIFY",
        "override_risk": "No significant risk from proceeding.",
    }

    values = mapping.get(pattern.pattern_name, defaults)
    resolution = _normalize_resolution_label(values["resolution"])

    return ClassificationResult(
        pattern_name=pattern.pattern_name,
        resolution=resolution,
        safe_to_verify=values["safe_to_verify"],
        follow_up_need=values["follow_up_need"],
        action=values["action"],
        severity=values["severity"],
        risk_score=values["risk_score"],
        ui_priority=values["ui_priority"],
        override_risk=values["override_risk"],
    )
