import re
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
        prescriber_msg = generate_ready_to_send_message(
            drug=drug,
            sig=sig,
            quantity=quantity,
            issue_text="",
    )
        internal_msg = "Clarify the specific dosing intent before relying on quantity alone."
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
def generate_ready_to_send_message(drug: str, sig: str, quantity: int | str, issue_text: str = "") -> str:
    drug_lower = drug.lower()
    sig_lower = sig.lower()
    issue_lower = issue_text.lower()
    


    if "once" in sig_lower and str(quantity).isdigit() and int(quantity) > 2:
        return (
            "The quantity exceeds a single-dose regimen. "
            "Please confirm if additional dosing is intended, such as repeat dosing or partner therapy."
        )

    # Migraine/triptan event-based PRN logic
    migraine_drugs = ["sumatriptan", "rizatriptan", "zolmitriptan", "naratriptan", "eletriptan"]
    event_based_terms = ["at onset", "onset of migraine", "may repeat", "for migraine"]
    has_migraine_drug = any(term in drug_lower for term in migraine_drugs)
    has_event_based = any(term in sig_lower for term in event_based_terms)
    has_may_repeat = "may repeat" in sig_lower
    # Look for repeat interval (e.g., "after 2 hours", "in 2 hours", "every 2 hours", "q2h", "2 hours")
    repeat_interval_pattern = r"(after|in|every|q) ?\d+ ?(hour|hr|hours|hrs)"
    has_repeat_interval = re.search(repeat_interval_pattern, sig_lower)
    # Look for max daily dose (e.g., "max 2 tablets", "maximum 2 tablets", "per day", "24 hours")
    has_max_daily = any(term in sig_lower for term in ["max", "maximum", "per day", "24 hours"])

    if has_migraine_drug and has_event_based and has_may_repeat and not has_repeat_interval and not has_max_daily:
        return (
            "Repeat dosing limits are incomplete. "
            "Please confirm the repeat interval and maximum daily dose."
        )

    if "metoprolol tartrate" in drug_lower and any(term in sig_lower for term in ["daily", "once daily", "qd"]):
        return (
            "The dosing schedule may not align with the intended formulation. "
            "Please confirm whether metoprolol tartrate once daily is intended or if a different formulation/frequency was meant."
        )


    # Suppress quantity mismatch for PRN NSAIDs and similar unless high-risk for overuse and max daily dose is missing
    prn_terms = ["prn", "as needed"]
    is_prn = any(term in sig_lower for term in prn_terms)
    nsaid_drugs = ["ibuprofen", "naproxen", "meloxicam", "celecoxib", "diclofenac", "ketorolac"]
    is_nsaid = any(drug_name in drug_lower for drug_name in nsaid_drugs)
    high_risk_overuse = ["oxycodone", "hydrocodone", "morphine", "tramadol", "acetaminophen", "codeine"]
    is_high_risk = any(drug_name in drug_lower for drug_name in high_risk_overuse)
    has_max_daily = any(term in sig_lower for term in ["max", "maximum", "per day", "24 hours"])

    if any(term in issue_lower for term in ["quantity mismatch", "qty mismatch", "quantity does not match", "math mismatch"]):
        if "ibuprofen" in drug_lower and any(term in sig_lower for term in ["prn", "as needed"]):
             return (
                "The quantity does not match the written directions and duration. "
                "Please confirm the intended quantity or treatment length."
        )
        # Suppress for PRN NSAIDs
        if is_prn and is_nsaid:
            return ""
        # Suppress for PRN non-high-risk drugs
        if is_prn and not is_high_risk:
            return ""
        # Only trigger for PRN high-risk drugs if max daily dose is missing
        if is_prn and is_high_risk and not has_max_daily:
            return (
                "As-needed dosing limits are incomplete. "
                "Please confirm the maximum daily dose or use limit."
            )
        # For scheduled (non-PRN) or high-risk PRN with max missing, show default message
       

    if any(term in issue_lower for term in ["missing duration", "duration missing", "treatment length"]):
        return (
            "Treatment duration is not specified. "
            "Please confirm the intended length of therapy."
        )

    if any(term in sig_lower for term in ["prn", "as needed"]) and not any(term in sig_lower for term in ["max", "maximum", "per day", "24 hours"]):
        return (
            "As-needed dosing limits are incomplete. "
            "Please confirm the maximum daily dose or use limit."
        )

    if any(term in issue_lower for term in ["conflicting", "multiple regimens", "scheduled and prn"]):
        return (
            "The directions contain conflicting use patterns. "
            "Please confirm the intended regimen so the patient receives one clear set of instructions."
        )

    if any(term in issue_lower for term in ["indication", "intent"]):
        return (
            "Indication is needed to confirm the intended dosing pattern. "
            "Please confirm what this medication is being used to treat."
        )

    return (
        "The directions are unclear as written. "
        "Please confirm the intended dosing instructions."
    )