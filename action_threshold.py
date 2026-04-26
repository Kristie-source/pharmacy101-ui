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
    quantity: Optional[str] = None,
    issue_type: Optional[str] = None,
    affects: Optional[str] = None,
    risk: Optional[str] = None,
    pattern_assessment: Optional[str] = None,
) -> ActionThresholdResult:
    """
    Converts a detected prescription issue into a real-world pharmacist action threshold.

    Core question:
    Can a pharmacist safely and defensibly verify this without adding unstated assumptions?
    """

    text = " ".join(
        str(x or "").lower()
        for x in [drug, sig, quantity, issue_type, affects, risk, pattern_assessment]
    )

    # -------------------------
    # 🔴 HOLD NOW / CHALLENGE
    # -------------------------
    hold_now_signals = [
        "wrong formulation",
        "tartrate once daily",
        "succinate twice daily",
        "dose mismatch",
        "quantity mismatch",
        "duration mismatch",
        "extra tablets",
        "extra doses",
        "unclear total dose",
        "unclear course",
        "course structure",
        "treatment intent unclear",
        "indication required",
        "cannot determine intended regimen",
        "not safely executable",
        "materially affects treatment",
        "may not provide adequate",
        "underdose",
        "overdose",
    ]

    if any(signal in text for signal in hold_now_signals):
        return ActionThresholdResult(
            action_level="HOLD_NOW",
            badge="🔴",
            action_label="HOLD NOW / CHALLENGE",
            safe_to_verify="UNSAFE",
            follow_up_required=True,
            reason=(
                "The prescription cannot be safely verified without adding an unstated "
                "assumption that may affect dose, duration, frequency, quantity, or treatment intent."
            ),
        )

    # Drug-specific hard stops
    if "metoprolol tartrate" in text and (
        "once daily" in text or "qd" in text or "daily" in text
    ):
        return ActionThresholdResult(
            action_level="HOLD_NOW",
            badge="🔴",
            action_label="HOLD NOW / CHALLENGE",
            safe_to_verify="UNSAFE",
            follow_up_required=True,
            reason=(
                "Metoprolol tartrate once daily may not provide adequate 24-hour blood pressure "
                "or heart rate control. Clarify formulation or dosing frequency before verification."
            ),
        )

    if "azithromycin" in text and "take 2 tablets once" in text and "qty 4" in text:
        return ActionThresholdResult(
            action_level="HOLD_NOW",
            badge="🔴",
            action_label="HOLD NOW / CHALLENGE",
            safe_to_verify="UNSAFE",
            follow_up_required=True,
            reason=(
                "Directions account for only 2 tablets, but quantity is 4. The extra tablets may reflect "
                "EPT, repeat dosing, or an error, so the intended regimen must be clarified."
            ),
        )

    # -------------------------
    # 🟠 ADDRESS DURING WORKFLOW
    # -------------------------
    workflow_signals = [
        "prn",
        "as needed",
        "missing max",
        "missing limit",
        "use limit",
        "confirm schedule",
        "clarify use",
        "episodic use",
        "ongoing scheduled use",
        "patient may misunderstand",
        "counseling needed",
    ]

    if any(signal in text for signal in workflow_signals):
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason=(
                "The prescription has a usability gap that should be clarified or documented during workflow, "
                "but it does not automatically require a hard stop unless dose, quantity, duration, or intent is unclear."
            ),
        )

    # -------------------------
    # 🟡 COMPLETE
    # -------------------------
    complete_signals = [
        "minor improvement",
        "optimize counseling",
        "complete through counseling",
        "administration detail",
        "better wording",
        "patient-friendly",
    ]

    if any(signal in text for signal in complete_signals):
        return ActionThresholdResult(
            action_level="COMPLETE",
            badge="🟡",
            action_label="COMPLETE",
            safe_to_verify="SAFE WITH COUNSELING",
            follow_up_required=False,
            reason=(
                "The prescription is usable as written. Minor wording improvements may help counseling, "
                "but pharmacist verification does not require prescriber clarification."
            ),
        )

    # -------------------------
    # 🟢 NONE
    # -------------------------
    return ActionThresholdResult(
        action_level="NONE",
        badge="🟢",
        action_label="NONE",
        safe_to_verify="SAFE",
        follow_up_required=False,
        reason="No material ambiguity detected. The prescription appears usable as written.",
    )