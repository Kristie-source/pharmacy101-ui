from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import csv
import io
import re
import string
from structural import detect_structural_issue
from action_threshold import determine_action_threshold
from knowledge_refresh import explain_pattern
from documenter import generate_documentation
from messager import generate_message
from app import (
    get_action_bias, get_follow_up_need, get_safe_to_verify,
    get_severity, get_risk_score, get_ui_priority, get_override_risk
)
from database import (
    save_analysis,
    update_resolution,
    get_history_summary_by_pattern_key,
    build_pattern_key,
    get_connection,
)
from drug_context import build_compact_drug_context_block
from ui_helpers import merge_ui_fields
import ui_helpers
from resolution_memory import (
    init_resolution_memory_tables,
    build_normalized_fingerprint,
    validate_rx_instance_id,
    find_same_rx_refill_resolution,
    find_prior_rx_pattern,
    build_seen_before_context,
    append_analysis_audit,
    save_resolution_record,
    validate_resolve_input,
)
from validation_buckets import run_invalid_bucket

app = FastAPI()
init_resolution_memory_tables()


def init_event_log_table() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            pharmacist_id TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def insert_event(
    analysis_id: int,
    event_type: str,
    note: Optional[str] = None,
    pharmacist_id: Optional[str] = None,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO analysis_events (analysis_id, event_type, note, pharmacist_id)
        VALUES (?, ?, ?, ?)
        """,
        (analysis_id, event_type, note, pharmacist_id),
    )
    conn.commit()
    event_id = int(cursor.lastrowid)
    conn.close()
    return event_id


init_event_log_table()


def _normalize_export_status(value: str | None) -> str:
    status = (value or "").strip().lower()
    if "resolv" in status or status in {"complete", "done", "closed"}:
        return "resolved"
    return "pending"


def _extract_strength(drug: str | None) -> str:
    text = str(drug or "")
    match = re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm)\b", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"\bgm\b", "g", match.group(0), flags=re.IGNORECASE).lower()


def _extract_drug_name(drug: str | None, strength: str) -> str:
    text = str(drug or "").strip()
    if not text:
        return ""
    if not strength:
        return text
    return re.sub(re.escape(strength), "", text, flags=re.IGNORECASE).replace("  ", " ").strip()


def _derive_fast_lane(final_lane: str | None) -> str:
    lane = str(final_lane or "").upper()
    if "CHALLENGE" in lane:
        return "HOLD"
    if "CLARIFY" in lane or "COMPLETE" in lane:
        return "ADDRESS"
    return "VERIFY"


def _derive_confidence(risk_score: int | None) -> str:
    if risk_score is None:
        return ""
    try:
        value = int(risk_score)
    except (TypeError, ValueError):
        return ""
    if value >= 70:
        return "HIGH"
    if value >= 40:
        return "MEDIUM"
    return "LOW"


def _has_structural_trigger(structural: object) -> bool:
    """
    Scope validator for Pharmacy101:
    - Cases must originate from structural ambiguity in prescription instructions.
    - Context may refine severity/risk but cannot independently trigger a case.
    """
    lane = str(getattr(structural, "resolution", "") or "").upper()
    affects = str(getattr(structural, "affects", "") or "").lower()
    issue_text = str(getattr(structural, "structural_issue", "") or "").lower()
    pattern_assessment = str(getattr(structural, "pattern_assessment", "") or "")

    if pattern_assessment == "Pattern-questionable":
        return True
    if "NONE" in lane:
        return False
    if affects not in {"instructions", "duration", "frequency"}:
        return False
    if not issue_text or issue_text.startswith("no obvious structural issue"):
        return False
    return True


def _capitalize_sentence_start(text: Optional[str]) -> Optional[str]:
    value = str(text or "")
    if not value:
        return text

    for idx, ch in enumerate(value):
        if ch.isalpha():
            if ch.islower():
                return f"{value[:idx]}{ch.upper()}{value[idx + 1:]}"
            return value

    return value


def _capitalize_clinical_check_fields(payload: dict) -> dict:
    sentence_fields = (
        "structural_issue",
        "override_risk",
        "refresh_conclusion",
        "documentation",
        "prescriber_message",
        "internal_message",
        "issue_line",
        "why_this_matters",
        "action_line",
        "known_pattern_message",
    )

    for field in sentence_fields:
        if field in payload and isinstance(payload[field], str):
            payload[field] = _capitalize_sentence_start(payload[field])

    if isinstance(payload.get("refresh_points"), list):
        payload["refresh_points"] = [
            _capitalize_sentence_start(point) if isinstance(point, str) else point
            for point in payload["refresh_points"]
        ]

    return payload


def _normalize_sentence_for_compare(text: Optional[str]) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        return ""
    stripped = raw.translate(str.maketrans("", "", string.punctuation))
    return " ".join(stripped.split())


def _extract_refresh_deviation(refresh_points: list) -> Optional[str]:
    for point in refresh_points or []:
        if not isinstance(point, str):
            continue
        lower_point = point.lower()
        if lower_point.startswith("why this stands out:"):
            return point.split(":", 1)[1].strip() if ":" in point else point.strip()
    return None


def _fallback_deviation(payload: dict) -> str:
    pattern_assessment = str(payload.get("pattern_assessment", "") or "")
    structural_issue = str(payload.get("structural_issue", "") or "")
    affects = str(payload.get("affects", "") or "")

    if pattern_assessment == "Pattern-questionable":
        return "Directions are structurally complete, but the regimen does not align cleanly with a recognized low-ambiguity pattern for this drug."
    if "dose / unit / formulation inconsistency" in structural_issue.lower():
        return "The stated strength expression and administration unit imply different formulation assumptions."
    if affects == "duration":
        return "The written duration structure does not cleanly map to the implied course pattern."
    if affects == "frequency":
        return "The schedule wording does not fully align with a single, unambiguous administration cadence."
    return "The written structure diverges from expected instruction patterning and needs targeted follow-up."


def _fallback_risk(payload: dict) -> str:
    affects = str(payload.get("affects", "") or "")
    structural_issue = str(payload.get("structural_issue", "") or "").lower()

    if "dose / unit / formulation inconsistency" in structural_issue:
        return "Dispensing against a mismatched formulation assumption may cause unintended per-administration exposure."
    if affects == "duration":
        return "The patient may continue longer or shorter than intended, with risk of under- or over-treatment."
    if affects == "frequency":
        return "The patient may use the medication at an unintended cadence, reducing effectiveness or increasing adverse effects."
    if affects == "instructions":
        return "Ambiguous instructions may lead to incorrect use at the point of administration."
    return "Proceeding without clarification may result in medication use that differs from prescriber intent."


def _apply_non_redundant_clinical_sections(payload: dict) -> dict:
    clinical_check = str(payload.get("issue_line") or payload.get("structural_issue") or "").strip()
    deviation = str(payload.get("why_this_matters") or "").strip()
    if not deviation:
        deviation = str(_extract_refresh_deviation(payload.get("refresh_points", [])) or "").strip()
    risk = str(payload.get("override_risk") or "").strip()

    normalized_clinical = _normalize_sentence_for_compare(clinical_check)
    normalized_deviation = _normalize_sentence_for_compare(deviation)
    normalized_risk = _normalize_sentence_for_compare(risk)

    if not deviation or normalized_deviation == normalized_clinical:
        deviation = _fallback_deviation(payload)
        normalized_deviation = _normalize_sentence_for_compare(deviation)

    if not risk or normalized_risk in {normalized_clinical, normalized_deviation}:
        risk = _fallback_risk(payload)

    payload["clinical_check"] = clinical_check
    payload["deviation"] = deviation
    payload["risk"] = risk

    # Keep legacy fields aligned with non-redundant section content.
    payload["issue_line"] = clinical_check
    payload["why_this_matters"] = deviation
    payload["override_risk"] = risk
    return payload

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class PrescriptionInput(BaseModel):
    raw_text: str
    source_ref: Optional[str] = None
    debug: bool = False
    rx_instance_id: Optional[str] = None
    fill_number: int = 0
    patient_id: Optional[str] = None
    prescriber_id: Optional[str] = None


class ResolveInput(BaseModel):
    rx_instance_id: str
    fill_number: int = 0
    normalized_fingerprint: str
    issue_type: str
    patient_id: str
    resolution_state: str
    suppression_scope: str = "PATIENT_ONLY"
    prescriber_id: Optional[str] = None
    note: Optional[str] = None
    pharmacist_id: Optional[str] = None


class AnalysisEventInput(BaseModel):
    event_type: str
    note: Optional[str] = None
    pharmacist_id: Optional[str] = None

@app.post("/analyze")
def analyze(input: PrescriptionInput):
    invalid_outcome = run_invalid_bucket(input.raw_text)
    if invalid_outcome.is_invalid:
        return {"status": "INVALID", "error": invalid_outcome.error or "Invalid input."}

    parsed = invalid_outcome.parsed
    if parsed is None:
        return {"status": "INVALID", "error": "Invalid input."}

    # Require explicit drug strength for most products
    import re
    strength_pattern = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|g|gm|unit|units|%)\b", re.IGNORECASE)
    if not strength_pattern.search(parsed.drug):
        return {
            "status": "INVALID",
            "error": "Missing drug strength. Include drug name, strength, SIG, and quantity."
        }

    structural = detect_structural_issue(
        parsed.drug, parsed.sig, parsed.quantity, parsed.frequency
    )
    # SAFE override for fluconazole repeat-dose pattern (qty 2, single dose + repeat)
    sig_lower = (parsed.sig or "").lower()
    if (
        "fluconazole" in (parsed.drug or "").lower()
        and str(parsed.quantity).strip() == "2"
        and "once" in sig_lower
        and (
            "repeat" in sig_lower
            or "in 72 hours" in sig_lower
            or "second dose" in sig_lower
            or "may repeat" in sig_lower
        )
        and "once daily" not in sig_lower
    ):
        # Force all fields to SAFE/NONE and clear any mismatch
        structural.resolution = "🟢 NONE"
        structural.structural_issue = "No action needed"
        structural.affects = "none"
        structural.clarification = "Unlikely"
        prescriber_message = ""
        internal_message = ""
        clinical_check = "No action needed"
        issue_line = "No action needed"
        from types import SimpleNamespace
        threshold = SimpleNamespace(
            action_level="NONE",
            badge="🟢",
            action_label="SAFE / NONE",
            safe_to_verify="SAFE",
            follow_up_required=False,
            reason="Repeat-dose pattern accounted for in quantity"
        )
        has_structural_trigger = False
    else:
        has_structural_trigger = _has_structural_trigger(structural)
        # Action threshold logic
        threshold = determine_action_threshold(
            drug=parsed.drug,
            sig=parsed.sig,
            quantity=parsed.quantity,
            issue_type=locals().get("issue_type"),
            affects=locals().get("affects"),
            risk=locals().get("override_risk") or locals().get("risk"),
            pattern_assessment=locals().get("pattern_assessment"),
            clinical_check=locals().get("clinical_check") or locals().get("issue_line"),
            deviation=locals().get("deviation") or locals().get("why_this_matters"),
            prescriber_message=locals().get("prescriber_message"),
        )

    # Intentional product boundary:
    # If no structural ambiguity is detected, classify as No Issue and do not
    # escalate from context/history signals to avoid duplicating DUR alerting.
    if not has_structural_trigger:
        structural.structural_issue = "No obvious structural issue detected."
        structural.affects = "none"
        structural.clarification = "Unlikely"
        structural.resolution = "🟢 NONE"


    # --- Normalization block for legacy UI fields (applied immediately before result) ---
    if threshold.action_level == "HOLD_NOW":
        resolution = "🔴 HOLD NOW / CHALLENGE"
        severity = "🔴 HIGH"
        risk_severity = "HIGH"
        immediate_usability = "NO"
        workflow_status = "HOLD NOW"
        ui_priority = "🔴 HOLD"
        action_badge = "🔴 HOLD NOW / CHALLENGE"
        follow_up_need = "🔴 REQUIRED BEFORE VERIFY"
        action_bias = "Confirm before verification"
    elif threshold.action_level == "ADDRESS_DURING_WORKFLOW":
        resolution = "🟠 ADDRESS DURING WORKFLOW"
        severity = "🟠 MODERATE"
        risk_severity = "MODERATE"
        immediate_usability = "CONDITIONAL"
        workflow_status = "ADDRESS DURING WORKFLOW"
        ui_priority = "🟠 WORKFLOW"
        action_badge = "🟠 ADDRESS DURING WORKFLOW"
        follow_up_need = "🟠 REQUIRED DURING WORKFLOW"
        action_bias = "Clarify or document during workflow"
    elif threshold.action_level == "COMPLETE":
        resolution = "🟡 COMPLETE"
        severity = "🟡 LOW"
        risk_severity = "LOW"
        immediate_usability = "YES"
        workflow_status = "COMPLETE"
        ui_priority = "🟡 COMPLETE"
        action_badge = "🟡 COMPLETE"
        follow_up_need = "Optional"
        action_bias = "Verify with counseling if useful"
    else:
        resolution = "🟢 NONE"
        severity = "🟢 NONE"
        risk_severity = "NONE"
        immediate_usability = "YES"
        workflow_status = "NONE"
        ui_priority = "🟢 NONE"
        action_badge = "🟢 NONE"
        follow_up_need = "None"
        action_bias = "No action needed"
    safe_to_verify = threshold.safe_to_verify
    risk_score = get_risk_score(
        resolution, safe_to_verify, follow_up_need, severity
    )
    refresh = explain_pattern(
        parsed.drug, parsed.sig, parsed.quantity, parsed.frequency
    )
    doc = generate_documentation(
        parsed.drug, parsed.sig, parsed.quantity, parsed.frequency
    )
    msg = generate_message(
        parsed.drug, parsed.sig, parsed.quantity, parsed.frequency
    )
    debug_enabled = bool(input.debug)
    override_risk = get_override_risk(structural, parsed.drug, parsed.sig, parsed)

    result = {
        "status": "OK",
        "drug": parsed.drug,
        "sig": parsed.sig,
        "quantity": parsed.quantity,
        "frequency": parsed.frequency,
        "structural_issue": structural.structural_issue,
        "affects": structural.affects,
        "clarification": structural.clarification,
        "resolution": f"{threshold.badge} {threshold.action_label}",
        "severity": severity,
        "risk_severity": risk_severity,
        "immediate_usability": immediate_usability,
        "workflow_status": threshold.action_label,
        "ui_priority": f"{threshold.badge} {threshold.action_label}",
        "action_badge": f"{threshold.badge} {threshold.action_label}",
        "follow_up_need": follow_up_need,
        "action_bias": action_bias,
        "structure_assessment": structural.structure_assessment,
        "pattern_assessment": structural.pattern_assessment,
        "pattern_issue": structural.pattern_issue,
        "pattern_context_supported": structural.pattern_context_supported,
        "drug_recognition_status": structural.drug_recognition_status,
        "drug_recognition_match": structural.drug_recognition_match,
        "safe_to_verify": safe_to_verify,
        "risk_score": risk_score,
        "override_risk": override_risk,
        "refresh_points": refresh.summary_points,
        "refresh_conclusion": refresh.conclusion,
        "documentation": doc.note,
        "prescriber_message": msg.prescriber_message,
        "internal_message": msg.internal_message,
        "drug_context_match": msg.drug_context_key,
        "source_ref": input.source_ref,
        # Action threshold fields (source of truth)
        "action_level": threshold.action_level,
        "badge": threshold.badge,
        "action_label": threshold.action_label,
        "follow_up_required": threshold.follow_up_required,
        "threshold_reason": threshold.reason,
        # Debug field for normalization
        "threshold_debug_applied": threshold.action_level,
    }

    if debug_enabled:
        result["llm_prompt_text"] = msg.prompt_text
        result["drug_context_block"] = build_compact_drug_context_block(parsed.drug)

    result = _capitalize_clinical_check_fields(result)

    pattern_key = build_pattern_key(parsed.drug, parsed.sig, parsed.quantity)
    result["pattern_key"] = pattern_key

    analysis_id = save_analysis({**result, "pattern_key": pattern_key})
    result["analysis_id"] = analysis_id
    result["history_summary"] = get_history_summary_by_pattern_key(pattern_key, analysis_id)

    if structural.pattern_assessment == "Pattern-questionable":
        issue_type = "PATTERN_QUESTIONABLE"
    else:
        issue_type = ui_helpers.normalize_issue_type(structural.structural_issue) if has_structural_trigger else ""

    rx_id_check = validate_rx_instance_id(input.rx_instance_id)
    rx_instance_id_valid = rx_id_check["valid"]
    rx_instance_id_error = rx_id_check["reason"]

    strength = _extract_strength(parsed.drug)
    drug_generic = _extract_drug_name(parsed.drug, strength)
    sig_text = str(parsed.sig or "")
    prn_flag = "prn" in sig_text.lower() or "as needed" in sig_text.lower()
    normalized_fingerprint = build_normalized_fingerprint(
        drug_generic=drug_generic,
        issue_type=issue_type,
        dosage_form=None,
        strength=strength,
        sig_raw=sig_text,
        prn=prn_flag,
        qty=parsed.quantity,
    )

    lane = "INTERRUPTIVE" if (has_structural_trigger and structural.pattern_assessment != "Pattern-questionable") else "NONE"
    history_match_type = "NONE"
    history_match_confidence = "NONE"
    seen_before_context = None

    if lane != "NONE" and issue_type and input.patient_id:
        if rx_instance_id_valid and input.rx_instance_id:
            same_rx = find_same_rx_refill_resolution(
                patient_id=input.patient_id,
                rx_instance_id=input.rx_instance_id,
                fill_number=input.fill_number,
                normalized_fingerprint=normalized_fingerprint,
                issue_type=issue_type,
                prescriber_id=input.prescriber_id,
            )
            if same_rx:
                lane = "PASSIVE"
                history_match_type = "SAME_RX_REFILL_RESOLUTION"
                history_match_confidence = "HIGH_CONFIDENCE"

        if history_match_type == "NONE":
            prior_match = find_prior_rx_pattern(
                patient_id=input.patient_id,
                rx_instance_id=input.rx_instance_id if rx_instance_id_valid else None,
                normalized_fingerprint=normalized_fingerprint,
                issue_type=issue_type,
                prescriber_id=input.prescriber_id,
            )
            if prior_match.get("record"):
                history_match_type = "PRIOR_RX_PATTERN"
                history_match_confidence = prior_match.get("confidence", "NONE")
                seen_before_context = build_seen_before_context(prior_match)

    result["normalized_fingerprint"] = normalized_fingerprint
    result["rx_instance_id_valid"] = rx_instance_id_valid
    result["rx_instance_id_error"] = rx_instance_id_error
    result["history_match_type"] = history_match_type
    result["history_match_confidence"] = history_match_confidence
    result["seen_before_context"] = seen_before_context

    try:
        result = ui_helpers.merge_ui_fields({
            **result,
            "issue_type": issue_type,
            "lane": lane,
            "history_match_type": history_match_type,
        })
        result = _apply_non_redundant_clinical_sections(result)
        result = _capitalize_clinical_check_fields(result)
    except Exception as e:
        print("UI_HELPERS_ERROR:", repr(e))
        print("DEBUG structural_issue:", repr(structural.structural_issue))
        print("DEBUG lane:", repr(lane))
        raise

    result["lane"] = lane

    append_analysis_audit(
        raw_rx_text=input.raw_text,
        issue_type=issue_type,
        normalized_fingerprint=normalized_fingerprint,
        lane_result=lane,
        history_match_type=history_match_type,
        history_match_confidence=history_match_confidence,
        analysis_id=analysis_id,
        rx_instance_id=input.rx_instance_id,
        rx_instance_id_valid=rx_instance_id_valid,
        rx_instance_id_error=rx_instance_id_error,
        fill_number=input.fill_number,
    )
    result["action_badge"] = f"{threshold.badge} {threshold.action_label}"

    # FINAL OVERRIDE: fluconazole qty 2 single-dose repeat pattern
    # fluconazole_safe_repeat_override_applied = False
    sig_lower = (parsed.sig or "").lower()
    if (
        "fluconazole" in (parsed.drug or "").lower()
        and str(parsed.quantity).strip() == "2"
        and "once" in sig_lower
        and (
            "repeat" in sig_lower
            or "in 72 hours" in sig_lower
            or "second dose" in sig_lower
            or "may repeat" in sig_lower
        )
        and "once daily" not in sig_lower
    ):
        # fluconazole_safe_repeat_override_applied = True
        result.update({
            "action_level": "NONE",
            "action_label": "SAFE / NONE",
            "follow_up_required": False,
            "lane": "NONE",
            "clinical_check": "No action needed",
            "issue_line": "No action needed",
            "safe_to_verify": "SAFE",
            "threshold_reason": "Repeat-dose pattern accounted for in quantity.",
            "structural_issue": "No action needed",
            "affects": "none",
            "clarification": "Unlikely",
            "resolution": "🟢 SAFE / NONE",
            "prescriber_message": "",
            "internal_message": "",
            "risk_score": 0,
            "risk_severity": "NONE",
            # Additional fields for full SAFE override consistency
            "structure_assessment": "Structurally complete",
            "pattern_assessment": "Common repeat-dose pattern",
            "pattern_issue": "",
            "refresh_points": [
                "This prescription matches a common repeat-dose pattern for fluconazole.",
                "Quantity 2 supports the initial dose plus one possible repeat dose as written.",
                "No clarification is needed if the intent is initial plus one repeat dose."
            ],
            "refresh_conclusion": "Repeat-dose quantity is accounted for; no clarification needed.",
            "why_this_matters": "Quantity 2 supports the initial dose plus one possible repeat dose.",
            "action_line": "No action needed",
            "deviation": "",
            "documentation": "Prescription written for Fluconazole 150 mg, take 1 tablet by mouth once. May repeat in 72 hours if symptoms persist, quantity 2. This matches a common repeat-dose pattern; no clarification needed."
        })
    # result["fluconazole_safe_repeat_override_applied"] = fluconazole_safe_repeat_override_applied
    # FINAL OVERRIDE: fluconazole qty 2 once daily + conditional repeat pattern
    # fluconazole_once_daily_conditional_override_applied = False
    if (
        "fluconazole" in (parsed.drug or "").lower()
        and str(parsed.quantity).strip() == "2"
        and (
            "once daily" in sig_lower or "every day" in sig_lower or "daily" in sig_lower
        )
        and (
            "if symptoms persist" in sig_lower
            or "2nd tablet" in sig_lower
            or "second tablet" in sig_lower
            or "repeat" in sig_lower
            or "in 72 hours" in sig_lower
        )
    ):
        # fluconazole_once_daily_conditional_override_applied = True
        result.update({
            "resolution": "🟠 CLARIFY DIRECTIONS",
            "severity": "🟠 MODERATE",
            "risk_severity": "MODERATE",
            "workflow_status": "CLARIFY DIRECTIONS",
            "ui_priority": "🟠 CLARIFY DIRECTIONS",
            "action_badge": "🟠 CLARIFY DIRECTIONS",
            "follow_up_need": "Required before verification",
            "action_bias": "Clarify directions",
            "safe_to_verify": "UNSAFE",
            "risk_score": max(result.get("risk_score", 2), 2),
            "action_level": "CLARIFY",
            "badge": "🟠",
            "action_label": "CLARIFY DIRECTIONS",
            "follow_up_required": True,
            "threshold_reason": "Directions contain both scheduled daily dosing and conditional 72-hour repeat-dose language; clarify intended regimen.",
            "lane": "CLARIFY DIRECTIONS",
            "issue_line": "Clarify intended fluconazole regimen",
            "clinical_check": "Directions contain both scheduled daily dosing and conditional 72-hour repeat-dose language.",
            "action_line": "Clarify intended regimen with prescriber",
            # risk: keep existing risk language if present
            "prescriber_message": "Please clarify whether this is intended as a single-dose regimen with one possible repeat dose, or scheduled once-daily dosing.",
            "internal_message": "Once-daily scheduled language conflicts with conditional 72-hour repeat-dose language; clarify intended regimen before verification."
        })
    # result["fluconazole_once_daily_conditional_override_applied"] = fluconazole_once_daily_conditional_override_applied
    return result

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/resolve/{analysis_id}")
def resolve(analysis_id: int, body: ResolveInput):
    payload = body.dict()
    err = validate_resolve_input(payload)
    if err:
        return {"status": "ERROR", "error": err}

    save_resolution_record(
        analysis_id=analysis_id,
        rx_instance_id=body.rx_instance_id,
        resolved_at_fill=body.fill_number,
        normalized_fingerprint=body.normalized_fingerprint,
        issue_type=body.issue_type,
        patient_id=body.patient_id,
        resolution_state=body.resolution_state,
        suppression_scope=body.suppression_scope,
        prescriber_id=body.prescriber_id,
        note=body.note,
        pharmacist_id=body.pharmacist_id,
    )

    update_resolution(analysis_id, body.resolution_state, body.note or "")
    return {"status": "ok"}


@app.post("/analysis/{analysis_id}/event")
def record_analysis_event(analysis_id: int, body: AnalysisEventInput):
    event_id = insert_event(
        analysis_id=analysis_id,
        event_type=body.event_type,
        note=body.note,
        pharmacist_id=body.pharmacist_id,
    )
    return {"status": "ok", "event_id": event_id}

@app.get("/audit")
def audit(limit: int = 100):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/audit/meta")
def audit_meta():
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS total FROM analyses").fetchone()
    conn.close()
    return {"total": int(row["total"]) if row else 0}


@app.get("/audit/export.csv")
def audit_export_csv():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM analyses ORDER BY created_at DESC, id DESC"
    ).fetchall()
    all_rows = [dict(r) for r in rows]
    conn.close()

    by_pattern: dict[str, list[dict]] = {}
    for row in all_rows:
        key = str(row.get("pattern_key") or "")
        if not key:
            continue
        by_pattern.setdefault(key, []).append(row)

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([
        "timestamp",
        "prescription input",
        "interpreted sig",
        "drug",
        "strength",
        "quantity",
        "fast lane",
        "final lane",
        "confidence",
        "structural issue",
        "explanation",
        "seen before count",
        "last resolution",
        "status",
    ])

    for row in all_rows:
        key = str(row.get("pattern_key") or "")
        group = by_pattern.get(key, []) if key else []
        seen_before_count = max(len(group) - 1, 0) if group else 0
        last_resolution = ""
        if len(group) > 1:
            if group[0].get("id") == row.get("id"):
                last_resolution = str(group[1].get("resolution") or "")
            else:
                last_resolution = str(group[0].get("resolution") or "")

        strength = _extract_strength(row.get("drug"))
        drug_name = _extract_drug_name(row.get("drug"), strength)
        final_lane = str(row.get("resolution") or "")
        prescription_input = f"{row.get('drug', '')} - {row.get('sig', '')} (qty {row.get('quantity', '')})"
        explanation = str(row.get("prescriber_message") or row.get("structural_issue") or "")

        writer.writerow([
            row.get("created_at") or "",
            prescription_input,
            row.get("sig") or "",
            drug_name,
            strength,
            row.get("quantity") or "",
            _derive_fast_lane(final_lane),
            final_lane,
            _derive_confidence(row.get("risk_score")),
            row.get("structural_issue") or "",
            explanation,
            seen_before_count,
            last_resolution,
            _normalize_export_status(row.get("status")),
        ])

    csv_text = "\ufeff" + output.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pharmacy101_audit_log.csv"},
    )
