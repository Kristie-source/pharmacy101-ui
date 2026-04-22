from __future__ import annotations

import json
import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RegimenPatternAssessment:
    pattern_context_supported: bool
    pattern_assessment: str
    pattern_issue: str = ""
    risk_severity: str = "LOW"
    immediate_usability: str = "YES"
    workflow_status: str = "VERIFY AS ENTERED"
    resolution: str = "🟢 NONE"
    pattern_dispensing_risk: bool = False


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


def _has_explicit_duration(sig: str) -> bool:
    return bool(
        re.search(
            r"\bfor\s+\d+\s+(?:days?|weeks?|months?)\b",
            str(sig or "").lower(),
        )
    )


def _extract_duration_days(sig: str) -> Optional[int]:
    sig_lower = str(sig or "").lower()

    day_match = re.search(r"\bfor\s+(\d+)\s+days?\b", sig_lower)
    if day_match:
        return int(day_match.group(1))

    week_match = re.search(r"\bfor\s+(\d+)\s+weeks?\b", sig_lower)
    if week_match:
        return int(week_match.group(1)) * 7

    month_match = re.search(r"\bfor\s+(\d+)\s+months?\b", sig_lower)
    if month_match:
        return int(month_match.group(1)) * 30

    return None


def _sig_has_any_phrase(sig: str, phrases: list[str]) -> bool:
    sig_lower = str(sig or "").lower()
    return any(str(phrase).lower() in sig_lower for phrase in phrases)


def _regimen_matches(
    regimen: dict[str, Any],
    sig: str,
    quantity: int,
    frequency: Optional[str],
) -> bool:
    normalized_frequency = str(frequency or "").strip().lower()
    duration_days = _extract_duration_days(sig)
    has_duration = _has_explicit_duration(sig)

    frequency_in = [str(value).strip().lower() for value in regimen.get("frequency_in", []) if str(value).strip()]
    if frequency_in and normalized_frequency not in frequency_in:
        return False

    quantity_in = regimen.get("quantity_in")
    if isinstance(quantity_in, list) and quantity not in quantity_in:
        return False

    quantity_min = regimen.get("quantity_min")
    if quantity_min is not None and quantity < int(quantity_min):
        return False

    quantity_max = regimen.get("quantity_max")
    if quantity_max is not None and quantity > int(quantity_max):
        return False

    if regimen.get("requires_explicit_duration") and not has_duration:
        return False

    if regimen.get("disallow_explicit_duration") and has_duration:
        return False

    max_duration_days = regimen.get("max_duration_days")
    if max_duration_days is not None:
        if duration_days is None or duration_days > int(max_duration_days):
            return False

    if regimen.get("requires_prn") and not _sig_has_any_phrase(sig, ["prn", "as needed"]):
        return False

    if regimen.get("disallow_prn") and _sig_has_any_phrase(sig, ["prn", "as needed"]):
        return False

    required_phrases = regimen.get("sig_contains_any", [])
    if required_phrases and not _sig_has_any_phrase(sig, required_phrases):
        return False

    return True


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


def evaluate_regimen_pattern(
    drug_name: str,
    sig: str,
    quantity: int,
    frequency: Optional[str] = None,
) -> RegimenPatternAssessment:
    matched = match_drug_context(drug_name)
    if not matched:
        return RegimenPatternAssessment(
            pattern_context_supported=False,
            pattern_assessment="Pattern not evaluated",
        )

    entry = matched["drug"]
    low_ambiguity_regimens = entry.get("low_ambiguity_regimens", [])
    if not isinstance(low_ambiguity_regimens, list) or not low_ambiguity_regimens:
        return RegimenPatternAssessment(
            pattern_context_supported=False,
            pattern_assessment="Pattern not evaluated",
        )

    for regimen in low_ambiguity_regimens:
        if isinstance(regimen, dict) and _regimen_matches(regimen, sig, quantity, frequency):
            return RegimenPatternAssessment(
                pattern_context_supported=True,
                pattern_assessment="Pattern-consistent",
            )

    concern = str(entry.get("pattern_questionable_message", "")).strip()
    if not concern:
        common_patterns = entry.get("common_use_patterns", [])
        concern = (
            "The regimen is structurally complete, but it does not map cleanly to "
            f"common low-ambiguity use patterns for this medication ({_compact_list(common_patterns, limit=2)})."
        )

    severity = str(entry.get("pattern_questionable_severity", "MODERATE") or "MODERATE").upper()
    pattern_dispensing_risk = bool(entry.get("pattern_questionable_dispensing_risk", False))
    immediate_usability = "NO" if pattern_dispensing_risk else "YES"
    workflow_status = "HOLD NOW" if pattern_dispensing_risk else "Verified — Needs Follow-up"
    resolution = "🟠 CLARIFY USE" if pattern_dispensing_risk else "🔴 CHALLENGE"

    return RegimenPatternAssessment(
        pattern_context_supported=True,
        pattern_assessment="Pattern-questionable",
        pattern_issue=concern,
        risk_severity=severity,
        immediate_usability=immediate_usability,
        workflow_status=workflow_status,
        resolution=resolution,
        pattern_dispensing_risk=pattern_dispensing_risk,
    )


def build_compact_drug_context_block(drug_name: str) -> str:
    matched = match_drug_context(drug_name)
    if not matched:
        return ""

    entry = matched["drug"]
    caution_notes = entry.get("structural_caution_notes", [])
    caution_text = _compact_list(caution_notes, limit=1)
    regimen_names = [
        str(regimen.get("label", regimen.get("name", ""))).strip()
        for regimen in entry.get("low_ambiguity_regimens", [])
        if isinstance(regimen, dict)
    ]

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
    if regimen_names:
        lines.append(f"low_ambiguity_regimens={_compact_list(regimen_names, limit=3)}")
    if caution_text:
        lines.append(f"caution={caution_text}")
    lines.append("[/DRUG_CONTEXT]")
    return "\n".join(lines)
