from dataclasses import dataclass
from typing import Optional
from case_library import match_case_pattern
from structural import detect_structural_issue


@dataclass
class MessageResult:
    prescriber_message: str
    internal_message: str


def _lane_token(resolution: str) -> str:
    normalized = str(resolution).upper()
    if "CLARIFY USE" in normalized:
        return "CLARIFY USE"
    if "COMPLETE" in normalized:
        return "COMPLETE"
    if "NONE" in normalized:
        return "NONE"
    return "CHALLENGE"


def generate_message(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> MessageResult:
    pattern = match_case_pattern(drug, sig, quantity, frequency)

    if pattern:
        return MessageResult(
            prescriber_message=pattern.prescriber_message,
            internal_message=pattern.internal_message,
        )

    # If no known pattern, consult structural analysis to generate a message
    # that reflects the clarification level.
    structural = detect_structural_issue(drug, sig, quantity, frequency)
    lane = _lane_token(structural.resolution)

    if lane == "NONE":
        prescriber_msg = "No message needed."
        internal_msg = "No clarification message needed."
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
    )