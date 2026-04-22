"""Simple test cases for Pharmacy101.

Each case is a simple dictionary containing `drug`, `sig`, and `quantity`.
The `run_test_cases` function loops through the list and runs the same
processing logic used in `app.py` for each case, printing clear output.

Validation rule clarity:
- A valid shorthand input must include drug name, required qualifier when needed,
    strength, explicit dose amount in SIG, usable frequency, and quantity.
- Invalid examples:
    - Metoprolol tartrate 50 mg qd
    - Lisinopril 10 mg qd qty 30
- Corrected valid examples:
    - Metoprolol tartrate 50 mg 1t po qd (qty 30) -> FLAG
    - Lisinopril 10 mg 1t po qd (qty 30) -> VERIFY AS ENTERED
"""

from parser import parse_prescription_line
from structural import detect_structural_issue
from knowledge_refresh import explain_pattern
from documenter import generate_documentation
from messager import generate_message


def _lane_token(resolution: str) -> str:
    normalized = str(resolution).upper()
    if "CLARIFY USE" in normalized:
        return "CLARIFY USE"
    if "COMPLETE" in normalized:
        return "COMPLETE"
    if "NONE" in normalized:
        return "NONE"
    return "CHALLENGE"


def get_action_bias(resolution: str) -> str:
    lane = _lane_token(resolution)
    if lane == "CHALLENGE":
        return "Question pattern"
    if lane == "CLARIFY USE":
        return "Clarify patient use"
    if lane == "COMPLETE":
        return "Clarify missing instruction"
    return "No action needed"


def get_follow_up_need(structural: object) -> str:
    lane = _lane_token(structural.resolution)
    safe_to_verify = get_safe_to_verify(structural)
    if lane == "NONE":
        return "🟢 NO FOLLOW-UP NEEDED"
    if safe_to_verify == "🔴 UNSAFE":
        return "🔴 REQUIRED BEFORE VERIFY"
    return "🟡 MESSAGE RECOMMENDED"


def get_safe_to_verify(structural: object) -> str:
    lane = _lane_token(structural.resolution)
    structural_text = structural.structural_issue.lower()
    if lane in ["COMPLETE", "CLARIFY USE"]:
        return "🔴 UNSAFE"
    elif lane == "CHALLENGE" and (
        "implies" in structural_text
        or "imply" in structural_text
        or "uncertainty about the intended course structure" in structural_text
    ):
        return "🔴 UNSAFE"
    else:
        return "🟢 SAFE"


def get_severity(structural: object) -> str:
    lane = _lane_token(structural.resolution)
    if lane in ["COMPLETE", "CLARIFY USE"]:
        # Special case: Non-daily dosing ambiguity should be MODERATE severity
        if "Non-daily dosing" in structural.structural_issue:
            return "🟡 MODERATE"
        return "🔴 HIGH"
    elif lane == "CHALLENGE":
        structural_text = structural.structural_issue.lower()
        if "quantity and directions imply an extended course, but no duration or treatment context is stated" in structural_text:
            return "🔴 HIGH"
        if (
            "quantity implies an extended course at" in structural_text
            or "uncertainty about the intended course structure" in structural_text
        ):
            return "🟡 MODERATE"
        if "implies an unusually long course" in structural_text:
            return "🔴 HIGH"
        if "implies" in structural_text:
            return "🔴 HIGH"
        return "🟡 MODERATE"
    else:
        return "🟢 LOW"


def get_risk_score(resolution: str, safe_to_verify: str, clarification_req: str, severity: str) -> int:
    lane = _lane_token(resolution)
    if lane == "NONE":
        return 0

    score = 0
    if lane == "CHALLENGE":
        score += 30
    elif lane == "CLARIFY USE":
        score += 25
    elif lane == "COMPLETE":
        score += 15

    if "UNSAFE" in safe_to_verify:
        score += 30

    if "REQUIRED" in clarification_req:
        score += 25
    elif "RECOMMENDED" in clarification_req:
        score += 10

    if "HIGH" in severity:
        score += 15
    elif "MODERATE" in severity:
        score += 8

    return min(score, 100)


def get_ui_priority(risk_score: int) -> str:
    if risk_score >= 80:
        return "🔴 STOP"
    if risk_score >= 50:
        return "🟠 REVIEW USE"
    if risk_score >= 20:
        return "🟡 CLARIFY"
    return "🟢 OK"


def get_override_risk(structural: object, drug: str, sig: str, parsed: object) -> str:
    drug_lower = drug.lower()
    sig_lower = sig.lower()
    pattern_assessment = str(getattr(structural, "pattern_assessment", "") or "")
    pattern_issue = str(getattr(structural, "pattern_issue", "") or "")
    if pattern_assessment == "Pattern-questionable":
        return "The patient could follow a regimen that differs from the intended treatment plan because the use pattern remains unclear."
    if "ubrelvy" in drug_lower and "as needed" in sig_lower:
        return "Patient may exceed safe daily dose without max limit."
    elif "sildenafil" in drug_lower and "as needed" in sig_lower:
        return "Patient may take inappropriately without frequency guidance."
    elif "valacyclovir" in drug_lower and "prn" in sig_lower:
        return "Patient may misuse antiviral without clear usage structure."
    elif "valacyclovir" in drug_lower and "every 12 hours" in sig_lower:
        return "Incorrect duration assumption could lead to undertreatment."
    elif "metoprolol tartrate" in drug_lower and "daily" in sig_lower:
        return "Once-daily dosing may not provide adequate blood pressure control."
    elif "azithromycin" in drug_lower and "daily" in sig_lower:
        return "Extended course without indication may promote resistance."
    elif "cephalexin" in drug_lower and "every 12 hours" in sig_lower:
        return "An extended course length may be assumed without a clearly stated duration, leading to unintended treatment length."
    elif "fleet enema" in drug_lower and "daily prn for 30 days" in sig_lower:
        return "Patient may use the medication as ongoing daily therapy when episodic use was intended, or delay use when ongoing use was intended."
    elif "valacyclovir" in drug_lower and "take 2 tablets" in sig_lower and "twice a day" in sig_lower:
        return "Patient may interpret as a single short course when multiple episodes are intended, or vice versa, leading to inappropriate treatment timing."

    safe_to_verify = get_safe_to_verify(structural)
    if safe_to_verify == "🔴 UNSAFE":
        if ("prn" in sig_lower or "as needed" in sig_lower) and parsed.frequency:
            return (
                f"Patient may interpret the medication as ongoing {parsed.frequency} use when episodic use was intended. "
                "Unclear use pattern may lead to unintended repeated use."
            )

        event_triggers = [
            "before travel", "before flying", "before procedure", "before intercourse",
            "at onset", "when symptoms start",
        ]
        if any(trigger in sig_lower for trigger in event_triggers):
            return (
                "Medication may be used repeatedly without a clearly defined use pattern. "
                "Unclear event-based instructions may lead to inconsistent or unintended repeated use."
            )

        if "non-daily dosing" in structural.structural_issue.lower():
            return (
                "Non-daily dosing ambiguity may lead to misinterpretation of frequency and total exposure. "
                "Please verify the intended timing before proceeding."
            )

        if (
            "extended course" in structural.structural_issue.lower()
            or "quantity implies an extended course" in structural.structural_issue.lower()
            or "intended course structure" in structural.structural_issue.lower()
        ):
            return (
                "Entered directions and quantity create uncertainty about intended course structure, which may lead to unintended regimen execution. "
                "Verify intended duration and course design before proceeding."
            )

        return f"{structural.structural_issue} Verify before proceeding."

    return "No significant risk from proceeding."


TEST_CASES = [
    {"drug": "Valacyclovir 1 gm", "sig": "take 1 tablet by mouth twice daily prn", "quantity": 28},
    {"drug": "Valacyclovir 1 gm", "sig": "take 1 tablet by mouth every 12 hours", "quantity": 28},
    {"drug": "Valacyclovir 1 gm", "sig": "take 1 tablet by mouth every 12 hours as needed", "quantity": 30},
    {"drug": "Azithromycin 500 mg", "sig": "take 1 tablet by mouth daily", "quantity": 30},
    {"drug": "Metoprolol tartrate 50 mg", "sig": "take 1 tablet by mouth daily", "quantity": 30},
    {"drug": "Lisinopril 20 mg", "sig": "take 1 tablet by mouth daily", "quantity": 30},
    {"drug": "Ubrelvy 50 mg", "sig": "take 1 tablet by mouth daily as needed", "quantity": 10},
    {"drug": "Sildenafil 100 mg", "sig": "take 1 tablet by mouth as needed", "quantity": 10},
    {"drug": "Valacyclovir 1 gm", "sig": "take 1 tablet by mouth daily prn", "quantity": 28},
    {"drug": "Acetaminophen 500 mg", "sig": "take 1 tablet by mouth daily prn", "quantity": 30},
    {"drug": "Unknown Drug 100 mg", "sig": "take 1 tablet by mouth before travel", "quantity": 10},
    {"drug": "Cephalexin 500 mg", "sig": "take 1 tablet by mouth every 12 hours", "quantity": 60},
    {"drug": "Fleet Enema", "sig": "use 1 enema rectally daily prn for 30 days", "quantity": 30},
    {"drug": "Valacyclovir 1 gm", "sig": "take 2 tablets by mouth twice a day", "quantity": 30},
    {"drug": "Levothyroxine 88 mcg", "sig": "take 8 tablets by mouth weekly", "quantity": 32},
    {"drug": "Valacyclovir 1 gm", "sig": "take 1 tablet by mouth three times daily", "quantity": 60},
    {"drug": "Levofloxacin 750 mg", "sig": "take 1 tablet by mouth daily", "quantity": 21},
    {"drug": "Fluconazole 150 mg", "sig": "take 1 tablet by mouth daily", "quantity": 4},
]


def run_test_cases(cases, mode="all"):
    """Run through each case and apply the same logic as in `app.py`.

    mode: one of 'structural', 'refresh', 'document', 'message', or 'all'
    """
    for i, case in enumerate(cases, start=1):
        print(f"Case {i}")
        raw_line = f"{case['drug']} - {case['sig']} (qty {case['quantity']})"
        print(raw_line)
        print("=" * 60)

        try:
            parsed = parse_prescription_line(raw_line)
        except ValueError as e:
            print("Input error:", e)
            print("-" * 60)
            continue

        # Always detect structural issue for drug recognition status
        structural = detect_structural_issue(parsed.drug, parsed.sig, parsed.quantity, parsed.frequency)

        print("--- PARSED INPUT ---")
        print("Drug:", parsed.drug)
        print("SIG:", parsed.sig)
        print("Quantity:", parsed.quantity)
        print("Frequency:", parsed.frequency or "Not parsed")
        if structural.drug_recognition_status != "Recognized":
            status = structural.drug_recognition_status.upper()
            prefix = "⚠️" if status == "POSSIBLY MISSPELLED" else "❓"
            print(f"Drug Recognition: {prefix} {status}")
            if structural.drug_recognition_match:
                print(f"Possible match: {structural.drug_recognition_match}")
            print("Generic structural checks only; drug-specific logic may be incomplete.")

        if mode in ["structural", "all"]:
            action_bias = get_action_bias(structural.resolution)
            safe_to_verify = get_safe_to_verify(structural)
            follow_up_need = get_follow_up_need(structural)
            severity = get_severity(structural)
            risk_score = get_risk_score(structural.resolution, safe_to_verify, follow_up_need, severity)
            priority_badge = get_ui_priority(risk_score)
            override_risk = get_override_risk(structural, parsed.drug, parsed.sig, parsed)

            print("--- SCAN SIGNAL ---")
            print(f"{priority_badge} ({structural.resolution.split(' ', 1)[1] if ' ' in structural.resolution else structural.resolution})")
            print(f"Risk Score: {risk_score}")
            print(structural.structural_issue)
            print(f"Safe to Verify: {safe_to_verify}")
            print(f"Follow-up Need: {follow_up_need}")
            print(f"Action: {action_bias}")
            print(f"Severity: {severity}")
            print(f"Override Risk: {override_risk}")
            print("Affects:", structural.affects)
            print("Confidence:", structural.clarification)
            print()

            if structural.drug_recognition_status != "Recognized":
                status = structural.drug_recognition_status.upper()
                prefix = "⚠️" if status == "POSSIBLY MISSPELLED" else "❓"
                print(f"Drug Recognition: {prefix} {status}")
                if structural.drug_recognition_match:
                    print(f"Possible match: {structural.drug_recognition_match}")
                print("Generic structural checks only; drug-specific logic may be incomplete.")
                print()

            print("\n--- STRUCTURAL ---")
            print("Structural issue:", structural.structural_issue)
            print("Affects:", structural.affects)
            print("Confidence:", structural.clarification)

            print("\n--- RESOLUTION ---")
            print(structural.resolution)

        if mode in ["refresh", "all"]:
            print("\n--- KNOWLEDGE REFRESH ---")
            refresh = explain_pattern(parsed.drug, parsed.sig, parsed.quantity, parsed.frequency)
            for point in refresh.summary_points:
                print("-", point)
            print(refresh.conclusion)

        if mode in ["document", "all"]:
            print("\n--- DOCUMENTATION ---")
            doc = generate_documentation(parsed.drug, parsed.sig, parsed.quantity, parsed.frequency)
            print(doc.note)

        if mode in ["message", "all"]:
            print("\n--- MESSAGE ---")
            msg = generate_message(parsed.drug, parsed.sig, parsed.quantity, parsed.frequency)
            print("Prescriber-facing:")
            print(msg.prescriber_message)
            print()
            print("Internal:")
            print(msg.internal_message)

        print("-" * 60)


if __name__ == "__main__":
    print("Running structured test cases from test_cases.py\n")
    run_test_cases(TEST_CASES, mode="all")
