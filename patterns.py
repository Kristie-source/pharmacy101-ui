# List of drugs for which strength is not required for structural analysis (pattern-safe drugs)
PATTERN_SAFE_DRUGS = [
    "albuterol inhaler", "levalbuterol inhaler", "fluticasone inhaler", "budesonide inhaler", "epinephrine autoinjector", "epipen", "naloxone nasal spray", "naloxone autoinjector", "sumatriptan pack", "methylprednisolone dose pack", "medrol dose pack", "contraceptive pack", "norelgestromin patch", "nicotine patch", "testosterone gel pack", "insulin pen", "insulin cartridge", "insulin vial", "glucagon kit", "glucagon emergency kit"
]

def is_pattern_safe_drug(drug: str) -> bool:
    normalized = normalize_drug_name(drug)
    for safe in PATTERN_SAFE_DRUGS:
        if safe in normalized:
            return True
    return False
import re
from typing import Optional

from case_library import (
    STRUCTURED_PRN_DRUGS,
    ANTIBIOTICS,
    CHRONIC_DAILY_DRUGS,
    CONTINUOUS_USE_DRUGS,
    drug_matches_base_name,
    normalize_drug_name,
)
from models import PatternResult
from structure_patterns import classify_structure_pattern


FORMULATION_FREQUENCY_RULES = [
    {
        "pattern_name": "formulation_frequency_mismatch_metoprolol_tartrate_qd",
        "drug_contains_all": ["metoprolol", "tartrate"],
        "once_daily_only": True,
        "structural_issue": (
            "Frequency mismatch: Immediate-release metoprolol is typically dosed more than once daily; "
            "once-daily dosing may not provide full coverage"
        ),
        "affects": "frequency",
        "clarification": "Likely",
    },
]

SPECIFIC_DURATION_CENTRAL_DRUGS = [
    "valacyclovir",
]

ACUTE_USE_CHRONIC_QTY_DRUGS = [
    "valacyclovir",
]

# Conservative upper bounds for expected total dose per administration (mg)
# for select recognized one-time regimens.
SOLID_DOSE_UNIT_GROUP = {"tablet", "capsule"}


def _is_once_daily_equivalent(frequency: Optional[str], sig: str) -> bool:
    normalized_frequency = str(frequency or "").strip().lower()
    if normalized_frequency in {"daily", "once daily", "every 24 hours", "once a day", "qd"}:
        return True

    sig_lower = str(sig or "").lower()
    return bool(
        re.search(
            r"\b(?:once\s+daily|once\s+a\s+day|daily|qd|every\s*24\s*(?:h|hr|hour)s?)\b",
            sig_lower,
        )
    )


def detect_formulation_frequency_mismatch(parsed) -> Optional[PatternResult]:
    drug_lower = str(parsed.drug or "").lower()

    for rule in FORMULATION_FREQUENCY_RULES:
        required_tokens = rule.get("drug_contains_all", [])
        if any(token not in drug_lower for token in required_tokens):
            continue

        if rule.get("once_daily_only") and not _is_once_daily_equivalent(parsed.frequency, parsed.sig):
            continue

        return PatternResult(
            pattern_name=rule["pattern_name"],
            structural_issue=rule["structural_issue"],
            affects=rule.get("affects", "frequency"),
            clarification=rule.get("clarification", "Likely"),
        )

    return None


def _is_acute_use_chronic_qty_medication(drug: str) -> bool:
    if any(_matches_clean_base_name(drug, base_name) for base_name in ACUTE_USE_CHRONIC_QTY_DRUGS):
        return True
    return any(_matches_clean_base_name(drug, antibiotic) for antibiotic in ANTIBIOTICS)


def detect_acute_use_chronic_quantity(parsed) -> Optional[PatternResult]:
    if not parsed.frequency:
        return None

    if parsed.quantity < 30:
        return None

    if not _is_acute_use_chronic_qty_medication(parsed.drug):
        return None

    return PatternResult(
        pattern_name="acute_use_chronic_quantity",
        structural_issue=(
            f"Quantity stands out: Quantity {parsed.quantity} looks more like a chronic-style supply than a typical acute-use pattern for this medication."
        ),
        affects="duration",
        clarification="Likely",
    )


def _has_explicit_duration(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    return any(token in sig_lower for token in (" for ", " days", " day", " weeks", " week", " months", " month"))


def _is_single_dose_structure(sig: str, frequency: Optional[str]) -> bool:
    normalized_frequency = str(frequency or "").strip().lower()
    if normalized_frequency == "single dose":
        return True

    sig_lower = str(sig or "").lower()
    one_time_patterns = [
        r"\bfor\s+(?:one|1)\s+dose\b",
        r"\bsingle\s*dose\b",
        r"\bone[-\s]?time\b",
        r"\bx\s*1\b",
    ]
    if any(re.search(pattern, sig_lower) for pattern in one_time_patterns):
        return True

    if not re.search(r"\bonce\b", sig_lower):
        return False

    recurring_once_patterns = [
        r"\bonce\s+daily\b",
        r"\bonce\s+a\s+day\b",
        r"\bonce\s+weekly\b",
        r"\bonce\s+a\s+week\b",
        r"\bonce\s+monthly\b",
        r"\bonce\s+a\s+month\b",
    ]
    return not any(re.search(pattern, sig_lower) for pattern in recurring_once_patterns)


def _extract_strength_components(drug: str) -> Optional[tuple[float, str, float]]:
    # If drug is in pattern-safe list, skip strength extraction (not required)
    if is_pattern_safe_drug(drug):
        return None
    match = re.search(
        r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|g|gm)\b",
        str(drug or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    value = float(match.group("value"))
    unit = match.group("unit").lower()
    if unit == "mg":
        return value, unit, value
    if unit == "mcg":
        return value, unit, value / 1000.0
    if unit in {"g", "gm"}:
        return value, unit, value * 1000.0
    return None


def detect_dose_unit_formulation_inconsistency(parsed) -> Optional[PatternResult]:
    strength_components = _extract_strength_components(parsed.drug)
    dose_components = _extract_dose_amount_and_unit(parsed.sig)
    if strength_components is None or dose_components is None:
        return None

    strength_value, strength_unit, strength_mg = strength_components
    dose_units, dose_unit_group = dose_components
    total_dose_mg = dose_units * strength_mg

    if strength_unit not in {"g", "gm"}:
        return None
    if dose_unit_group not in SOLID_DOSE_UNIT_GROUP:
        return None
    if dose_units < 2:
        return None

    total_dose_label = (
        f"{int(total_dose_mg)} mg" if total_dose_mg.is_integer() else f"{round(total_dose_mg, 1)} mg"
    )
    strength_display = f"{strength_value:g} {strength_unit}"

    if dose_unit_group == "tablet":
        dose_unit_text = "tablets"
    else:
        dose_unit_text = "capsules"

    return PatternResult(
        pattern_name="dose_unit_formulation_inconsistency",
        structural_issue=(
            "Dose / unit / formulation inconsistency: strength is expressed as "
            f"{strength_display}, but SIG uses {dose_units} {dose_unit_text}; implied total per administration is "
            f"{total_dose_label}, and the expression does not reconcile cleanly with the dosage unit."
        ),
        affects="instructions",
        clarification="Likely",
    )


def _matches_clean_base_name(drug: str, base_name: str) -> bool:
    normalized = normalize_drug_name(drug)
    return base_name == normalized or f"{base_name} " in f"{normalized} " or f" {base_name}" in f" {normalized}"


def _is_duration_central_medication(drug: str) -> bool:
    if any(_matches_clean_base_name(drug, base_name) for base_name in SPECIFIC_DURATION_CENTRAL_DRUGS):
        return True
    return any(_matches_clean_base_name(drug, antibiotic) for antibiotic in ANTIBIOTICS)


def detect_duration_central_missing_duration(parsed) -> Optional[PatternResult]:
    structure_pattern = classify_structure_pattern(parsed.sig)
    if structure_pattern.structurally_complete and not structure_pattern.requires_duration:
        return None

    if _is_single_dose_structure(parsed.sig, parsed.frequency):
        return None

    if _has_explicit_duration(parsed.sig):
        return None

    if not parsed.frequency:
        return None

    if not _is_duration_central_medication(parsed.drug):
        return None

    return PatternResult(
        pattern_name="duration_central_missing_duration",
        structural_issue=(
            "Duration missing: Duration is clinically central for this medication, but no treatment length is stated."
        ),
        affects="duration",
        clarification="Likely",
    )


def is_lisinopril_standard_daily_verify(parsed) -> bool:
    drug_lower = str(parsed.drug or "").lower()
    if "lisinopril" not in drug_lower:
        return False

    sig_lower = str(parsed.sig or "").lower()
    if "prn" in sig_lower or "as needed" in sig_lower:
        return False

    normalized_frequency = str(parsed.frequency or "").strip().lower()
    return normalized_frequency in {"daily", "once daily"}


def _is_fixed_scheduled_frequency(frequency: Optional[str], sig: str) -> bool:
    normalized_frequency = str(frequency or "").strip().lower()
    if normalized_frequency in {
        "twice daily",
        "three times daily",
        "four times daily",
        "every 8 hours",
        "every 12 hours",
    }:
        return True

    sig_lower = str(sig or "").lower()
    return bool(
        re.search(
            r"\b(?:bid|tid|qid|q\s*8\s*h|q\s*12\s*h|every\s*8\s*(?:h|hr|hour)s?|every\s*12\s*(?:h|hr|hour)s?)\b",
            sig_lower,
        )
    )


def detect_prn_scheduled_conflict(drug: str, sig: str, frequency: Optional[str]) -> Optional[PatternResult]:
    sig_lower = sig.lower()
    has_prn = "prn" in sig_lower or "as needed" in sig_lower
    has_fixed_schedule = _is_fixed_scheduled_frequency(frequency, sig)

    # Detect mixed scheduled + separate PRN regimens (e.g., 'take 1 tablet three times daily and 1 tablet as needed')
    split_regex = r"(?:\band\b|;|\n|\r)"
    instructions = [s.strip() for s in re.split(split_regex, sig_lower) if s.strip()]
    if len(instructions) > 1:
        scheduled_found = False
        prn_found = False
        for instr in instructions:
            instr_has_prn = "prn" in instr or "as needed" in instr
            instr_has_schedule = _is_fixed_scheduled_frequency(frequency, instr)
            # Accept bounded PRN (e.g., 'three times daily as needed')
            if instr_has_prn and instr_has_schedule:
                continue
            elif instr_has_prn:
                prn_found = True
            elif instr_has_schedule:
                scheduled_found = True
        # If both a separate scheduled and a separate PRN instruction are found, flag as mixed regimen
        if scheduled_found and prn_found:
            return PatternResult(
                pattern_name="scheduled_plus_separate_prn_conflict",
                structural_issue="Directions contain both scheduled and separate as-needed dosing, creating two possible use patterns.",
                affects="schedule",
                clarification="Likely",
            )
        # Otherwise, treat as valid bounded PRN
        return None

    # If PRN and frequency are part of the same instruction (e.g., 'twice daily as needed', 'every 6 hours as needed'), treat as valid bounded PRN
    if has_prn and has_fixed_schedule:
        return None
    return None


def _extract_dose_amount(sig: str) -> Optional[int]:
    match = re.search(
        r"\b(?P<amount>\d+)\s*(?:tablets?|tabs?|capsules?|caps?)\b",
        str(sig or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return int(match.group("amount"))


def _extract_dose_amount_and_unit(sig: str) -> Optional[tuple[int, str]]:
    match = re.search(
        r"\b(?P<amount>\d+)\s*(?P<unit>tablets?|tabs?|capsules?|caps?)\b",
        str(sig or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    amount = int(match.group("amount"))
    unit_token = str(match.group("unit") or "").lower()
    if unit_token.startswith("tab"):
        return amount, "tablet"
    if unit_token.startswith("cap"):
        return amount, "capsule"
    return None


def _extract_duration_days(sig: str) -> Optional[int]:
    sig_lower = str(sig or "").lower()
    day_match = re.search(r"\bfor\s+(\d+)\s+days?\b", sig_lower)
    if day_match:
        return int(day_match.group(1))

    week_match = re.search(r"\bfor\s+(\d+)\s+weeks?\b", sig_lower)
    if week_match:
        return int(week_match.group(1)) * 7

    month_match = re.search(r"\bfor\s+(\d+)\s+months?\b", sig_lower)
    if month_match:
        return int(month_match.group(1)) * 30

    return None


def _frequency_doses_per_day(frequency: Optional[str]) -> Optional[float]:
    normalized = str(frequency or "").strip().lower()
    mapping = {
        "daily": 1.0,
        "once daily": 1.0,
        "twice daily": 2.0,
        "three times daily": 3.0,
        "four times daily": 4.0,
        "every 12 hours": 2.0,
        "every 8 hours": 3.0,
        "every 6 hours": 4.0,
        "every 4 hours": 6.0,
        "every 2 hours": 12.0,
        "every other day": 0.5,
        "weekly": 1.0 / 7.0,
    }
    return mapping.get(normalized)


def detect_quantity_mismatch(parsed) -> Optional[PatternResult]:
    structure_pattern = classify_structure_pattern(parsed.sig)
    pattern_name = structure_pattern.pattern_name
    dose_amount = _extract_dose_amount(parsed.sig)
    duration_days = _extract_duration_days(parsed.sig)
    doses_per_day = _frequency_doses_per_day(parsed.frequency)

    # 1. Single-dose: quantity must match the explicit one-time dose
    if pattern_name == "single_dose":
        if dose_amount is None:
            return None
        if parsed.quantity != dose_amount:
            return PatternResult(
                pattern_name="quantity_mismatch_single_dose",
                structural_issue=(
                    f"Quantity mismatch: Quantity {parsed.quantity} does not match the written single-dose administration ({dose_amount})."
                ),
                affects="duration",
                clarification="Likely",
            )
        return None

    # 2. Taper: sum all segment doses × days
    if pattern_name == "taper":
        # Parse all segments like "take X tablets daily for Y days" or "X tablets ... for Y days"
        # More robust: allow arbitrary text between segments
        segments = re.findall(r"(\d+)\s*(?:tablet|tab|capsule|cap)s?[^\d]*(?:daily|once daily)?[^\d]*for\s*(\d+)\s*days?", parsed.sig, re.IGNORECASE)
        print(f"DEBUG: taper segments={segments} for sig={parsed.sig}")
        if not segments:
            return None
        total_expected = sum(int(dose) * int(days) for dose, days in segments)
        print(f"DEBUG: taper total_expected={total_expected} quantity={parsed.quantity}")
        if parsed.quantity != total_expected:
            return PatternResult(
                pattern_name="quantity_mismatch_taper",
                structural_issue=(
                    f"Quantity mismatch (taper): Quantity {parsed.quantity} does not match the sum of all taper segments ({total_expected})."
                ),
                affects="duration",
                clarification="Likely",
            )
        return None

    # 3. Fixed-duration: dose × frequency × duration
    if pattern_name == "fixed_duration_scheduled":
        if dose_amount is None or duration_days is None or doses_per_day is None:
            return None
        expected_quantity = dose_amount * doses_per_day * duration_days
        material_difference = abs(parsed.quantity - expected_quantity)
        if material_difference >= max(2, dose_amount):
            return PatternResult(
                pattern_name="quantity_mismatch_fixed_duration",
                structural_issue=(
                    f"Quantity mismatch (fixed-duration): Quantity {parsed.quantity} does not align with the written dose, frequency, and stated duration; expected about {int(expected_quantity) if expected_quantity.is_integer() else round(expected_quantity, 1)}."
                ),
                affects="duration",
                clarification="Likely",
            )
        return None

    # 4. Ongoing/weekly/variable: do not force daily math
    if pattern_name in {"ongoing_scheduled", "weekly_variable_day", "prn_bounded", "prn_unbounded", "episode_based_prn", "unclassified"}:
        return None

    # Fallback: use original logic if pattern is not recognized
    if dose_amount is not None and duration_days is not None and doses_per_day is not None:
        expected_quantity = dose_amount * doses_per_day * duration_days
        material_difference = abs(parsed.quantity - expected_quantity)
        if material_difference >= max(2, dose_amount):
            return PatternResult(
                pattern_name="quantity_mismatch_fallback",
                structural_issue=(
                    f"Quantity mismatch: Quantity {parsed.quantity} does not align with the written dose, frequency, and stated duration; expected about {int(expected_quantity) if expected_quantity.is_integer() else round(expected_quantity, 1)}."
                ),
                affects="duration",
                clarification="Likely",
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

    is_prn_interval_frequency = frequency in [
        "every 4 hours",
        "every 6 hours",
        "every 8 hours",
        "every 12 hours",
        "q4h",
        "q6h",
        "q8h",
        "q12h",
    ]

    is_flexible_nonstructured_prn = (
        has_prn
        and no_explicit_duration
        and (frequency in ["daily", "once daily"] or is_prn_interval_frequency)
        and not is_structured_prn_drug
    )
    # Standard scheduled maintenance frequencies (not episodic or event-based)
    standard_maintenance_frequencies = [
        "daily", "once daily", "twice daily", "three times daily", "four times daily",
        "every other day", "every 12 hours", "every 8 hours", "every 6 hours",
        "every 4 hours", "every 2 hours"
    ]
    
    is_standard_maintenance_frequency = frequency in standard_maintenance_frequencies

    # Suppress for routine maintenance fills (e.g., daily qty 30, BID qty 60, etc.)
    doses_per_day = None
    sig_lower = parsed.sig.lower()
    if 'four times daily' in sig_lower or 'qid' in sig_lower:
        doses_per_day = 4
    elif 'three times daily' in sig_lower or 'tid' in sig_lower:
        doses_per_day = 3
    elif 'twice daily' in sig_lower or 'twice a day' in sig_lower or 'bid' in sig_lower:
        doses_per_day = 2
    elif 'once daily' in sig_lower or 'every day' in sig_lower or 'daily' in sig_lower:
        doses_per_day = 1

    is_maintenance = (
        (doses_per_day == 1 and parsed.quantity in [28, 30, 31, 32, 90]) or
        (doses_per_day == 2 and parsed.quantity in [56, 60, 62, 90]) or
        (doses_per_day == 3 and parsed.quantity in [84, 90])
    )

    # Detect the pattern, but suppress for maintenance fills
    if (
        is_standard_maintenance_frequency
        and no_explicit_duration
        and implies_extended_course
        and not is_excluded_drug
        and not is_flexible_nonstructured_prn
        and not is_maintenance
    ):
        return PatternResult(
            pattern_name="extended_course_no_duration",
            structural_issue="Entered directions and quantity create uncertainty about the intended course structure; this should not be resolved by day-supply math alone.",
            affects="duration",
            clarification="Likely",
        )
    
    return None


def detect_regimen_transformation_ambiguity(parsed) -> Optional[PatternResult]:
    """Detect ambiguity when regimen structure is unclear or potentially changing.
    
    This should only flag truly ambiguous patterns, not normal maintenance medication
    schedules with standard frequencies (twice daily, three times daily, etc.).
    """
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

    # Standard scheduled maintenance frequencies (not episodic or event-based)
    standard_maintenance_frequencies = [
        "daily", "once daily", "twice daily", "three times daily", "four times daily",
        "every other day", "every 12 hours", "every 8 hours", "every 6 hours",
        "every 4 hours", "every 2 hours"
    ]
    
    is_standard_maintenance_frequency = frequency in standard_maintenance_frequencies

    # Only flag regimen transformation if:
    # 1. Frequency exists but is NOT a standard maintenance frequency
    # 2. No explicit duration stated
    # 3. Quantity implies extended course
    # 4. Not an excluded drug (chronic/antibiotic/continuous-use)
    # 5. Not a flexible PRN pattern
    if (
        frequency
        and not is_standard_maintenance_frequency
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

    # Tadalafil PRN for ED: patient counseling only, not workflow interruption
    drug_lower = drug.lower()
    sig_lower = sig.lower()
    tadalafil_strengths = ["5 mg", "10 mg", "20 mg"]
    is_tadalafil = "tadalafil" in drug_lower and any(strength in drug_lower for strength in tadalafil_strengths)
    is_prn_ed = ("prn" in sig_lower or "as needed" in sig_lower) and ("erectile dysfunction" in sig_lower or "ed" in sig_lower)
    if is_tadalafil and is_prn_ed:
        return PatternResult(
            pattern_name="tadalafil_prn_patient_clarity",
            structural_issue="PRN for ED: Patient may benefit from counseling on as-needed use, but no workflow interruption required.",
            affects="instructions",
            clarification="Patient counseling",
        )

    for detector in (detect_prn_scheduled_conflict,):
        result = detector(drug, sig, frequency)
        if result:
            return result

    result = detect_non_daily_dosing_ambiguity(sig)
    if result:
        return result

    result = detect_quantity_mismatch(parsed)
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
