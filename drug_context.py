from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


_DB_PATH = Path(__file__).with_name("drug_context_db.json")


def _load_db() -> dict[str, Any]:
    if not _DB_PATH.exists():
        return {"drugs": {}}
    with _DB_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"drugs": {}}


_DRUG_CONTEXT_DB = _load_db()


def _normalize_drug_name(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|units?)\b", " ", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", " ", text)
    text = re.sub(r"[^a-z ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compact_list(values: list[str], limit: int = 3) -> str:
    picked = [str(v).strip() for v in values if str(v).strip()][:limit]
    return "; ".join(picked)


def match_drug_context(drug_name: str) -> Optional[dict[str, Any]]:
    normalized = _normalize_drug_name(drug_name)
    if not normalized:
        return None

    drugs = _DRUG_CONTEXT_DB.get("drugs", {})
    if not isinstance(drugs, dict):
        return None

    for key, entry in drugs.items():
        aliases = entry.get("aliases", []) if isinstance(entry, dict) else []
        alias_tokens = [str(a).lower().strip() for a in aliases if str(a).strip()]
        if str(key).lower().strip() not in alias_tokens:
            alias_tokens.append(str(key).lower().strip())

        for alias in sorted(alias_tokens, key=len, reverse=True):
            if alias and re.search(rf"\b{re.escape(alias)}\b", normalized):
                return {
                    "key": str(key),
                    "drug": entry,
                    "matched_alias": alias,
                }
    return None


def build_compact_drug_context_block(drug_name: str) -> str:
    matched = match_drug_context(drug_name)
    if not matched:
        return ""

    entry = matched["drug"]
    caution_notes = entry.get("structural_caution_notes", [])
    caution_text = _compact_list(caution_notes, limit=1)

    lines = [
        "[DRUG_CONTEXT]",
        f"generic={entry.get('generic_name', '')}",
        f"brands={_compact_list(entry.get('brand_names', []), limit=3)}",
        f"class={entry.get('class', '')}",
        f"use_patterns={_compact_list(entry.get('common_use_patterns', []), limit=2)}",
        f"sig_structures={_compact_list(entry.get('common_sig_structures', []), limit=2)}",
        f"ambiguity_flags={_compact_list(entry.get('known_ambiguity_flags', []), limit=3)}",
        f"high_risk_clarify={_compact_list(entry.get('high_risk_clarification_areas', []), limit=3)}",
    ]
    if caution_text:
        lines.append(f"caution={caution_text}")
    lines.append("[/DRUG_CONTEXT]")
    return "\n".join(lines)
