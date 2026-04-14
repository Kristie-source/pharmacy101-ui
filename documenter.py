from models import DocumentationResult
from case_library import match_case_pattern


def generate_documentation(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> DocumentationResult:
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        note = pattern.documentation_template.format(
            drug=drug,
            sig=sig,
            quantity=quantity,
        )
        return DocumentationResult(note=note)

    return DocumentationResult(
        note=(
            f"Prescription written for {drug}, {sig}, quantity {quantity}. "
            "No documentation template available for this pattern yet."
        )
    )