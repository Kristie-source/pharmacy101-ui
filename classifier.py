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


def _risk_severity_from_legacy(severity: str) -> str:
    normalized = str(severity or "").upper()
    if "HIGH" in normalized:
        return "HIGH"
    if "MODERATE" in normalized:
        return "MODERATE"
    return "LOW"


def _immediate_usability_from_legacy(safe_to_verify: str) -> str:
    normalized = str(safe_to_verify or "").upper()
    if "UNSAFE" in normalized:
        return "NO"
    return "YES"


def _workflow_status(risk_severity: str, immediate_usability: str) -> str:
    if str(immediate_usability or "").upper() == "NO":
        return "HOLD NOW"
    if str(risk_severity or "").upper() in {"MODERATE", "HIGH"}:
        return "Verified — Needs Follow-up"
    return "Resolved"


def classify_pattern(pattern: PatternResult) -> ClassificationResult:
    mapping = {
        "formulation_frequency_mismatch_metoprolol_tartrate_qd": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🟡 SAFE WITH GUIDANCE",
            "follow_up_need": "🟡 MESSAGE RECOMMENDED",
            "action": "Clarify patient use",
            "severity": "🟡 MODERATE",
            "risk_score": 58,
            "ui_priority": "🟡 CLARIFY",
            "override_risk": (
                "Immediate-release metoprolol is typically dosed more than once daily; once-daily dosing may not provide full coverage."
            ),
        },
        "acute_use_chronic_quantity": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🟡 SAFE WITH GUIDANCE",
            "follow_up_need": "🟡 MESSAGE RECOMMENDED",
            "action": "Question duration expectation",
            "severity": "🟡 MODERATE",
            "risk_score": 64,
            "ui_priority": "🟡 CLARIFY",
            "override_risk": (
                "Patient may continue therapy longer than intended or keep excess medication for unintended future use."
            ),
        },
        "duration_central_missing_duration": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🟡 SAFE WITH GUIDANCE",
            "follow_up_need": "🟡 MESSAGE RECOMMENDED",
            "action": "Question duration expectation",
            "severity": "🟡 MODERATE",
            "risk_score": 62,
            "ui_priority": "🟡 CLARIFY",
            "override_risk": (
                "Patient may use the medication longer or shorter than intended, leading to incomplete treatment or unnecessary exposure."
            ),
        },
        "dose_unit_formulation_inconsistency": {
            "resolution": "🔴 CHALLENGE",
            "safe_to_verify": "🔴 UNSAFE",
            "follow_up_need": "🔴 REQUIRED BEFORE VERIFY",
            "action": "Review dose/unit/form consistency",
            "severity": "🔴 HIGH",
            "risk_score": 92,
            "ui_priority": "🔴 STOP",
            "override_risk": (
                "Strength expression and dosage unit may represent mismatched formulation intent, creating risk of unintended per-administration dosing."
            ),
        },
        "quantity_mismatch": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🟡 SAFE WITH GUIDANCE",
            "follow_up_need": "🟡 MESSAGE RECOMMENDED",
            "action": "Review quantity expectation",
            "severity": "🟡 MODERATE",
            "risk_score": 60,
            "ui_priority": "🟡 CLARIFY",
            "override_risk": (
                "Patient may run out early or continue therapy longer than intended."
            ),
        },
        "non_daily_dosing_ambiguity": {
            "resolution": "🟠 CLARIFY USE",
            "safe_to_verify": "🔴 UNSAFE",
            "follow_up_need": "🔴 REQUIRED BEFORE VERIFY",
            "action": "Clarify patient use",
            "severity": "🟡 MODERATE",
            "risk_score": 88,
            "ui_priority": "🔴 STOP",
            "override_risk": (
                "Patient may take too much or too little over time if the intended timing pattern is misunderstood."
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
                "Patient may use medication more frequently than intended or misunderstand when to take it."
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
                "Patient may use the medication longer or shorter than intended, leading to incomplete treatment or unnecessary exposure."
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
                "Patient may repeat the medication at the wrong times or more often than intended."
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
                "Patient may use the medication longer or shorter than intended, leading to incomplete treatment or unnecessary exposure."
            ),
        },
    }

    defaults = {
        "resolution": "🟠 CLARIFY USE",
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
    risk_severity = _risk_severity_from_legacy(values["severity"])
    immediate_usability = _immediate_usability_from_legacy(values["safe_to_verify"])
    workflow_status = _workflow_status(risk_severity, immediate_usability)

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
        risk_severity=risk_severity,
        immediate_usability=immediate_usability,
        workflow_status=workflow_status,
    )
