from dataclasses import dataclass
from typing import Optional
from case_library import match_case_pattern
from structural import detect_structural_issue
from drug_context import build_compact_drug_context_block, match_drug_context


@dataclass
class MessageResult:
    prescriber_message: str
    internal_message: str
    prompt_text: str = ""
    drug_context_key: Optional[str] = None


def _lane_token(resolution: str) -> str:
    normalized = str(resolution).upper()
    if "CLARIFY USE" in normalized:
        return "CLARIFY USE"
    if "COMPLETE" in normalized:
        return "COMPLETE"
    if "NONE" in normalized:
        return "NONE"
    return "CHALLENGE"


def _build_message_prompt(
    drug: str,
    sig: str,
    quantity: int,
    frequency: Optional[str],
    resolution: str,
    affects: str,
) -> tuple[str, Optional[str]]:
    context_block = build_compact_drug_context_block(drug)
    matched = match_drug_context(drug)
    context_key = matched["key"] if matched else None

    lines = [
        "You are generating a structural pharmacy clarification message.",
        "Focus on wording clarity, workflow safety, and ambiguity boundaries.",
        f"Drug: {drug}",
        f"SIG: {sig}",
        f"Quantity: {quantity}",
        f"Frequency: {frequency or 'unspecified'}",
        f"Resolution Lane: {resolution}",
        f"Primary Affect Area: {affects}",
    ]
    if context_block:
        lines.append(context_block)
    lines.append("Return concise, non-diagnostic workflow wording.")

    return "\n".join(lines), context_key


def generate_message(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> MessageResult:
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        prompt_text, context_key = _build_message_prompt(
            drug,
            sig,
            quantity,
            frequency,
            "CHALLENGE",
            "instructions",
        )
        return MessageResult(
            prescriber_message=pattern.prescriber_message,
            internal_message=pattern.internal_message,
            prompt_text=prompt_text,
            drug_context_key=context_key,
        )

    # If no known pattern, consult structural analysis to generate a message
    # that reflects the clarification level.
    structural = detect_structural_issue(drug, sig, quantity, frequency)
    lane = _lane_token(structural.resolution)
    prompt_text, context_key = _build_message_prompt(
        drug,
        sig,
        quantity,
        frequency,
        structural.resolution,
        structural.affects,
    )

    if lane == "NONE":
        prescriber_msg = "No message needed."
        internal_msg = "No clarification message needed."
    elif structural.pattern_assessment == "Pattern-questionable":
        prescriber_msg = "Please clarify the intended use or treatment plan for this regimen."
        internal_msg = "Structurally complete directions do not map cleanly to a common low-ambiguity use pattern; follow-up on intended treatment plan is recommended."
    elif lane == "CLARIFY USE":
        prescriber_msg = "This order may benefit from documentation of intent or indication."
        internal_msg = "Consider documenting clinical intent or indication."
    elif lane == "COMPLETE":
        prescriber_msg = "Please clarify intended directions based on current order details."
        internal_msg = "Order details may require clarification based on current directions."
    else:
        # Default to cautious approach for CHALLENGE or unknown values.
        prescriber_msg = "Please clarify intended directions based on current order details."
        internal_msg = "Order details may require clarification based on current directions."

    return MessageResult(
        prescriber_message=prescriber_msg,
        internal_message=internal_msg,
        prompt_text=prompt_text,
        drug_context_key=context_key,
    )