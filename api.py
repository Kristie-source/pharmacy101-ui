from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import csv
import io
import re
from parser import parse_prescription_line
from structural import detect_structural_issue
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

app = FastAPI()
init_resolution_memory_tables()


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

    if "NONE" in lane:
        return False
    if affects not in {"instructions", "duration", "frequency"}:
        return False
    if not issue_text or issue_text.startswith("no obvious structural issue"):
        return False
    return True

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

@app.post("/analyze")
def analyze(input: PrescriptionInput):
    try:
        parsed = parse_prescription_line(input.raw_text)
    except ValueError as e:
        return {"status": "INVALID", "error": str(e)}

    structural = detect_structural_issue(
        parsed.drug, parsed.sig, parsed.quantity, parsed.frequency
    )
    has_structural_trigger = _has_structural_trigger(structural)

    # Intentional product boundary:
    # If no structural ambiguity is detected, classify as No Issue and do not
    # escalate from context/history signals to avoid duplicating DUR alerting.
    if not has_structural_trigger:
        structural.structural_issue = "No obvious structural issue detected."
        structural.affects = "none"
        structural.clarification = "Unlikely"
        structural.resolution = "🟢 NONE"

    safe_to_verify = get_safe_to_verify(structural)
    follow_up_need = get_follow_up_need(structural)
    severity = get_severity(structural)
    risk_score = get_risk_score(
        structural.resolution, safe_to_verify, follow_up_need, severity
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
        "resolution": structural.resolution,
        "drug_recognition_status": structural.drug_recognition_status,
        "drug_recognition_match": structural.drug_recognition_match,
        "safe_to_verify": safe_to_verify,
        "follow_up_need": follow_up_need,
        "severity": severity,
        "risk_score": risk_score,
        "ui_priority": get_ui_priority(risk_score),
        "action_bias": get_action_bias(structural.resolution),
        "override_risk": override_risk,
        "refresh_points": refresh.summary_points,
        "refresh_conclusion": refresh.conclusion,
        "documentation": doc.note,
        "prescriber_message": msg.prescriber_message,
        "internal_message": msg.internal_message,
        "drug_context_match": msg.drug_context_key,
        "source_ref": input.source_ref,
    }

    if debug_enabled:
        result["llm_prompt_text"] = msg.prompt_text
        result["drug_context_block"] = build_compact_drug_context_block(parsed.drug)

    pattern_key = build_pattern_key(parsed.drug, parsed.sig, parsed.quantity)
    result["pattern_key"] = pattern_key

    analysis_id = save_analysis({**result, "pattern_key": pattern_key})
    result["analysis_id"] = analysis_id
    result["history_summary"] = get_history_summary_by_pattern_key(pattern_key, analysis_id)

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

    lane = "INTERRUPTIVE" if has_structural_trigger else "NONE"
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
