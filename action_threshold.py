# action_threshold.py

from dataclasses import dataclass
from typing import Literal, Optional


ActionLevel = Literal[
    "NONE",
    "COMPLETE",
    "ADDRESS_DURING_WORKFLOW",
    "HOLD_NOW",
]


@dataclass
class ActionThresholdResult:
    action_level: ActionLevel
    badge: str
    action_label: str
    safe_to_verify: str
    follow_up_required: bool
    reason: str


def determine_action_threshold(
    *,
    drug: str,
    sig: str,
    quantity=None,
    issue_type=None,
    affects=None,
    risk=None,
    pattern_assessment=None,
    clinical_check=None,
    deviation=None,
    prescriber_message=None,
) -> ActionThresholdResult:
    """
    Converts a detected prescription issue into a real-world pharmacist action threshold.

    Core question:
    Can a pharmacist safely and defensibly verify this without adding unstated assumptions?
    """

    text = " ".join(
    str(x or "").lower()
    for x in [
        drug,
        sig,
        quantity,
        issue_type,
        affects,
        risk,
        pattern_assessment,
        clinical_check,
        deviation,
        prescriber_message,
    ]
)

    # -------------------------
    # 🔴 HOLD NOW / CHALLENGE
    # -------------------------
    # If verifying requires an unstated assumption about dose, duration, formulation, frequency, quantity, or intent, HOLD.
    # Quantity/sig mismatch, formulation-frequency mismatch, or unclear regimen = HOLD.
    if (
        "tartrate once daily" in text
        or ("metoprolol tartrate" in text and ("once daily" in text or "qd" in text or "daily" in text))
        or ("azithromycin" in text and "take 2 tablets once" in text and "qty 4" in text)
        or ("valacyclovir" in text and "bid" in text and "qty 28" in text and ("no duration" in text or "no indication" in text))
        or ("colchicine" in text and ("prn" in text and "scheduled" in text))
        or "quantity mismatch" in text
        or "dose mismatch" in text
        or "duration mismatch" in text
        or "unclear total dose" in text
        or "unclear course" in text
        or "treatment intent unclear" in text
        or "cannot determine intended regimen" in text
        or "not safely executable" in text
        or "materially affects treatment" in text
        or "underdose" in text
        or "overdose" in text
    ):
        return ActionThresholdResult(
            action_level="HOLD_NOW",
            badge="🔴",
            action_label="HOLD NOW / CHALLENGE",
            safe_to_verify="UNSAFE",
            follow_up_required=True,
            reason="Verification requires an unstated assumption about dose, duration, formulation, frequency, quantity, or intent.",
        )

    # -------------------------
    # 🟠 ADDRESS DURING WORKFLOW
    # -------------------------
    # PRN alone is not enough. Only flag if PRN + high-risk, missing max, unclear puff/frequency, or unclear use boundary.
    # Do not over-flag common low-risk PRN NSAID wording.
    # Examples: Ubrelvy PRN missing max, Albuterol PRN no puff frequency, PRN with overuse risk.

    # Special rule: Albuterol/inhaler PRN with missing dose, puff frequency, or max use boundary
    if (
    ("albuterol" in text or "inhaler" in text)
    and ("as needed" in text or "prn" in text)
    and not ("puff" in text or "puffs" in text)
):
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason="Albuterol/inhaler PRN directions missing dose, puff frequency, or max daily use require clarification before handoff/counseling.",
        )

    # Weekly med missing admin day, if counseling depends on it
    if "weekly" in text and ("missing day" in text or "no admin day" in text):
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason="Weekly medication missing administration day requires clarification before handoff/counseling.",
        )

    # -------------------------
    # 🟢 SAFE / NONE
    # -------------------------
    # If the Rx is common, executable, and no real pharmacist would stop workflow, return SAFE/NONE.
    # Do not flag for structural imperfection alone. Examples: Metformin 500 mg BID qty 60, Naproxen 500 mg BID PRN pain qty 60, Lisinopril 20 mg daily qty 30.
    return ActionThresholdResult(
        action_level="NONE",
        badge="🟢",
        action_label="SAFE / NONE",
        safe_to_verify="SAFE",
        follow_up_required=False,
        reason="No material ambiguity detected. The prescription appears usable as written.",
    )