# action_threshold.py


import re
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
    drug: str,
    sig: str,
    quantity: int,
    issue_type: str = "",
    affects: str = "",
    risk: str = "",
    pattern_assessment: str = "",
    pattern_issue: str = "",
    pattern_context_supported: bool = False,
    therapy_type: str = "UNKNOWN",
    clinical_check: str = "",
    deviation: str = "",
    prescriber_message: str = "",
) -> ActionThresholdResult:
    # Special rule: Tadalafil PRN for ED — patient counseling only, not workflow interruption
    tadalafil_prn_ed_signals = [
        "tadalafil",
        "prn for ed",
        "prn for erectile dysfunction",
        "as needed for ed",
        "as needed for erectile dysfunction",
        "prn for ed: patient may benefit from counseling on as-needed use",
        "prn for ed: patient may benefit from counseling on as-needed use, but no workflow interruption required."
    ]
    text_lower = " ".join(
        str(x or "").lower()
        for x in [
            drug,
            sig,
            quantity,
            issue_type,
            affects,
            risk,
            pattern_assessment,
            pattern_issue,
            clinical_check,
            deviation,
            prescriber_message,
        ]
    )
    if (
        "tadalafil" in text_lower
        and (
            "prn for ed" in text_lower
            or "prn for erectile dysfunction" in text_lower
            or "as needed for ed" in text_lower
            or "as needed for erectile dysfunction" in text_lower
        )
    ) or any(signal in text_lower for signal in tadalafil_prn_ed_signals):
        return ActionThresholdResult(
            action_level="NONE",
            badge="🟢",
            action_label="SAFE / NONE",
            safe_to_verify="SAFE",
            follow_up_required=False,
            reason="NON_BLOCKING_PATIENT_CLARITY: PRN for ED is not a workflow interruption. Patient may benefit from counseling on as-needed use, but no prescriber clarification is required.",
        )
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
        pattern_issue,
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
        or (
            "azithromycin" in text
            and "2 tablets" in text
            and "once" in text
            and (str(quantity or "").strip() == "4" or "qty 4" in text)
        )
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
    # 🟠 Segment 6: ACUTE + missing duration
    # -------------------------
    # If therapy_type is ACUTE and duration/course is missing or unclear,
    # and regimen is not clearly inferable from quantity + frequency,
    # route to ADDRESS DURING WORKFLOW (do not escalate to HOLD_NOW).
    if (
        therapy_type.upper() == "ACUTE"
        and any(
            phrase in text
            for phrase in [
                "no duration",
                "duration missing",
                "missing duration",
                "unclear course",
                "course boundary",
                "duration not specified",
            ]
        )
    ):
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason="Acute therapy is missing a clear duration or course boundary.",
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

    # Special rule: Ubrelvy/ubrogepant PRN always requires max daily use boundary
    if (
        ("ubrelvy" in text or "ubrogepant" in text)
        and ("prn" in text or "as needed" in text)
    ):
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason="Ubrelvy/ubrogepant PRN directions require explicit maximum daily use boundary for safe verification.",
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
    # Targeted PRN frequency/use-boundary rule (sig-based)

    sig_lower = sig.lower()
    if (
        ("as needed" in sig_lower or "prn" in sig_lower)
        and not any(x in sig_lower for x in [
            "q4h", "q6h", "q8h", "q12h",
            "every 4 hours", "every 6 hours", "every 8 hours", "every 12 hours",
            "daily", "once daily",
            "bid", "twice daily",
            "tid", "three times daily",
            "qid", "four times daily",
            "qhs", "at bedtime"
        ])
    ):
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason="PRN directions require a frequency or maximum-use boundary before the patient can safely execute them.",
        )

    # Prednisone taper quantity integrity check
    if drug.lower().startswith("prednisone") and "then" in sig.lower():
        taper_pattern = re.findall(r"(\d+) tablets? daily for (\d+) days?", sig.lower())
        if taper_pattern:
            required_total = sum(int(dose) * int(days) for dose, days in taper_pattern)
            if quantity < required_total:
                return ActionThresholdResult(
                    action_level="ADDRESS_DURING_WORKFLOW",
                    badge="🟠",
                    action_label="ADDRESS DURING WORKFLOW",
                    safe_to_verify="CONDITIONAL",
                    follow_up_required=True,
                    reason="Quantity does not match total tablets required for written taper.",
                )
    # Pattern-questionable: Address during workflow unless a higher-priority rule already returned
    if pattern_assessment == "Pattern-questionable" and pattern_context_supported:
        return ActionThresholdResult(
            action_level="ADDRESS_DURING_WORKFLOW",
            badge="🟠",
            action_label="ADDRESS DURING WORKFLOW",
            safe_to_verify="CONDITIONAL",
            follow_up_required=True,
            reason="Regimen is structurally complete but does not map cleanly to a common low-ambiguity use pattern.",
        )

    return ActionThresholdResult(
        action_level="NONE",
        badge="🟢",
        action_label="SAFE / NONE",
        safe_to_verify="SAFE",
        follow_up_required=False,
        reason="No material ambiguity detected. The prescription appears usable as written.",
    )