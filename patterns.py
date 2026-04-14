from typing import Optional

from case_library import (
    STRUCTURED_PRN_DRUGS,
    ANTIBIOTICS,
    CHRONIC_DAILY_DRUGS,
    CONTINUOUS_USE_DRUGS,
    drug_matches_base_name,
)
from models import PatternResult


def detect_prn_scheduled_conflict(drug: str, sig: str, frequency: Optional[str]) -> Optional[PatternResult]:
    sig_lower = sig.lower()
    has_prn = "prn" in sig_lower or "as needed" in sig_lower
    is_structured_prn_drug = any(
        drug_matches_base_name(drug, drug_name) for drug_name in STRUCTURED_PRN_DRUGS
    )

    if has_prn and frequency and is_structured_prn_drug:
        return PatternResult(
            pattern_name="prn_scheduled_conflict",
            structural_issue=(
                f"PRN use is combined with {frequency} frequency, making it unclear whether the "
                "order is intended for ongoing scheduled use or episodic use."
            ),
            affects="instructions",
            clarification="Context-dependent",
        )

    return None


def detect_non_daily_dosing_ambiguity(sig: str) -> Optional[PatternResult]:
    sig_lower = sig.lower()

    non_daily_frequencies = [
        "weekly",
        "monthly",
        "every week",
        "every month",
        "every other day",
        "alternating days",
        "twice weekly",
        "three times weekly",
        "four times weekly",
        "twice monthly",
        "three times monthly",
        "every 2 weeks",
        "biweekly",
        "every 3 days",
        "every 4 days",
        "every 5 days",
        "every 6 days",
    ]

    administration_indicators = [
        "all at once",
        "at the same time",
        "together",
        "once a week",
        "once weekly",
        "once a month",
        "once monthly",
        "one each day",
        "one per day",
        "divided",
        "split",
        "distributed",
        "throughout the",
        "over the",
        "across the",
    ]

    has_non_daily_frequency = any(term in sig_lower for term in non_daily_frequencies)
    has_clear_administration = any(indicator in sig_lower for indicator in administration_indicators)

    if has_non_daily_frequency and not has_clear_administration:
        return PatternResult(
            pattern_name="non_daily_dosing_ambiguity",
            structural_issue=(
                "Non-daily dosing is specified, but the administration pattern is not clearly defined."
            ),
            affects="instructions",
            clarification="Context-dependent",
        )

    return None


def detect_extended_course_without_context(parsed) -> Optional[PatternResult]:
    """Detect extended course prescriptions without stated duration or context.
    
    Checks for:
    - Scheduled daily dosing
    - Quantity implying extended duration (>= 30)
    - No explicit duration stated
    - Not excluded drug categories (antibiotics, chronic daily, continuous-use)
    - Not flexible PRN pattern
    """
    drug = parsed.drug
    sig = parsed.sig
    quantity = parsed.quantity
    frequency = parsed.frequency
    sig_lower = sig.lower()
    
    # Check prerequisites
    no_explicit_duration = (
        "for" not in sig_lower
        and "days" not in sig_lower
        and "weeks" not in sig_lower
        and "months" not in sig_lower
    )
    has_prn = "prn" in sig_lower or "as needed" in sig_lower
    implies_extended_course = quantity >= 30
    
    # Check if drug is in excluded categories
    is_excluded_drug = (
        any(drug_matches_base_name(drug, drug_name) for drug_name in ANTIBIOTICS)
        or any(drug_matches_base_name(drug, drug_name) for drug_name in CHRONIC_DAILY_DRUGS)
        or any(drug_matches_base_name(drug, drug_name) for drug_name in CONTINUOUS_USE_DRUGS)
    )
    
    # Check if it's a flexible non-structured PRN (should be excluded)
    is_structured_prn_drug = any(
        drug_matches_base_name(drug, drug_name) for drug_name in STRUCTURED_PRN_DRUGS
    )
    is_flexible_nonstructured_prn = (
        has_prn
        and no_explicit_duration
        and frequency in ["daily", "once daily"]
        and not is_structured_prn_drug
    )
    
    is_scheduled_daily_dosing = frequency in ["daily", "once daily"]

    # Detect the pattern
    if (
        is_scheduled_daily_dosing
        and no_explicit_duration
        and implies_extended_course
        and not is_excluded_drug
        and not is_flexible_nonstructured_prn
    ):
        return PatternResult(
            pattern_name="extended_course_no_duration",
            structural_issue="Entered directions and quantity create uncertainty about the intended course structure; this should not be resolved by day-supply math alone.",
            affects="duration",
            clarification="Likely",
        )
    
    return None


def detect_regimen_transformation_ambiguity(parsed) -> Optional[PatternResult]:
    drug = parsed.drug
    sig = parsed.sig
    quantity = parsed.quantity
    frequency = parsed.frequency
    sig_lower = sig.lower()

    no_explicit_duration = (
        "for" not in sig_lower
        and "days" not in sig_lower
        and "weeks" not in sig_lower
        and "months" not in sig_lower
    )
    has_prn = "prn" in sig_lower or "as needed" in sig_lower
    implies_extended_course = quantity >= 30

    is_excluded_drug = (
        any(drug_matches_base_name(drug, drug_name) for drug_name in ANTIBIOTICS)
        or any(drug_matches_base_name(drug, drug_name) for drug_name in CHRONIC_DAILY_DRUGS)
        or any(drug_matches_base_name(drug, drug_name) for drug_name in CONTINUOUS_USE_DRUGS)
    )

    is_structured_prn_drug = any(
        drug_matches_base_name(drug, drug_name) for drug_name in STRUCTURED_PRN_DRUGS
    )
    is_flexible_nonstructured_prn = (
        has_prn
        and no_explicit_duration
        and frequency in ["daily", "once daily"]
        and not is_structured_prn_drug
    )

    is_scheduled_daily_dosing = frequency in ["daily", "once daily"]

    if (
        frequency
        and not is_scheduled_daily_dosing
        and no_explicit_duration
        and implies_extended_course
        and not is_excluded_drug
        and not is_flexible_nonstructured_prn
    ):
        return PatternResult(
            pattern_name="regimen_transformation_ambiguity",
            structural_issue="Entered directions and quantity create uncertainty about the intended course structure; this should not be resolved by day-supply math alone.",
            affects="duration",
            clarification="Likely",
        )

    return None


def detect_event_based_use(parsed) -> Optional[PatternResult]:
    sig_lower = parsed.sig.lower()

    event_triggers = [
        "before travel",
        "before flying",
        "before procedure",
        "before intercourse",
        "at onset",
        "when symptoms start",
    ]
    has_event_based_wording = any(trigger in sig_lower for trigger in event_triggers)

    if has_event_based_wording:
        return PatternResult(
            pattern_name="event_based_use",
            structural_issue=(
                "Order contains event-based or future-use wording, indicating a non-routine use pattern that may "
                "require clarification of intended repeated-use structure."
            ),
            affects="instructions",
            clarification="Context-dependent",
        )

    return None


def detect_pattern_families(parsed) -> Optional[PatternResult]:
    """Detect explicit pattern families in order of priority.
    
    Priority order:
    1. PRN + scheduled conflict (high risk if combined)
    2. Non-daily dosing without clear administration
    3. Extended course without stated duration
    4. Event-based/future-use wording
    5. Regimen transformation ambiguity
    """
    drug = parsed.drug
    sig = parsed.sig
    frequency = parsed.frequency

    for detector in (detect_prn_scheduled_conflict,):
        result = detector(drug, sig, frequency)
        if result:
            return result

    result = detect_non_daily_dosing_ambiguity(sig)
    if result:
        return result

    result = detect_extended_course_without_context(parsed)
    if result:
        return result

    result = detect_event_based_use(parsed)
    if result:
        return result

    result = detect_regimen_transformation_ambiguity(parsed)
    if result:
        return result

    return None
