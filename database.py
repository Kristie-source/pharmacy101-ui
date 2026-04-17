import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path

DB_PATH = Path("pharmacy101.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            pharmacy_id TEXT DEFAULT 'default',
            pattern_key TEXT,
            drug TEXT NOT NULL,
            sig TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            frequency TEXT,
            resolution TEXT NOT NULL,
            risk_score INTEGER,
            structural_issue TEXT,
            prescriber_message TEXT,
            source_ref TEXT,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS sig_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_normalized TEXT NOT NULL,
            sig_normalized TEXT NOT NULL,
            quantity INTEGER,
            resolution TEXT,
            count INTEGER DEFAULT 1,
            last_seen TEXT,
            UNIQUE(drug_normalized, sig_normalized, quantity)
        );

        CREATE TABLE IF NOT EXISTS resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER REFERENCES analyses(id),
            resolved_at TEXT,
            resolution_type TEXT,
            notes TEXT
        );
    """)

    # Lightweight migration for existing databases.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
    if "pattern_key" not in columns:
        conn.execute("ALTER TABLE analyses ADD COLUMN pattern_key TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_pattern_key_created_at ON analyses(pattern_key, created_at)")

    conn.commit()
    conn.close()


def normalize_pattern_text(value: str) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"\s+", " ", text)

    # Normalize common unit variants.
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*gm\b", r"\1 g", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*g\b", r"\1 g", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*mg\b", r"\1 mg", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*mcg\b", r"\1 mcg", text)

    # Normalize common dosage-form variants.
    text = re.sub(r"\btabs?\b", "tablet", text)
    text = re.sub(r"\btablets\b", "tablet", text)

    # Normalize simple SIG shorthand.
    replacements = [
        (r"\bpo\b", "by mouth"),
        (r"\bprn\b", "as needed"),
        (r"\bbid\b", "twice daily"),
        (r"\btid\b", "three times daily"),
        (r"\bqid\b", "four times daily"),
        (r"\bqd\b", "daily"),
        (r"\bqhs\b", "nightly"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\bq\s*(\d+)\s*h\b", r"every \1 hours", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_pattern_key(drug: str, sig: str, quantity: int) -> str:
    drug_norm = normalize_pattern_text(drug)
    sig_norm = normalize_pattern_text(sig)
    return f"{drug_norm} | {sig_norm} | qty {quantity}"


def normalize_history_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if "resolv" in value or value in {"complete", "done", "closed"}:
        return "resolved"
    return "pending"

def save_analysis(data: dict) -> int:
    conn = get_connection()
    pattern_key = data.get("pattern_key") or build_pattern_key(
        data.get("drug", ""), data.get("sig", ""), data.get("quantity") or 0
    )
    cursor = conn.execute("""
        INSERT INTO analyses
        (created_at, pattern_key, drug, sig, quantity, frequency, resolution,
         risk_score, structural_issue, prescriber_message, source_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        pattern_key,
        data.get("drug"), data.get("sig"), data.get("quantity"),
        data.get("frequency"), data.get("resolution"),
        data.get("risk_score"), data.get("structural_issue"),
        data.get("prescriber_message"), data.get("source_ref"),
    ))
    analysis_id = cursor.lastrowid

    # Update pattern memory
    drug_norm = data.get("drug", "").lower().split()[0]
    sig_norm = data.get("sig", "").lower().strip()
    conn.execute("""
        INSERT INTO sig_patterns
            (drug_normalized, sig_normalized, quantity, resolution, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(drug_normalized, sig_normalized, quantity)
        DO UPDATE SET
            count = count + 1,
            last_seen = excluded.last_seen,
            resolution = excluded.resolution
    """, (
        drug_norm, sig_norm, data.get("quantity"),
        data.get("resolution"), datetime.utcnow().isoformat(),
    ))

    conn.commit()
    conn.close()
    return analysis_id

def get_similar_pattern(drug: str, sig: str, quantity: int):
    conn = get_connection()
    drug_norm = drug.lower().split()[0]
    sig_norm = sig.lower().strip()
    row = conn.execute("""
        SELECT * FROM sig_patterns
        WHERE drug_normalized = ?
        AND sig_normalized = ?
        ORDER BY count DESC LIMIT 1
    """, (drug_norm, sig_norm)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_history_summary_by_pattern_key(pattern_key: str, current_analysis_id: int | None = None) -> dict:
    conn = get_connection()
    if not pattern_key:
        conn.close()
        return {
            "pattern_key": "",
            "seen_before_count": 0,
            "last_resolution": None,
            "last_status": None,
            "last_seen_at": None,
        }

    total_row = conn.execute(
        "SELECT COUNT(*) AS total FROM analyses WHERE pattern_key = ?",
        (pattern_key,),
    ).fetchone()
    total = int(total_row["total"]) if total_row else 0

    last_row = None
    if current_analysis_id is not None:
        last_row = conn.execute(
            """
            SELECT resolution, status, created_at
            FROM analyses
            WHERE pattern_key = ? AND id != ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (pattern_key, current_analysis_id),
        ).fetchone()
    else:
        last_row = conn.execute(
            """
            SELECT resolution, status, created_at
            FROM analyses
            WHERE pattern_key = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (pattern_key,),
        ).fetchone()

    conn.close()

    seen_before_count = max(total - 1, 0) if current_analysis_id is not None else total
    return {
        "pattern_key": pattern_key,
        "seen_before_count": seen_before_count,
        "last_resolution": last_row["resolution"] if last_row else None,
        "last_status": normalize_history_status(last_row["status"]) if last_row else None,
        "last_seen_at": last_row["created_at"] if last_row else None,
    }

def update_resolution(analysis_id: int, resolution_type: str, notes: str = ""):
    conn = get_connection()
    conn.execute("""
        UPDATE analyses SET status = ? WHERE id = ?
    """, (resolution_type, analysis_id))
    conn.execute("""
        INSERT INTO resolutions (analysis_id, resolved_at, resolution_type, notes)
        VALUES (?, ?, ?, ?)
    """, (analysis_id, datetime.utcnow().isoformat(), resolution_type, notes))
    conn.commit()
    conn.close()

init_db()
