from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional
import re


def normalize_drug_name(drug: str) -> str:
    normalized = drug.lower()
    # Remove numeric strength/unit segments like '750 mg', '88 mcg', '1 gm'.
    normalized = re.sub(r'\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|units?)\b', ' ', normalized)
    # Remove any leftover numeric fragments and non-letter separators.
    normalized = re.sub(r'\b\d+(?:\.\d+)?\b', ' ', normalized)
    normalized = re.sub(r'[^a-z ]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def drug_matches_base_name(drug: str, base_name: str) -> bool:
    normalized = normalize_drug_name(drug)
    if base_name in normalized.split():
        return True
    if base_name in normalized:
        return True
    for token in normalized.split():
        if abs(len(token) - len(base_name)) <= 3:
            ratio = SequenceMatcher(None, token, base_name).ratio()
            if ratio >= 0.8:
                return True
    return False


KNOWN_DRUG_NAMES = [
    "docusate",
    "valacyclovir",
    "metoprolol tartrate",
    "azithromycin",
    "cephalexin",
    "levofloxacin",
    "levothyroxine",
    "ubrelvy",
    "sildenafil",
    "colchicine",
    "sumatriptan",
    "rizatriptan",
    "lisinopril",
    "acetaminophen",
    "apixaban",
    "rivaroxaban",
    # Antibiotics
    "amoxicillin", "augmentin", "azithromycin", "cephalexin", "ciprofloxacin",
    "clindamycin", "doxycycline", "levofloxacin", "metronidazole", "nitrofurantoin",
    "trimethoprim", "sulfamethoxazole", "cefdinir", "cefuroxime",
    # Antivirals
    "acyclovir", "valacyclovir", "famciclovir", "oseltamivir",
    # Antifungals
    "fluconazole", "nystatin",
    # Cardiovascular
    "amlodipine", "atenolol", "carvedilol", "lisinopril", "losartan",
    "metoprolol", "metoprolol tartrate", "metoprolol succinate",
    "valsartan", "irbesartan", "olmesartan", "hydrochlorothiazide",
    "furosemide", "spironolactone", "digoxin", "warfarin",
    "apixaban", "rivaroxaban", "clopidogrel",
    # Cholesterol
    "atorvastatin", "rosuvastatin", "simvastatin", "pravastatin",
    # Diabetes
    "metformin", "glipizide", "glimepiride", "sitagliptin",
    "empagliflozin", "dapagliflozin", "insulin",
    # Thyroid
    "levothyroxine",
    # GI
    "omeprazole", "pantoprazole", "esomeprazole", "lansoprazole",
    "ondansetron", "promethazine", "metoclopramide",
    "docusate", "polyethylene glycol", "bisacodyl",
    # Pain / Inflammation
    "acetaminophen", "ibuprofen", "naproxen", "meloxicam",
    "celecoxib", "diclofenac", "ketorolac", "tramadol",
    "oxycodone", "hydrocodone", "morphine", "gabapentin", "pregabalin",
    "cyclobenzaprine", "methocarbamol",
    # Respiratory
    "albuterol", "montelukast", "fluticasone", "budesonide",
    "tiotropium", "ipratropium",
    # Mental health
    "sertraline", "escitalopram", "fluoxetine", "paroxetine",
    "bupropion", "venlafaxine", "duloxetine", "mirtazapine",
    "alprazolam", "lorazepam", "clonazepam", "diazepam",
    "quetiapine", "aripiprazole", "risperidone", "olanzapine",
    "lithium", "lamotrigine", "valproic acid",
    # Sleep
    "zolpidem", "trazodone", "melatonin",
    # Migraine
    "sumatriptan", "rizatriptan", "ubrelvy", "nurtec",
    # Gout
    "colchicine", "allopurinol", "febuxostat",
    # Hormones
    "estradiol", "progesterone", "testosterone", "prednisone",
    "methylprednisolone", "dexamethasone", "hydrocortisone",
    # Urological
    "tamsulosin", "finasteride", "oxybutynin", "sildenafil", "tadalafil",
    # Other common
    "hydroxychloroquine", "azathioprine", "methotrexate",
    "folic acid", "vitamin d", "ferrous sulfate",
]

BRAND_ALIASES = {
    "eliquis": "apixaban",
    "xarelto": "rivaroxaban",
    "zithromax": "azithromycin",
    "valtrex": "valacyclovir",
}

# Shared lookup groups for pattern-family detection.
STRUCTURED_PRN_DRUGS = ["colchicine", "sumatriptan", "rizatriptan", "valacyclovir"]

# Drug categories for extended-course pattern detection.
ANTIBIOTICS = [
    "azithromycin", "cephalexin", "amoxicillin", "ciprofloxacin",
    "doxycycline", "clindamycin", "metronidazole", "trimethoprim",
    "levofloxacin"
]

CHRONIC_DAILY_DRUGS = [
    "lisinopril", "metoprolol", "metoprolol tartrate", "atorvastatin",
    "levothyroxine", "omeprazole", "simvastatin", "amlodipine",
    "losartan", "hydrochlorothiazide", "warfarin", "digoxin"
]

CONTINUOUS_USE_DRUGS = [
    "insulin", "estradiol", "testosterone", "prednisone"
]


def recognize_drug(drug: str) -> tuple[str, Optional[str]]:
    normalized = normalize_drug_name(drug)
    for known in KNOWN_DRUG_NAMES:
        if known in normalized.split() or known in normalized:
            return "Recognized", known

    # Check brand aliases
    for brand, generic in BRAND_ALIASES.items():
        if brand in normalized.split() or brand in normalized:
            return "Recognized", generic

    best_match = None
    best_ratio = 0.0
    for known in KNOWN_DRUG_NAMES:
        ratio = SequenceMatcher(None, normalized, known).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = known
        for token in normalized.split():
            token_ratio = SequenceMatcher(None, token, known).ratio()
            if token_ratio > best_ratio:
                best_ratio = token_ratio
                best_match = known

    if best_match and best_ratio >= 0.75:
        return "Possibly misspelled", best_match

    return "Unrecognized", None


@dataclass
class CasePattern:
    name: str
    structural_issue: str
    affects: str
    clarification: str
    refresh_points: list[str]
    refresh_conclusion: str
    prescriber_message: str
    internal_message: str
    documentation_template: str


def match_case_pattern(drug: str, sig: str, quantity: int, frequency: Optional[str] = None) -> Optional[CasePattern]:
    drug_lower = drug.lower()
    sig_lower = sig.lower()

    if "valacyclovir" in drug_lower and "prn" in sig_lower and frequency == "twice daily" and quantity == 28:
        implied_days = 14

        return CasePattern(
            name="valacyclovir_prn_bid_qty28_no_duration",
            structural_issue=(
                "PRN use is present, but treatment window or episode-based instruction is not stated; "
                f"usage structure is ambiguous and quantity implies up to {implied_days} days at {frequency or 'current'} directions."
            ),
            affects="instructions",
            clarification="Context-dependent",
            refresh_points=[
                "This PRN order commonly includes a defined treatment window.",
                "PRN use stands out because it differs from scheduled directions and needs clear timing guidance.",
                "Quantity supports a longer course than expected for a short episodic pattern.",
            ],
            refresh_conclusion=(
                "PRN valacyclovir without duration and with quantity supporting longer use is structurally unclear."
            ),
            prescriber_message=(
                f"PRN use is listed, but treatment window or episode-based instruction is not stated. "
                f"Current quantity supports up to {implied_days} days at {frequency or 'listed'} directions. "
                "Please clarify intended usage structure."
            ),
            internal_message=(
                f"PRN valacyclovir entered without stated duration; quantity supports up to "
                f"{implied_days} days at {frequency or 'listed'} directions."
            ),
            documentation_template=(
                "Prescription written for {drug}, {sig}, quantity {quantity}, with PRN use noted "
                "but no duration or treatment window specified. Quantity supports up to "
                f"{implied_days} days at {frequency or 'listed'} directions; clarification not present on original order."
            ),
        )

    # Flag metoprolol tartrate daily dosing as a formulation/frequency pattern
    if "metoprolol tartrate" in drug_lower and frequency in ["daily", "once daily"] and quantity == 30:
        return CasePattern(
            name="metoprolol_tartrate_daily_qty30",
            structural_issue=(
                f"{frequency or 'Daily'} dosing for metoprolol tartrate differs from typical dosing practice; "
                "clarification on intended frequency is not stated."
            ),
            affects="frequency",
            clarification="Likely",
            refresh_points=[
                "This formulation is commonly aligned with more frequent administration patterns.",
                f"{frequency or 'Daily'} directions stand out for metoprolol tartrate.",
                f"Quantity is consistent with {frequency or 'daily'} use, so the concern is formulation-frequency alignment.",
            ],
            refresh_conclusion=(
                f"{frequency or 'Daily'} metoprolol tartrate (quantity {quantity}) is structurally notable; confirm formulation-frequency alignment."
            ),
            prescriber_message=(
                f"This order specifies {frequency or 'daily'} dosing for metoprolol tartrate; "
                "please confirm intended dosing frequency."
            ),
            internal_message=(
                f"Metoprolol tartrate {frequency or 'daily'} noted; confirm frequency."
            ),
            documentation_template=(
                "Prescription written for {drug}, {sig}, quantity {quantity}. "
                f"{frequency or 'Daily'} dosing noted for metoprolol tartrate."
            ),
        )

    # Flag extended daily azithromycin quantities as context-dependent
    if "azithromycin" in drug_lower and frequency in ["daily", "once daily"] and quantity >= 30:
        return CasePattern(
            name="azithromycin_daily_extended_qty",
            structural_issue=(
                f"Duration not specified; quantity ({quantity}) suggests an extended {frequency or 'daily'} course."
            ),
            affects="duration",
            clarification="Likely",
            refresh_points=[
                f"{frequency or 'Daily'} courses commonly include a stated duration.",
                "Extended quantity without duration stated.",
                "Quantity suggests longer course than typical short regimens.",
            ],
            refresh_conclusion=(
                f"Extended {frequency or 'daily'} azithromycin ({quantity} tablets) without duration is context-dependent and lacks structural clarity."
            ),
            prescriber_message=(
                f"Quantity implies an extended {frequency or 'daily'} course; please document intended duration or indication."
            ),
            internal_message=(
                f"Quantity suggests extended {frequency or 'daily'} azithromycin; duration/indication not documented."
            ),
            documentation_template=(
                "Prescription written for {drug}, {sig}, quantity {quantity}, with no duration specified. "
                f"Consider documenting duration or indication for extended {frequency or 'daily'} courses."
            ),
        )

    # Flag PRN medications without maximum daily dose when associated with acute therapies or vague wording
    acute_prn_drugs = ["ubrelvy", "sildenafil"]
    has_frequency = (
        "every" in sig_lower or "daily" in sig_lower or "twice" in sig_lower or
        "three" in sig_lower or "four" in sig_lower or "q" in sig_lower or
        "bid" in sig_lower or "tid" in sig_lower or "qid" in sig_lower
    )
    is_vague_prn = ("prn" in sig_lower or "as needed" in sig_lower) and not has_frequency
    is_acute_prn = any(drug in drug_lower for drug in acute_prn_drugs)
    if (is_acute_prn or is_vague_prn) and not ("maximum" in sig_lower or "max" in sig_lower or "up to" in sig_lower):
        if "ubrelvy" in drug_lower:
            refresh_points = [
                "This type of PRN therapy is often paired with a defined dosing limit.",
                "Lack of a maximum dose constraint makes the PRN instruction less structurally clear.",
                "Quantity allows use without a stated dosing limit.",
            ]
        elif "sildenafil" in drug_lower:
            refresh_points = [
                "As-needed wording appears without a frequency or interval anchor.",
                "That makes this PRN instruction more open-ended than a scheduled alternative.",
                "Quantity allows open-ended use without stated limits.",
            ]
        else:
            refresh_points = [
                "PRN orders often pair with a defined dosing limit.",
                "Lack of a maximum dose constraint reduces structural clarity in PRN instructions.",
                "Quantity allows use without stated limits.",
            ]

        return CasePattern(
            name="prn_without_max_dose",
            structural_issue="PRN medication without specified maximum daily dose; dosing constraint not stated.",
            affects="instructions",
            clarification="Likely",
            refresh_points=refresh_points,
            refresh_conclusion=f"PRN orders without maximum constraints (quantity {quantity}) are structurally unclear.",
            prescriber_message="PRN medication without maximum daily dose specified; please clarify intended maximum.",
            internal_message="PRN order noted without maximum daily dose; confirm dosing limits.",
            documentation_template="Prescription written for {drug}, {sig}, quantity {quantity}, PRN without maximum daily dose specified.",
        )

    # Detect conflict between PRN usage and scheduled frequency for structured PRN drugs
    has_prn = "prn" in sig_lower or "as needed" in sig_lower
    is_structured_prn_drug = any(drug_matches_base_name(drug, drug_name) for drug_name in STRUCTURED_PRN_DRUGS)

    if has_prn and frequency and is_structured_prn_drug:
        return CasePattern(
            name="prn_with_scheduled_frequency",
            structural_issue=f"PRN use is combined with {frequency} frequency, making it unclear whether the order is intended for ongoing scheduled use or episodic use.",
            affects="instructions",
            clarification="Context-dependent",
            refresh_points=[
                "PRN instructions typically signal as-needed or episodic use, not a fixed schedule.",
                f"Combining PRN wording with {frequency} makes the intended use pattern unclear.",
                "Clarification is needed to determine whether the order is ongoing scheduled use or episodic use.",
            ],
            refresh_conclusion=f"PRN combined with {frequency} creates structural ambiguity about whether the order is scheduled or episodic.",
            prescriber_message=f"The current wording mixes PRN and {frequency} directions, making it unclear whether the medication is intended for ongoing scheduled use or episodic use. Please clarify the intended use pattern.",
            internal_message=f"PRN with {frequency} noted; intended use pattern is unclear and requires clarification.",
            documentation_template=f"Prescription written for {drug}, {sig}, quantity {quantity}. PRN wording is combined with {frequency}, making intended use pattern unclear.",
        )

    no_explicit_duration = "for" not in sig_lower and "days" not in sig_lower and "weeks" not in sig_lower and "months" not in sig_lower
    has_prn = "prn" in sig_lower or "as needed" in sig_lower

    # Guardrail: flexible non-structured PRN (e.g., daily PRN stool softeners) should
    # not be escalated by broad course-structure challenge rules.
    is_flexible_nonstructured_prn = (
        has_prn
        and no_explicit_duration
        and frequency in ["daily", "once daily"]
        and not is_structured_prn_drug
    )

    # Generic rule for episodic short-regimen orders with large quantity
    # RESTRICTED TO: structured PRN or episodic drug groups only
    # EXCLUDE: antibiotics, chronic daily medications, continuous-use drugs
    
    EPISODIC_PRN_DRUGS = [
        "colchicine", "sumatriptan", "rizatriptan", "valacyclovir", 
        "ubrelvy", "sildenafil"
    ]
    
    # Check if drug belongs to episodic/PRN group
    is_episodic_prn_drug = any(drug_matches_base_name(drug, drug_name) for drug_name in EPISODIC_PRN_DRUGS)
    
    # Exclude antibiotics, chronic daily, and continuous-use drugs
    is_excluded_drug = (
        any(drug_matches_base_name(drug, drug_name) for drug_name in ANTIBIOTICS) or
        any(drug_matches_base_name(drug, drug_name) for drug_name in CHRONIC_DAILY_DRUGS) or
        any(drug_matches_base_name(drug, drug_name) for drug_name in CONTINUOUS_USE_DRUGS)
    )
    
    # Only apply episodic logic to episodic/PRN drugs, exclude the others
    if is_episodic_prn_drug and not is_excluded_drug:
        dose_match = re.search(r'take (\d+) (tablet|capsule)', sig_lower)
        if dose_match:
            dose_per_take = int(dose_match.group(1))
            if 'twice daily' in sig_lower or 'twice a day' in sig_lower or 'bid' in sig_lower:
                daily_dose = dose_per_take * 2
            elif 'three times daily' in sig_lower or 'tid' in sig_lower:
                daily_dose = dose_per_take * 3
            elif 'every 12 hours' in sig_lower or 'q12h' in sig_lower:
                daily_dose = dose_per_take * 2
            elif 'every 8 hours' in sig_lower or 'q8h' in sig_lower:
                daily_dose = dose_per_take * 3
            elif 'every 6 hours' in sig_lower or 'q6h' in sig_lower:
                daily_dose = dose_per_take * 4
            elif 'four times daily' in sig_lower or 'qid' in sig_lower:
                daily_dose = dose_per_take * 4
            elif 'daily' in sig_lower or 'once daily' in sig_lower:
                daily_dose = dose_per_take
            else:
                daily_dose = None

            if daily_dose and quantity > daily_dose * 5 and no_explicit_duration:
                return CasePattern(
                    name="episodic_short_regimen_large_quantity",
                    structural_issue=f"Quantity and directions imply a duration that conflicts with intended course length, creating uncertainty about total exposure.",
                    affects="instructions",
                    clarification="Context-dependent",
                    refresh_points=[
                        f"Current directions suggest {daily_dose} doses per day, implying a {quantity / daily_dose:.1f}-day course.",
                        "Quantity appears larger than typical for a single short course, suggesting potential inconsistency with intended use.",
                        "Clarification needed for intended duration and whether repeated use is appropriate.",
                    ],
                    refresh_conclusion=f"Quantity ({quantity}) and directions suggest {quantity / daily_dose:.1f}-day course; verify intended duration and total exposure.",
                    prescriber_message=f"Quantity of {quantity} creates inconsistency with directions suggesting {daily_dose} doses daily. Please confirm intended duration and total exposure.",
                    internal_message=f"Quantity ({quantity}) implies {quantity / daily_dose:.1f} days at {daily_dose} doses/day; duration verification needed.",
                    documentation_template=f"Prescription written for {drug}, {sig}, quantity {quantity}. Quantity implies {quantity / daily_dose:.1f}-day course at {daily_dose} doses/day.",
                )

    # Stronger handling for antibiotic-like extended courses without stated duration
    is_antibiotic_like = any(drug_matches_base_name(drug, drug_name) for drug_name in ANTIBIOTICS)
    if frequency in ["daily", "once daily"] and no_explicit_duration and quantity >= 21 and is_antibiotic_like:
        return CasePattern(
            name="antibiotic_extended_course_no_duration",
            structural_issue="Quantity and directions imply an extended course, but no duration or treatment context is stated.",
            affects="duration",
            clarification="Likely",
            refresh_points=[
                f"Current directions specify daily scheduled use with quantity consistent with an extended course.",
                "No explicit duration or treatment context is stated.",
                "Clarification is needed to confirm intended duration and indication.",
            ],
            refresh_conclusion=(
                "Current directions and quantity imply an extended course without stated duration or treatment context."
            ),
            prescriber_message=(
                "Current directions and quantity imply an extended course, but no duration or treatment context is stated. "
                "Please clarify intended duration and indication."
            ),
            internal_message=(
                "Quantity and directions imply an extended course without stated duration or treatment context; verify intended course length and indication."
            ),
            documentation_template=(
                "Prescription written for {drug}, {sig}, quantity {quantity}. "
                "Quantity and directions imply an extended course but no duration or treatment context is stated."
            ),
        )

    # Generic rule for PRN with scheduled frequency and explicit long duration
    has_prn = "prn" in sig_lower or "as needed" in sig_lower
    has_explicit_duration = "for" in sig_lower and ("days" in sig_lower or "weeks" in sig_lower or "months" in sig_lower)

    if has_prn and frequency and has_explicit_duration:
        return CasePattern(
            name="prn_scheduled_with_duration",
            structural_issue=f"PRN use is combined with {frequency} schedule and a long duration, creating ambiguity between episodic and ongoing use.",
            affects="instructions",
            clarification="Context-dependent",
            refresh_points=[
                "PRN wording suggests episodic use, but scheduled frequency and long duration suggest ongoing use.",
                f"Combining PRN with {frequency} and duration creates ambiguity in the intended use pattern.",
                "Clarification is needed to distinguish between episodic and continuous use.",
            ],
            refresh_conclusion=f"PRN with {frequency} and long duration creates ambiguity between episodic and ongoing use patterns.",
            prescriber_message=f"PRN use is combined with {frequency} schedule and explicit duration, creating ambiguity between episodic and ongoing use. Please clarify the intended use pattern.",
            internal_message=f"PRN with {frequency} and duration noted; use pattern ambiguity requires clarification.",
            documentation_template=f"Prescription written for {drug}, {sig}, quantity {quantity}. PRN combined with {frequency} and duration creates use pattern ambiguity.",
        )

    # Generic rule for non-daily dosing ambiguity
    non_daily_frequencies = [
        "weekly", "monthly", "every week", "every month", "every other day",
        "alternating days", "twice weekly", "three times weekly", "four times weekly",
        "twice monthly", "three times monthly", "every 2 weeks", "biweekly",
        "every 3 days", "every 4 days", "every 5 days", "every 6 days"
    ]
    
    has_non_daily_frequency = any(term in sig_lower for term in non_daily_frequencies)
    
    # Check if administration pattern is clearly defined
    # Pattern is NOT clearly defined if it doesn't specify distribution
    administration_indicators = [
        "all at once", "at the same time", "together", "once a week", "once weekly",
        "once a month", "once monthly", "one each day", "one per day", "divided",
        "split", "distributed", "throughout the", "over the", "across the"
    ]
    
    has_clear_administration = any(indicator in sig_lower for indicator in administration_indicators)
    
    if has_non_daily_frequency and not has_clear_administration:
        return CasePattern(
            name="non_daily_dosing_ambiguity",
            structural_issue="Non-daily dosing is specified, but the administration pattern is not clearly defined.",
            affects="instructions",
            clarification="Context-dependent",
            refresh_points=[
                "Non-daily dosing often benefits from explicit administration instructions.",
                "The current wording gives frequency but not how the total dose should be taken.",
                "Quantity may support repeated non-daily dosing, but the per-dose administration pattern is unclear.",
            ],
            refresh_conclusion="Non-daily dosing without clear administration pattern creates ambiguity about how the medication should be taken.",
            prescriber_message="Non-daily dosing is listed, but the administration pattern is not clearly defined. Please clarify how the medication should be taken.",
            internal_message="Non-daily dosing noted without clear administration pattern; clarification needed for how medication should be taken.",
            documentation_template=f"Prescription written for {drug}, {sig}, quantity {quantity}. Non-daily dosing specified without clear administration pattern.",
        )

    # Generic rule for quantity-SIG consistency
    # Check for structural inconsistency between quantity and dosing directions
    
    # Parse dose per administration (e.g., "take 1 tablet" = 1)
    dose_match = re.search(r'take (\d+) (tablet|capsule|pill)', sig_lower)
    if dose_match and not is_flexible_nonstructured_prn:
        dose_per_admin = int(dose_match.group(1))

        # Parse frequency to get doses per day
        doses_per_day = None
        if 'four times daily' in sig_lower or 'qid' in sig_lower:
            doses_per_day = 4
        elif 'three times daily' in sig_lower or 'tid' in sig_lower:
            doses_per_day = 3
        elif 'twice daily' in sig_lower or 'twice a day' in sig_lower or 'bid' in sig_lower:
            doses_per_day = 2
        elif 'once daily' in sig_lower or 'every day' in sig_lower or 'daily' in sig_lower:
            doses_per_day = 1
        elif 'every 12 hours' in sig_lower or 'q12h' in sig_lower:
            doses_per_day = 2
        elif 'every 8 hours' in sig_lower or 'q8h' in sig_lower:
            doses_per_day = 3
        elif 'every 6 hours' in sig_lower or 'q6h' in sig_lower:
            doses_per_day = 4
        elif 'every 4 hours' in sig_lower:
            doses_per_day = 6
        elif 'every 2 hours' in sig_lower:
            doses_per_day = 12

        if doses_per_day:
            expected_daily_dose = dose_per_admin * doses_per_day
            implied_duration_days = quantity / expected_daily_dose

            # --- NEW LOGIC: Only trigger mismatch if one of the following ---
            # 1. Explicit duration exists AND implied_duration_days does not match it
            explicit_duration_match = re.search(r'for (\d+) (day|days|week|weeks|month|months)', sig_lower)
            explicit_duration = None
            if explicit_duration_match:
                num = int(explicit_duration_match.group(1))
                unit = explicit_duration_match.group(2)
                if 'week' in unit:
                    explicit_duration = num * 7
                elif 'month' in unit:
                    explicit_duration = num * 30
                else:
                    explicit_duration = num
            duration_mismatch = False
            if explicit_duration:
                # Allow 1-day rounding tolerance
                if abs(implied_duration_days - explicit_duration) > 1:
                    duration_mismatch = True

            # 2. Single-dose pattern AND quantity exceeds expected single-dose amount
            single_dose_pattern = doses_per_day == 1 and explicit_duration == 1
            single_dose_excess = single_dose_pattern and quantity > dose_per_admin

            # 3. Clearly non-reconcilable quantity/regimen structure
            # (e.g., quantity does not divide evenly and remainder is significant)
            non_reconcilable = False
            if quantity % expected_daily_dose != 0:
                remainder = quantity % expected_daily_dose
                if remainder > expected_daily_dose * 0.1:
                    non_reconcilable = True

            # 4. Implied duration is unusually long (>30 days for most medications)
            unusually_long = implied_duration_days > 30

            # 5. Implied duration is very short (<1 day) but quantity suggests multiple doses
            very_short = implied_duration_days < 1 and quantity > expected_daily_dose

            # 6. Quantity implies a course much longer than typical short-term therapy
            # Flag if quantity suggests >10 days for medications typically used short-term
            long_short_term = implied_duration_days > 10 and quantity > expected_daily_dose * 7

            # 7. Suppress for routine maintenance fills (e.g., daily qty 30, BID qty 60, etc.)
            is_maintenance = (
                (doses_per_day == 1 and quantity in [28, 30, 31, 32, 90]) or
                (doses_per_day == 2 and quantity in [56, 60, 62, 90]) or
                (doses_per_day == 3 and quantity in [84, 90])
            )

            # Only emit an issue if a real mismatch, ambiguity, or uncertainty is detected
            if (
                duration_mismatch
                or single_dose_excess
                or non_reconcilable
                or unusually_long
                or very_short
                or long_short_term
            ) and not is_maintenance:
                structural_issue_text = "Quantity and directions imply a duration that may be inconsistent with intended course length."
                if unusually_long:
                    structural_issue_text = f"Quantity implies an unusually long course ({implied_duration_days:.1f} days) that conflicts with current directions."
                return CasePattern(
                    name="quantity_sig_consistency",
                    structural_issue=structural_issue_text,
                    affects="duration",
                    clarification="Likely",
                    refresh_points=[
                        f"Current directions suggest {expected_daily_dose} doses per day ({dose_per_admin} × {doses_per_day}).",
                        f"Quantity of {quantity} implies approximately {implied_duration_days:.1f} days of therapy.",
                        "Quantity-frequency mismatch creates uncertainty about intended course length and needs clarification.",
                    ],
                    refresh_conclusion=f"Quantity ({quantity}) and directions suggest {implied_duration_days:.1f}-day course; verify intended duration and total exposure.",
                    prescriber_message=f"Quantity of {quantity} creates inconsistency with directions suggesting {expected_daily_dose} doses daily. Please confirm intended duration and total exposure.",
                    internal_message=f"Quantity ({quantity}) implies {implied_duration_days:.1f} days at {expected_daily_dose} doses/day; duration verification needed.",
                    documentation_template=f"Prescription written for {drug}, {sig}, quantity {quantity}. Quantity implies {implied_duration_days:.1f}-day course at {expected_daily_dose} doses/day.",
                )
    return None