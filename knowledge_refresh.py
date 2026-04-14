from models import KnowledgeResult
from case_library import match_case_pattern


def explain_pattern(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> KnowledgeResult:
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        # Format the refresh output into three clear parts for consistency:
        # 1) Common pattern
        # 2) Why this stands out
        # 3) Why quantity matters
        rp = getattr(pattern, "refresh_points", []) or []
        common = rp[0] if len(rp) > 0 else "No common pattern available."
        why_stands = rp[1] if len(rp) > 1 else "No distinguishing features recorded."
        why_quantity = pattern.refresh_conclusion or "No quantity-specific note available."

        summary_points = [
            f"Common pattern: {common}",
            f"Why this stands out: {why_stands}",
            f"Why quantity matters: {why_quantity}",
        ]

        return KnowledgeResult(
            summary_points=summary_points,
            conclusion="",
        )

    return KnowledgeResult(
        summary_points=["No drug-specific refresh pattern available yet."],
        conclusion="Knowledge refresh not available for this pattern yet.",
    )