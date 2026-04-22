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
    safe_to_verify = get_safe_to_verify(structural)
    risk_severity = str(getattr(structural, "risk_severity", "LOW") or "LOW").upper()
    if risk_severity == "LOW" and safe_to_verify != "🔴 UNSAFE":
        return "🟢 NO FOLLOW-UP NEEDED"
    if safe_to_verify == "🔴 UNSAFE":
        return "🔴 REQUIRED BEFORE VERIFY"
    return "🟡 MESSAGE RECOMMENDED"


def get_safe_to_verify(structural: object) -> str:
    immediate_usability = str(getattr(structural, "immediate_usability", "") or "").upper()
    if immediate_usability == "NO":
        return "🔴 UNSAFE"
    if immediate_usability == "YES":
        return "🟡 SAFE WITH GUIDANCE" if str(getattr(structural, "risk_severity", "LOW") or "LOW").upper() in {"MODERATE", "HIGH"} else "🟢 SAFE"

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
    risk_severity = str(getattr(structural, "risk_severity", "") or "").upper()
    if risk_severity == "HIGH":
        return "🔴 HIGH"
    if risk_severity == "MODERATE":
        return "🟡 MODERATE"
    if risk_severity == "LOW":
        return "🟢 LOW"

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
    # Scope guardrail: contextual risk wording is secondary only.
    # If there is no structural ambiguity trigger, we intentionally return
    # no-risk text to avoid DUR-style alerting drift and alert fatigue.
    lane = _lane_token(structural.resolution)
    pattern_assessment = str(getattr(structural, "pattern_assessment", "") or "")
    pattern_issue = str(getattr(structural, "pattern_issue", "") or "")
    if lane == "NONE" or str(structural.affects).lower() == "none":
        if pattern_assessment == "Pattern-questionable":
            return "The patient could follow a regimen that differs from the intended treatment plan because the use pattern remains unclear."
        return "No significant risk from proceeding."

    if pattern_assessment == "Pattern-questionable":
        return "The patient could follow a regimen that differs from the intended treatment plan because the use pattern remains unclear."

    drug_lower = drug.lower()
    sig_lower = sig.lower()
    if "ubrelvy" in drug_lower and "as needed" in sig_lower:
        return "Patient may exceed safe daily dose without max limit."
    elif "sildenafil" in drug_lower and "as needed" in sig_lower:
        return "Patient may take inappropriately without frequency guidance."
    elif "valacyclovir" in drug_lower and "prn" in sig_lower:
        return "Patient may start treatment at the wrong time or use repeated doses inappropriately."
    elif "valacyclovir" in drug_lower and parsed.frequency == "every 12 hours":
        return "Patient may stop too soon or continue too long, leading to undertreatment or unnecessary antiviral exposure."
    elif "metoprolol tartrate" in drug_lower and parsed.frequency in ["daily", "once daily"]:
        return "Once-daily dosing may not provide adequate blood pressure control."
    elif "azithromycin" in drug_lower and parsed.frequency in ["daily", "once daily"]:
        return "Patient may continue therapy longer than intended, increasing adverse effects and resistance pressure."
    elif "quantity stands out:" in structural.structural_issue.lower():
        return "Patient may continue therapy longer than intended or keep excess medication for unintended future use."

    safe_to_verify = get_safe_to_verify(structural)
    if safe_to_verify == "🔴 UNSAFE":
        if ("prn" in sig_lower or "as needed" in sig_lower) and parsed.frequency:
            return (
                "Patient may use medication more frequently than intended or misunderstand when to take it."
            )

        event_triggers = [
            "before travel", "before flying", "before procedure", "before intercourse",
            "at onset", "when symptoms start",
        ]
        if any(trigger in sig_lower for trigger in event_triggers):
            return (
                "Patient may repeat the medication at the wrong times or more often than intended."
            )

        if "non-daily dosing" in structural.structural_issue.lower():
            return (
                "Patient may take too much or too little over time because the timing pattern can be misunderstood."
            )

        if (
            "extended course" in structural.structural_issue.lower()
            or "quantity implies an extended course" in structural.structural_issue.lower()
            or "intended course structure" in structural.structural_issue.lower()
            or "duration missing" in structural.structural_issue.lower()
        ):
            return (
                "Patient may use the medication longer or shorter than intended, leading to incomplete treatment or unnecessary exposure."
            )

        if "quantity mismatch" in structural.structural_issue.lower():
            return "Patient may run out early or continue therapy longer than intended."

        return "Patient may follow the medication differently than intended, which could affect safety or treatment success."

    return "No significant risk from proceeding."


def main():
    raw_input_line = input("Pharmacist input: ")
    mode = input("Mode (Structural / Refresh / Document / Message / All): ").strip().lower()

    try:
        parsed = parse_prescription_line(raw_input_line)
    except ValueError as e:
        print("\nInput error:", e)
        return

    if mode not in ["structural", "refresh", "document", "message", "all"]:
        print("\nInvalid mode. Use Structural, Refresh, Document, Message, or All.")
        return

    print("\n--- PARSED INPUT ---")
    print("Drug:", parsed.drug)
    print("SIG:", parsed.sig)
    print("Quantity:", parsed.quantity)
    print("Frequency:", parsed.frequency or "Not parsed")

    if mode in ["structural", "all"]:
        print("\n--- STRUCTURAL ---")
        structural = detect_structural_issue(parsed.drug, parsed.sig, parsed.quantity, parsed.frequency)
        print("Structural issue:", structural.structural_issue)
        print("Affects:", structural.affects)
        print("Clarification:", structural.clarification)
        if structural.drug_recognition_status != "Recognized":
            status = structural.drug_recognition_status.upper()
            prefix = "⚠️" if status == "POSSIBLY MISSPELLED" else "❓"
            print(f"Drug Recognition: {prefix} {status}")
            if structural.drug_recognition_match:
                print(f"Possible match: {structural.drug_recognition_match}")
            print("Generic structural checks only; drug-specific logic may be incomplete.")

        print("\n--- RESOLUTION ---")
        print(structural.resolution)

        # If structural issue detected, show SCAN SIGNAL
        if structural.resolution != "🟢 NONE":
            action_bias = get_action_bias(structural.resolution)
            safe_to_verify = get_safe_to_verify(structural)
            follow_up_need = get_follow_up_need(structural)
            severity = get_severity(structural)
            risk_score = get_risk_score(structural.resolution, safe_to_verify, follow_up_need, severity)
            priority_badge = get_ui_priority(risk_score)
            override_risk = get_override_risk(structural, parsed.drug, parsed.sig, parsed)

            print("\n--- SCAN SIGNAL ---")
            print(f"{priority_badge} ({structural.resolution[2:]})")
            print(f"Risk Score: {risk_score}")
            print(structural.structural_issue)
            print(f"Safe to Verify: {safe_to_verify}")
            print(f"Follow-up Need: {follow_up_need}")
            print(f"Action: {action_bias}")
            print(f"Severity: {severity}")
            print(f"Override Risk: {override_risk}")
            print("Affects:", structural.affects)
            print("Confidence:", structural.clarification)

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


if __name__ == "__main__":
    main()
def calculate_days_supply(quantity):
    # Placeholder logic for calculating days supply based on quantity and SIG
    # In a real implementation, this would involve parsing the SIG and applying dosing rules
    return quantity // 30  # Example: assume 30 units per day for simplicity