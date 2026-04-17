"""
resolution_memory.py

Resolution memory + prior-pattern context for Pharmacy101.

Purpose:
- Remember how a structurally ambiguous prescription was resolved
- Suppress repeat interruptive alerts only for later fills of the SAME Rx
- Re-audit NEW prescriptions, while optionally showing prior-Rx context
- Keep an audit trail of analysis and resolution events

Notes:
- This module is intentionally conservative
- accepted_as_is is context only, never suppressing
- Missing/invalid rx_instance_id disables same-Rx suppression
"""

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Any

DB_PATH = "pharmacy101.db"

SUPPRESSING_STATES = frozenset({
    "intent_confirmed_sig_unchanged",
    "intentional_nonstandard",
})

CONTEXT_STATES = frozenset({
    "intent_confirmed_sig_unchanged",
    "intentional_nonstandard",
    "accepted_as_is",  # context only — never suppresses
})

VALID_RESOLUTION_STATES = frozenset({
    "structure_fixed",
    "intent_confirmed_sig_unchanged",
    "intentional_nonstandard",
    "accepted_as_is",
})

VALID_SUPPRESSION_SCOPES = frozenset({
    "PATIENT_ONLY",
    "PATIENT_PRESCRIBER",
})

RESOLUTION_STATE_LABELS = {
    "structure_fixed": "structure fixed",
    "intent_confirmed_sig_unchanged": "confirmed with MD",
    "intentional_nonstandard": "intentional/off-label",
    "accepted_as_is": "accepted as-is",
}

# Default staleness window.
# Older records can still be shown as context, but should not suppress.
DEFAULT_SUPPRESSION_STALE_DAYS = 90


# ---------------------------------------------------------------------------
# rx_instance_id validation
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PREFIX_NUMERIC_RE = re.compile(r"^[A-Za-z]+[-_]\d+$")


def validate_rx_instance_id(rx_instance_id: Optional[str]) -> dict:
    """
    Returns:
      {"valid": bool, "reason": None | "MISSING" | "BAD_FORMAT"}

    Valid formats:
    - UUID v1-v5
    - prefix+numeric such as RX-12345 or script_9981
    """
    if not rx_instance_id or not str(rx_instance_id).strip():
        return {"valid": False, "reason": "MISSING"}

    v = str(rx_instance_id).strip()
    if _UUID_RE.match(v) or _PREFIX_NUMERIC_RE.match(v):
        return {"valid": True, "reason": None}

    return {"valid": False, "reason": "BAD_FORMAT"}


# ---------------------------------------------------------------------------
# Fingerprint building
# ---------------------------------------------------------------------------

_TIMING_ALIASES = {
    "qd": "FREQ:1/DAY",
    "daily": "FREQ:1/DAY",
    "once daily": "FREQ:1/DAY",
    "bid": "FREQ:2/DAY",
    "twice daily": "FREQ:2/DAY",
    "tid": "FREQ:3/DAY",
    "three times daily": "FREQ:3/DAY",
    "qid": "FREQ:4/DAY",
    "four times daily": "FREQ:4/DAY",
}


def _normalize_text(value: Optional[str], fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip().lower()
    return text if text else fallback


def _normalize_drug_generic(drug_generic: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", _normalize_text(drug_generic, "unknown-drug"))


def _normalize_strength(strength: Optional[str]) -> str:
    s = _normalize_text(strength, "unknown-strength")
    s = s.replace(" gm", " g").replace("mg.", "mg")
    return s


def _normalize_timing(sig_raw: Optional[str]) -> str:
    if not sig_raw:
        return "UNKNOWN_TIMING"

    s = str(sig_raw).strip().lower()

    # Prefer more specific phrases (e.g., "three times daily") over generic "daily".
    for alias, normalized in sorted(_TIMING_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", s):
            return normalized

    # q8h / q12h / q6h patterns
    m = re.search(r"q(\d+(?:\.\d+)?)h", s)
    if m:
        hours = float(m.group(1))
        if hours > 0:
            return f"FREQ:{24 / hours:g}/DAY"

    # every 8 hours / every 12 hours patterns
    m = re.search(r"every\s+(\d+(?:\.\d+)?)\s*hours?", s)
    if m:
        hours = float(m.group(1))
        if hours > 0:
            return f"FREQ:{24 / hours:g}/DAY"

    return "UNKNOWN_TIMING"


def _qty_bucket(issue_type: str, qty: Optional[float]) -> str:
    """
    For some issue types, exact qty matters more than buckets.
    """
    if qty is None:
        return "QTY:UNK"

    try:
        qty_val = float(qty)
    except Exception:
        return "QTY:UNK"

    if issue_type == "ACUTE_DRUG_CHRONIC_QTY":
        return f"QTY:EXACT:{int(qty_val)}"

    if qty_val <= 7:
        return "QTY:0-7"
    if qty_val <= 30:
        return "QTY:8-30"
    if qty_val <= 90:
        return "QTY:31-90"
    return "QTY:91+"


def build_normalized_fingerprint(
    drug_generic: str,
    issue_type: str,
    dosage_form: Optional[str],
    strength: Optional[str],
    sig_raw: Optional[str],
    prn: bool,
    qty: Optional[float],
) -> str:
    """
    Produces a 7-part fingerprint string.

    Format:
      D:<drug>|I:<issue>|F:<form>|S:<strength>|T:<timing>|P:<PRN|SCHEDULED>|Q:<qty>
    """
    d = _normalize_drug_generic(drug_generic)
    i = str(issue_type or "").strip().upper()
    f = _normalize_text(dosage_form, "unknown-form")
    s = _normalize_strength(strength)
    t = _normalize_timing(sig_raw)
    p = "PRN" if prn else "SCHEDULED"
    q = _qty_bucket(i, qty)

    return f"D:{d}|I:{i}|F:{f}|S:{s}|T:{t}|P:{p}|Q:{q}"


_REQUIRED_FP_KEYS = frozenset({"D", "I", "F", "S", "T", "P", "Q"})


def is_full_fingerprint(fp: Optional[str]) -> bool:
    if not fp:
        return False

    parts = str(fp).split("|")
    if len(parts) != 7:
        return False

    keys = set()
    for part in parts:
        idx = part.find(":")
        if idx > 0:
            keys.add(part[:idx])

    return _REQUIRED_FP_KEYS.issubset(keys)


def _parse_fp_map(fp: str) -> dict:
    result = {}
    for part in str(fp).split("|"):
        idx = part.find(":")
        if idx > 0:
            result[part[:idx]] = part[idx + 1:]
    return result


def _timing_to_daily_rate(timing_value: str) -> Optional[float]:
    m = re.match(r"^FREQ:(\d+(?:\.\d+)?)/DAY$", timing_value, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _timing_similar(a: str, b: str) -> bool:
    if a == b:
        return True

    da = _timing_to_daily_rate(a)
    db = _timing_to_daily_rate(b)

    if da is None or db is None:
        return False

    return abs(da - db) < 0.01  # TID == q8h


def _qty_rank(qty_value: str) -> Optional[int]:
    return {
        "QTY:0-7": 0,
        "QTY:8-30": 1,
        "QTY:31-90": 2,
        "QTY:91+": 3,
    }.get(qty_value)


def _qty_similar(a: str, b: str) -> bool:
    if a == b:
        return True

    # exact qty should stay exact
    if a.startswith("QTY:EXACT:") or b.startswith("QTY:EXACT:"):
        return a == b

    ra = _qty_rank(a)
    rb = _qty_rank(b)

    if ra is None or rb is None:
        return False

    return abs(ra - rb) <= 1  # adjacent buckets allowed


def _strength_equal(a: str, b: str) -> bool:
    """
    Conservative rule:
    - exact match = suppress eligible
    - mismatch = do not suppress
    """
    return a == b


def fingerprints_similar(fp_a: str, fp_b: str, allow_context_looser: bool = False) -> bool:
    """
    Matching rules:
    - strict on drug_generic, issue_type, prn
    - timing similarity allowed (TID == q8h)
    - qty similarity allowed (adjacent buckets)
    - strength must match for suppression; for context we can allow looser matching
    - dosage form is metadata, not primary gate
    """
    a = _parse_fp_map(fp_a)
    b = _parse_fp_map(fp_b)

    if a.get("I") != b.get("I"):
        return False
    if a.get("D") != b.get("D"):
        return False
    if a.get("P") != b.get("P"):
        return False

    if not _timing_similar(a.get("T", ""), b.get("T", "")):
        return False
    if not _qty_similar(a.get("Q", ""), b.get("Q", "")):
        return False

    if allow_context_looser:
        return True

    return _strength_equal(a.get("S", ""), b.get("S", ""))


def _triad_low_confidence_match(
    fp_record: str,
    fp_current: str,
    issue_record: str,
    issue_current: str,
) -> bool:
    """
    Fallback for incomplete fingerprints.
    Never used for suppression.
    Context only.
    """
    a = _parse_fp_map(fp_record)
    b = _parse_fp_map(fp_current)

    if issue_record != issue_current:
        return False
    if not a.get("D") or not b.get("D"):
        return False
    if not a.get("P") or not b.get("P"):
        return False

    return a["D"] == b["D"] and a["P"] == b["P"]


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def init_resolution_memory_tables() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS resolution_memory (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id             INTEGER NOT NULL,
            rx_instance_id          TEXT NOT NULL,
            resolved_at_fill        INTEGER NOT NULL DEFAULT 0,
            created_at              TEXT NOT NULL,
            normalized_fingerprint  TEXT NOT NULL,
            issue_type              TEXT NOT NULL,
            patient_id              TEXT NOT NULL,
            prescriber_id           TEXT,
            resolution_state        TEXT NOT NULL,
            suppression_scope       TEXT NOT NULL DEFAULT 'PATIENT_ONLY',
            note                    TEXT,
            pharmacist_id           TEXT
        );

        CREATE TABLE IF NOT EXISTS resolution_audit (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id             INTEGER NOT NULL,
            rx_instance_id          TEXT NOT NULL,
            resolved_at_fill        INTEGER NOT NULL DEFAULT 0,
            created_at              TEXT NOT NULL,
            normalized_fingerprint  TEXT NOT NULL,
            issue_type              TEXT NOT NULL,
            patient_id              TEXT NOT NULL,
            prescriber_id           TEXT,
            resolution_state        TEXT NOT NULL,
            suppression_scope       TEXT NOT NULL,
            note                    TEXT,
            pharmacist_id           TEXT
        );

        CREATE TABLE IF NOT EXISTS analysis_audit (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id              INTEGER,
            rx_instance_id           TEXT,
            rx_instance_id_valid     INTEGER,
            rx_instance_id_error     TEXT,
            fill_number              INTEGER NOT NULL DEFAULT 0,
            created_at               TEXT NOT NULL,
            raw_rx_text              TEXT,
            issue_type               TEXT,
            normalized_fingerprint   TEXT,
            lane_result              TEXT,
            history_match_type       TEXT NOT NULL DEFAULT 'NONE',
            history_match_confidence TEXT NOT NULL DEFAULT 'NONE',
            pharmacist_action        TEXT
        );
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Audit / persistence helpers
# ---------------------------------------------------------------------------

def save_resolution_record(
    analysis_id: int,
    rx_instance_id: str,
    resolved_at_fill: int,
    normalized_fingerprint: str,
    issue_type: str,
    patient_id: str,
    resolution_state: str,
    suppression_scope: str = "PATIENT_ONLY",
    prescriber_id: Optional[str] = None,
    note: Optional[str] = None,
    pharmacist_id: Optional[str] = None,
) -> int:
    now = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """
        INSERT INTO resolution_memory (
            analysis_id, rx_instance_id, resolved_at_fill, created_at,
            normalized_fingerprint, issue_type, patient_id, prescriber_id,
            resolution_state, suppression_scope, note, pharmacist_id
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            analysis_id,
            rx_instance_id,
            resolved_at_fill,
            now,
            normalized_fingerprint,
            issue_type,
            patient_id,
            prescriber_id,
            resolution_state,
            suppression_scope,
            note,
            pharmacist_id,
        ),
    )
    record_id = cur.lastrowid

    conn.execute(
        """
        INSERT INTO resolution_audit (
            analysis_id, rx_instance_id, resolved_at_fill, created_at,
            normalized_fingerprint, issue_type, patient_id, prescriber_id,
            resolution_state, suppression_scope, note, pharmacist_id
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            analysis_id,
            rx_instance_id,
            resolved_at_fill,
            now,
            normalized_fingerprint,
            issue_type,
            patient_id,
            prescriber_id,
            resolution_state,
            suppression_scope,
            note,
            pharmacist_id,
        ),
    )
    conn.commit()
    conn.close()
    return record_id


def append_analysis_audit(
    raw_rx_text: str,
    issue_type: Optional[str],
    normalized_fingerprint: Optional[str],
    lane_result: str,
    history_match_type: str = "NONE",
    history_match_confidence: str = "NONE",
    analysis_id: Optional[int] = None,
    rx_instance_id: Optional[str] = None,
    rx_instance_id_valid: bool = False,
    rx_instance_id_error: Optional[str] = None,
    fill_number: int = 0,
    pharmacist_action: Optional[str] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO analysis_audit (
            analysis_id, rx_instance_id, rx_instance_id_valid,
            rx_instance_id_error, fill_number, created_at,
            raw_rx_text, issue_type, normalized_fingerprint,
            lane_result, history_match_type, history_match_confidence,
            pharmacist_action
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            analysis_id,
            rx_instance_id,
            int(rx_instance_id_valid),
            rx_instance_id_error,
            fill_number,
            now,
            raw_rx_text,
            issue_type,
            normalized_fingerprint,
            lane_result,
            history_match_type,
            history_match_confidence,
            pharmacist_action,
        ),
    )
    conn.commit()
    conn.close()


def update_analysis_pharmacist_action(analysis_id: int, pharmacist_action: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE analysis_audit
        SET pharmacist_action = ?
        WHERE analysis_id = ?
        """,
        (pharmacist_action, analysis_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Internal read helpers
# ---------------------------------------------------------------------------

def _load_patient_records(patient_id: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM resolution_memory
        WHERE patient_id = ?
        ORDER BY created_at DESC
        """,
        (patient_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _scope_ok(record: dict, prescriber_id: Optional[str]) -> bool:
    if record.get("suppression_scope") == "PATIENT_PRESCRIBER":
        return bool(
            record.get("prescriber_id")
            and prescriber_id
            and record.get("prescriber_id") == prescriber_id
        )
    return True


def _is_stale(created_at: Optional[str], stale_days: int = DEFAULT_SUPPRESSION_STALE_DAYS) -> bool:
    if not created_at:
        return True

    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return True

    now = datetime.utcnow()
    # normalize away timezone info if needed
    if created_dt.tzinfo is not None:
        created_dt = created_dt.astimezone().replace(tzinfo=None)

    return created_dt < (now - timedelta(days=stale_days))


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def find_same_rx_refill_resolution(
    patient_id: str,
    rx_instance_id: str,
    fill_number: int,
    normalized_fingerprint: str,
    issue_type: str,
    prescriber_id: Optional[str] = None,
    stale_days: int = DEFAULT_SUPPRESSION_STALE_DAYS,
) -> Optional[dict]:
    """
    Suppression lookup for SAME Rx ONLY.

    Returns a matching suppressing record only if:
    - rx_instance_id is valid
    - current fingerprint is full
    - same patient
    - same rx_instance_id
    - later fill than resolved_at_fill
    - resolution_state is suppressing
    - not stale
    - same issue_type
    - fingerprints are similar
    - scope check passes
    """
    id_check = validate_rx_instance_id(rx_instance_id)
    if not id_check["valid"]:
        return None

    if not is_full_fingerprint(normalized_fingerprint):
        return None

    for record in _load_patient_records(patient_id):
        if record.get("resolution_state") not in SUPPRESSING_STATES:
            continue
        if _is_stale(record.get("created_at"), stale_days=stale_days):
            continue
        if not validate_rx_instance_id(record.get("rx_instance_id")).get("valid"):
            continue
        if record.get("rx_instance_id") != rx_instance_id:
            continue
        if record.get("issue_type") != issue_type:
            continue
        if fill_number <= int(record.get("resolved_at_fill", 0)):
            continue
        if not is_full_fingerprint(record.get("normalized_fingerprint")):
            continue
        if not fingerprints_similar(
            record.get("normalized_fingerprint", ""),
            normalized_fingerprint,
            allow_context_looser=False,
        ):
            continue
        if not _scope_ok(record, prescriber_id):
            continue
        return record

    return None


def find_prior_rx_pattern(
    patient_id: str,
    rx_instance_id: Optional[str],
    normalized_fingerprint: str,
    issue_type: str,
    prescriber_id: Optional[str] = None,
    stale_days: int = DEFAULT_SUPPRESSION_STALE_DAYS,
) -> dict:
    """
    Context-only lookup across DIFFERENT Rx instances.

    Never suppresses.

    Returns:
      {
        "record": dict | None,
        "confidence": "HIGH_CONFIDENCE" | "LOW_CONFIDENCE" | "NONE",
        "stale": bool,
        "prior_match_count": int,
      }
    """
    records = [
        r for r in _load_patient_records(patient_id)
        if r.get("resolution_state") in CONTEXT_STATES
        and r.get("rx_instance_id") != rx_instance_id
        and _scope_ok(r, prescriber_id)
    ]

    high_conf_matches = []
    low_conf_matches = []

    for record in records:
        fp_record = record.get("normalized_fingerprint", "")
        if (
            is_full_fingerprint(fp_record)
            and is_full_fingerprint(normalized_fingerprint)
            and fingerprints_similar(fp_record, normalized_fingerprint, allow_context_looser=True)
        ):
            high_conf_matches.append(record)

    if high_conf_matches:
        top = high_conf_matches[0]
        return {
            "record": top,
            "confidence": "HIGH_CONFIDENCE",
            "stale": _is_stale(top.get("created_at"), stale_days=stale_days),
            "prior_match_count": len(high_conf_matches),
        }

    for record in records:
        if _triad_low_confidence_match(
            record.get("normalized_fingerprint", ""),
            normalized_fingerprint,
            record.get("issue_type", ""),
            issue_type,
        ):
            low_conf_matches.append(record)

    if low_conf_matches:
        top = low_conf_matches[0]
        return {
            "record": top,
            "confidence": "LOW_CONFIDENCE",
            "stale": _is_stale(top.get("created_at"), stale_days=stale_days),
            "prior_match_count": len(low_conf_matches),
        }

    return {
        "record": None,
        "confidence": "NONE",
        "stale": False,
        "prior_match_count": 0,
    }


# ---------------------------------------------------------------------------
# Seen-before context builder
# ---------------------------------------------------------------------------

def build_seen_before_context(prior_match: dict) -> Optional[dict]:
    """
    Builds the output block used by /analyze for NEW Rx prior-pattern context.

    Does NOT affect suppression.
    """
    record = prior_match.get("record")
    confidence = prior_match.get("confidence", "NONE")
    stale = bool(prior_match.get("stale", False))
    prior_match_count = int(prior_match.get("prior_match_count", 0))

    if not record or confidence == "NONE":
        return None

    resolution_state = record.get("resolution_state")
    label = RESOLUTION_STATE_LABELS.get(resolution_state, resolution_state or "resolved")
    created_at = record.get("created_at")
    date_str = (created_at or "")[:10] if created_at else "unknown date"
    note = record.get("note") or ""

    def _norm_display_text(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(text or "").strip().lower()).strip()

    if prior_match_count > 1:
        display = f"Seen {prior_match_count} times before on prior Rx — {label} on {date_str}"
    else:
        display = f"Seen before on prior Rx — {label} on {date_str}"

    if note:
        normalized_note = _norm_display_text(note)
        normalized_label = _norm_display_text(label)
        if normalized_note and normalized_note != normalized_label:
            display += f" ({note})"

    if stale:
        display += " [older resolution]"
    if confidence == "LOW_CONFIDENCE":
        display += " [LOW_CONFIDENCE match]"

    return {
        "source": "PRIOR_RX",
        "resolution_state": resolution_state,
        "resolution_label": label,
        "last_resolved_at": created_at,
        "note": note or None,
        "confidence": confidence,
        "stale": stale,
        "prior_match_count": prior_match_count,
        "display": display,
    }


# ---------------------------------------------------------------------------
# Input validation for /resolve endpoint
# ---------------------------------------------------------------------------

def validate_resolve_input(body: dict) -> Optional[str]:
    """
    Returns an error string if invalid, otherwise None.
    """
    state = body.get("resolution_state", "")
    if state not in VALID_RESOLUTION_STATES:
        return f"Invalid resolution_state: {state!r}"

    if state == "accepted_as_is" and not str(body.get("note") or "").strip():
        return "note is required when resolution_state is accepted_as_is"

    scope = body.get("suppression_scope", "PATIENT_ONLY")
    if scope not in VALID_SUPPRESSION_SCOPES:
        return f"Invalid suppression_scope: {scope!r}"

    id_check = validate_rx_instance_id(body.get("rx_instance_id"))
    if not id_check["valid"]:
        return f"Invalid rx_instance_id: {id_check['reason']}"

    if not str(body.get("patient_id") or "").strip():
        return "patient_id is required"

    if not str(body.get("issue_type") or "").strip():
        return "issue_type is required"

    if not str(body.get("normalized_fingerprint") or "").strip():
        return "normalized_fingerprint is required"

    return None