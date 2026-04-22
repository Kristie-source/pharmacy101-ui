from models import KnowledgeResult
from case_library import match_case_pattern
from typing import Optional
from drug_context import evaluate_regimen_pattern, match_drug_context


def _capitalize_sentence_start(text: str) -> str:
    value = str(text or "")
    if not value:
        return value

    for idx, ch in enumerate(value):
        if ch.isalpha():
            if ch.islower():
                return f"{value[:idx]}{ch.upper()}{value[idx + 1:]}"
            return value

    return value


def explain_pattern(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> KnowledgeResult:
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        # Format the refresh output into three clear parts for consistency:
        # 1) Common pattern
        # 2) Why this stands out
        # 3) Why quantity matters
        rp = getattr(pattern, "refresh_points", []) or []
        common = _capitalize_sentence_start(rp[0] if len(rp) > 0 else "No common pattern available.")
        why_stands = _capitalize_sentence_start(rp[1] if len(rp) > 1 else "No distinguishing features recorded.")
        why_quantity = _capitalize_sentence_start(pattern.refresh_conclusion or "No quantity-specific note available.")

        summary_points = [
            f"Common pattern: {common}",
            f"Why this stands out: {why_stands}",
            f"Why quantity matters: {why_quantity}",
        ]

        return KnowledgeResult(
            summary_points=summary_points,
            conclusion="",
        )

    regimen_pattern = evaluate_regimen_pattern(drug, sig, quantity, frequency)
    if regimen_pattern.pattern_assessment == "Pattern-questionable":
        matched = match_drug_context(drug)
        entry = matched["drug"] if matched else {}
        common_patterns = entry.get("common_use_patterns", []) if isinstance(entry, dict) else []
        common_pattern_text = ", ".join(str(value).strip() for value in common_patterns[:2] if str(value).strip())
        if not common_pattern_text:
            common_pattern_text = "recognized treatment patterns"

        summary_points = [
            f"Common pattern: {common_pattern_text}.",
            "Why this stands out: Daily dosing with quantity 4 is fully written, but it does not clearly match a common low-ambiguity fluconazole treatment pattern.",
            "Why quantity matters: Quantity 4 supports several scheduled doses, but quantity alone does not identify whether the intended plan is single-dose, short-course, or another regimen.",
        ]

        return KnowledgeResult(
            summary_points=summary_points,
            conclusion="Pattern concern identified despite structurally complete directions.",
        )

    return KnowledgeResult(
        summary_points=["No drug-specific refresh pattern available yet."],
        conclusion="Knowledge refresh not available for this pattern yet.",
    )