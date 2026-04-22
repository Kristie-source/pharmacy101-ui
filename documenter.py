from models import DocumentationResult
from case_library import match_case_pattern
from structural import detect_structural_issue


def generate_documentation(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> DocumentationResult:
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        note = pattern.documentation_template.format(
            drug=drug,
            sig=sig,
            quantity=quantity,
        )
        return DocumentationResult(note=note)

    structural = detect_structural_issue(drug, sig, quantity, frequency)
    if structural.pattern_assessment == "Pattern-questionable":
        return DocumentationResult(
            note=(
                f"Prescription written for {drug}, {sig}, quantity {quantity}. "
                "Directions are structurally complete, but the regimen does not map cleanly to a common low-ambiguity use pattern for this medication. "
                "Clarification of intended use or treatment plan is recommended."
            )
        )

    return DocumentationResult(
        note=(
            f"Prescription written for {drug}, {sig}, quantity {quantity}. "
            "No documentation template available for this pattern yet."
        )
    )