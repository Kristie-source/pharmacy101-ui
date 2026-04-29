from patterns import is_pattern_safe_drug
import re
from models import ParsedPrescription
from typing import Optional
from structure_patterns import classify_structure_pattern


# CATEGORY A: drugs that require a distinguishing product qualifier (salt form, release type, formulation).
# CATEGORY B: drugs that require strength only, no product qualifier.
# This is a focused, high-value validation list for practical product identification.

# Generic, maintainable rule table for drugs that require distinguishing qualifiers.
# Each base drug name must include at least one qualifier from the list below.
ENHANCED_IDENTITY_RULES = {
    # Category A: require product qualifier
    "metoprolol": {
        "required_qualifiers": ["succinate", "tartrate"],
    },
    "bupropion": {
        "required_qualifiers": ["xl", "xr", "sr", "ir", "extended", "sustained", "immediate"],
    },
    "venlafaxine": {
        "required_qualifiers": ["xr", "xl", "er", "extended"],
    },
}


# Maintainable strength-validation rules for recognized medications.
# Values are normalized to mg or mcg for comparison when possible.
KNOWN_VALID_STRENGTHS = {
    # Category B: strength validation only
    "lisinopril": {
        "normalize_to": "mg",
        "allowed_values": [2.5, 5, 10, 20, 30, 40],
    },
    "valacyclovir": {
        "normalize_to": "mg",
        "allowed_values": [500, 1000],
    },
    "levothyroxine": {
        "normalize_to": "mcg",
        "allowed_values": [25, 50, 75, 88, 100, 112, 125, 137, 150, 175, 200, 225, 250, 300],
    },
}


def normalize_sig_shorthand(right_side: str) -> str:
    """
    Expand common shorthand in the SIG/right-side text while preserving
    the existing parser architecture.
    """
    normalized = right_side.strip()

    # Normalize quantity spellings to a single form used by the parser.
    normalized = re.sub(r"#\s*(\d+)\b", r"(qty \1)", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"(?<!\()\b(?:qty|quantity)\s*[:=]?\s*(\d+)\b(?!\))",
        r"(qty \1)",
        normalized,
        flags=re.IGNORECASE,
    )

    # Dose-form shorthand such as 1t / 2t / 1c / 2c.
    def _expand_dose_form(match: re.Match) -> str:
        amount = int(match.group(1))
        unit_code = match.group(2).lower()
        if unit_code == "t":
            unit = "tablet" if amount == 1 else "tablets"
        else:
            unit = "capsule" if amount == 1 else "capsules"
        return f"{amount} {unit}"

    normalized = re.sub(r"\b(\d+)\s*([tc])\b", _expand_dose_form, normalized, flags=re.IGNORECASE)

    # Frequency shorthand like q12h, q8h.
    normalized = re.sub(r"\bq\s*(\d+)\s*h\b", r"every \1 hours", normalized, flags=re.IGNORECASE)

    token_replacements = [
        (r"\bpo\b", "by mouth"),
        (r"\bprn\b", "as needed"),
        (r"\bbid\b", "twice daily"),
        (r"\btid\b", "three times daily"),
        (r"\bqid\b", "four times daily"),
        (r"\bqd\b", "daily"),
        (r"\bqod\b", "every other day"),
        (r"\btab\b", "tablet"),
        (r"\btabs\b", "tablets"),
    ]
    for pattern, replacement in token_replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    # Keep output tidy and predictable.
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _find_unresolved_shorthand(sig: str) -> Optional[str]:
    """Return unresolved shorthand token text if any known shorthand remains."""
    unresolved = re.search(
        r"\b(?:po|prn|bid|tid|qid|qd|qod|q\d+h|\d+[tc]|hs|qhs|qam|qpm|ac|pc)\b",
        sig,
        flags=re.IGNORECASE,
    )
    return unresolved.group(0) if unresolved else None


def _validate_enhanced_drug_identity(drug: str) -> None:
    """Require additional qualifiers for selected base drug names."""
    drug_lower = drug.lower()

    for base_name, rule in ENHANCED_IDENTITY_RULES.items():
        if not re.search(rf"\b{re.escape(base_name)}\b", drug_lower):
            continue

        required_qualifiers = rule.get("required_qualifiers", [])
        has_required_qualifier = any(
            re.search(rf"\b{re.escape(qualifier)}\b", drug_lower)
            for qualifier in required_qualifiers
        )
        if not has_required_qualifier:
            raise ValueError(
                "Missing required drug qualifier. Specify salt form, release type, or formulation as needed for this medication."
            )


def _extract_strength_value_and_unit(drug: str) -> Optional[tuple[float, str]]:
    """Extract the first numeric strength token from the drug segment."""
    match = re.search(
        r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|g|gm|grams?|milligrams?|micrograms?|mEq|units?|IU|ml|mL)\b",
        drug,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return float(match.group("value")), match.group("unit").lower()


def _to_mg(value: float, unit: str) -> Optional[float]:
    """Convert supported mass units to mg. Return None when not comparable as mass."""
    if unit in {"mg", "milligram", "milligrams"}:
        return value
    if unit in {"mcg", "microgram", "micrograms"}:
        return value / 1000.0
    if unit in {"g", "gm", "gram", "grams"}:
        return value * 1000.0
    return None


def _to_mcg(value: float, unit: str) -> Optional[float]:
    """Convert supported mass units to mcg. Return None when not comparable as mass."""
    if unit in {"mcg", "microgram", "micrograms"}:
        return value
    if unit in {"mg", "milligram", "milligrams"}:
        return value * 1000.0
    if unit in {"g", "gm", "gram", "grams"}:
        return value * 1000000.0
    return None


def _validate_known_strength_for_recognized_medication(drug: str) -> None:
    """
    Validate entered strength for recognized medications when a trusted
    known-strength rule exists. Skip rejection when strength comparison is unsafe.
    """
    drug_lower = drug.lower()
    extracted_strength = _extract_strength_value_and_unit(drug)
    if not extracted_strength:
        return

    entered_value, entered_unit = extracted_strength

    for base_name, rule in KNOWN_VALID_STRENGTHS.items():
        if not re.search(rf"\b{re.escape(base_name)}\b", drug_lower):
            continue

        active_rule = rule
        qualifier_rules = rule.get("qualifier_rules")
        if qualifier_rules:
            active_rule = None
            for qualifier, qualifier_rule in qualifier_rules.items():
                if re.search(rf"\b{re.escape(qualifier)}\b", drug_lower):
                    active_rule = qualifier_rule
                    break
            if active_rule is None:
                # Not specific enough to validate strength safely.
                return

        normalize_to = active_rule.get("normalize_to")
        allowed_values = active_rule.get("allowed_values", [])
        if not normalize_to or not allowed_values:
            return

        if normalize_to == "mg":
            entered_normalized = _to_mg(entered_value, entered_unit)
            if entered_normalized is None:
                # Unit cannot be safely compared for this rule.
                return
            if not any(abs(entered_normalized - float(v)) < 1e-9 for v in allowed_values):
                raise ValueError(
                    "Invalid strength for this medication. Verify the drug strength entered."
                )
        elif normalize_to == "mcg":
            entered_normalized = _to_mcg(entered_value, entered_unit)
            if entered_normalized is None:
                # Unit cannot be safely compared for this rule.
                return
            if not any(abs(entered_normalized - float(v)) < 1e-9 for v in allowed_values):
                raise ValueError(
                    "Invalid strength for this medication. Verify the drug strength entered."
                )
        return


def parse_frequency(sig: str) -> Optional[str]:
    """
    Extract frequency information from SIG text.
    Returns the frequency string if found, None otherwise.
    """
    sig_lower = sig.lower().strip()

    # Remove common trailing counseling/advisory text so the main dosing clause is parsed first.
    sig_lower = re.sub(
        r"\b(?:drink plenty of water|take with food|with meals|avoid alcohol|as directed)\b[\.\s]*$",
        "",
        sig_lower,
        flags=re.IGNORECASE,
    )

    # Only consider the first sentence as the main dosing clause.
    if "." in sig_lower:
        sig_lower = sig_lower.split(".", 1)[0].strip()

    # One-time/single-dose regimens are valid complete structures even without recurring cadence.
    if _is_single_dose_structure(sig_lower):
        return "single dose"

    # Common recurring frequency patterns
    frequency_patterns = [
        r'every\s+(\d+)\s+hours?',
        r'every\s+(\d+)\s+hrs?',
        r'q(\d+)h',
        r'every\s+other\s+day',
        r'weekly',
        r'(?:one|two|three|four|\d+)\s+times\s+(?:a|per)\s+day',
        r'(?:twice|three times|four times)\s+daily',
        r'once\s+daily',
        r'once\s+a\s+day',
        r'twice\s+a\s+day',
        r'three\s+times\s+a\s+day',
        r'four\s+times\s+a\s+day',
        r'twice\s+daily',
        r'three\s+times\s+daily',
        r'four\s+times\s+daily',
        r'daily',
        r'bid',
        r'tid',
        r'qid',
    ]

    for pattern in frequency_patterns:
        match = re.search(pattern, sig_lower, re.IGNORECASE)
        if match:
            if len(match.groups()) > 0:
                # For patterns with capture groups
                if 'every' in pattern and 'hours' in pattern:
                    return f"every {match.group(1)} hours"
                elif 'q' in pattern and 'h' in pattern:
                    return f"every {match.group(1)} hours"
                elif 'times' in pattern:
                    num = match.group(1)
                    if num in ['one', '1']:
                        return "once daily"
                    elif num in ['two', '2']:
                        return "twice daily"
                    elif num in ['three', '3']:
                        return "three times daily"
                    elif num in ['four', '4']:
                        return "four times daily"
                    else:
                        return f"{num} times daily"
            else:
                # For exact matches
                if 'twice daily' in sig_lower:
                    return "twice daily"
                elif 'three times daily' in sig_lower:
                    return "three times daily"
                elif 'four times daily' in sig_lower:
                    return "four times daily"
                elif 'once daily' in sig_lower:
                    return "once daily"
                elif 'twice a day' in sig_lower:
                    return "twice daily"
                elif 'three times a day' in sig_lower:
                    return "three times daily"
                elif 'four times a day' in sig_lower:
                    return "four times daily"
                elif 'once a day' in sig_lower:
                    return "once daily"
                elif 'daily' in sig_lower:
                    return "daily"
                elif 'every other day' in sig_lower:
                    return "every other day"
                elif 'weekly' in sig_lower:
                    return "weekly"
                elif 'bid' in sig_lower:
                    return "twice daily"
                elif 'tid' in sig_lower:
                    return "three times daily"
                elif 'qid' in sig_lower:
                    return "four times daily"

    # If no standard frequency found, check for contextual meal-frequency phrases
    if "before meals" in sig_lower:
        return "before meals"
    elif "with meals" in sig_lower:
        return "with meals"
    elif "after meals" in sig_lower:
        return "after meals"

    return None


def _is_single_dose_structure(sig: str) -> bool:
    sig_lower = str(sig or "").lower().strip()
    if not sig_lower:
        return False

    explicit_one_time_patterns = [
        r"\bfor\s+(?:one|1)\s+dose\b",
        r"\bsingle\s*dose\b",
        r"\bone[-\s]?time\b",
        r"\bx\s*1\b",
    ]
    if any(re.search(pattern, sig_lower) for pattern in explicit_one_time_patterns):
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
    if any(re.search(pattern, sig_lower) for pattern in recurring_once_patterns):
        return False

    return True


def parse_prescription_line(raw_text: str) -> ParsedPrescription:
    """
    Required elements for a valid shorthand prescription input:
    - Drug name
    - Required qualifier when applicable (for example, tartrate/succinate)
    - Strength
    - Dose amount in the SIG (for example, 1t, 1 tab, 2 tabs)
    - Usable frequency
    - Quantity

    Example:
    Valacyclovir 1 gm - take 1 tablet by mouth every 12 hours (qty 28)
    """

    text = re.sub(r"\s+", " ", raw_text or "").strip()
    if not text:
        raise ValueError(
            "No prescription text found. Example: "
            "Valacyclovir 1 gm - take 1 tablet by mouth every 12 hours (qty 28)"
        )

    normalized_text = normalize_sig_shorthand(text)

    # Split into left side (drug/strength) and right side (sig + qty).
    # Hyphen is preferred but optional if SIG starts with a known action verb.
    split_match = re.match(r"^(?P<drug>.+?)\s*-\s*(?P<sig>.+)$", normalized_text)
    if split_match:
        drug = split_match.group("drug").strip()
        right_side = split_match.group("sig").strip()
    else:
        # Try a SIG action verb first (take / use / apply / …).
        sig_start = re.search(r"\b(take|use|apply|inhale|instill|inject)\b", normalized_text, flags=re.IGNORECASE)
        if not sig_start:
            # Fall back: SIG may start with a dose-form amount without a verb,
            # e.g. "1 tablet" / "2 capsules" in shorthand notation.
            sig_start = re.search(r"\b\d+\s+(?:tablets?|capsules?)\b", normalized_text, flags=re.IGNORECASE)
        if not sig_start:
            raise ValueError(
                "Could not find SIG directions. Add directions starting with take/use/apply/inhale/instill/inject. "
                "Example: Valacyclovir 1 gm take 1 tablet by mouth every 12 hours qty 28"
            )
        drug = normalized_text[:sig_start.start()].strip(" -")
        right_side = normalized_text[sig_start.start():].strip()

    if not drug:
        raise ValueError("Could not identify the drug segment before SIG directions.")

    # Require an explicit drug strength in the drug segment unless drug is pattern-safe.
    # A strength must contain a numeric value followed by a mass/volume unit.
    strength_pattern = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|grams?|milligrams?|micrograms?|mEq|units?|IU|ml|mL)\b",
        re.IGNORECASE,
    )
    if not strength_pattern.search(drug):
        if not is_pattern_safe_drug(drug):
            raise ValueError(
                "Missing drug strength. When drug name, SIG, and quantity are present, strength is required (for example, 500 mg or 1 g)."
            )
        # Optionally: add a low-priority note that strength was not supplied, but analysis continued
        # (Implementation of note is context-dependent; here, just pass)

    _validate_enhanced_drug_identity(drug)
    _validate_known_strength_for_recognized_medication(drug)

    # Extract quantity from normalized qty forms (qty 28), qty 28, or #28.
    qty_match = re.search(r"\(qty\s*(\d+)\)", right_side, re.IGNORECASE)
    if not qty_match:
        raise ValueError(
            "Could not find quantity. Include one of: '(qty 28)', 'qty 28', or 'quantity 28'."
        )

    quantity = int(qty_match.group(1))

    # Remove the qty part from the sig
    sig = re.sub(r"\(qty\s*\d+\)", "", right_side, flags=re.IGNORECASE).strip()
    sig = re.sub(r"\s+", " ", sig)

    if not sig:
        raise ValueError("SIG directions are missing after quantity removal.")

    unresolved = _find_unresolved_shorthand(sig)
    if unresolved:
        raise ValueError(
            f"Parsing incomplete: unresolved shorthand '{unresolved}' in SIG. "
            "Please expand it (for example, 'qhs' -> 'nightly') and try again."
        )

    # Run structure-only pattern detection before missing-field checks.
    structure_pattern = classify_structure_pattern(sig)

    # Allow missing dose amount: do not raise INVALID, just record missing element for downstream analysis.
    has_dose_amount = bool(
        re.search(
            r"\b\d+\s*(?:tablets?|tabs?|capsules?|caps?|puffs?|drops?|teaspoons?|tsp|ml|mL)\b",
            sig,
            flags=re.IGNORECASE,
        )
    )
    # Parse frequency from SIG
    frequency = parse_frequency(sig)

    if not frequency and _is_single_dose_structure(sig):
        frequency = "single dose"

    if not frequency and _is_event_based_prn_structure(sig):
        frequency = "event-based PRN"

    if not frequency and structure_pattern.requires_frequency:
        raise ValueError(
            "Missing usable SIG frequency. Include a schedule such as daily, BID, TID, q12h, or weekly."
        )

    # Only return INVALID if both drug and sig are missing/unparseable (already handled above).
    # Otherwise, allow missing dose and let downstream analysis handle it.
    return ParsedPrescription(
        raw_text=text,
        drug=drug,
        sig=sig,
        quantity=quantity,
        frequency=frequency,
        structure_pattern=structure_pattern.pattern_name,
        structure_complete=structure_pattern.structurally_complete,
        structure_missing=structure_pattern.missing_elements,
    )
def _is_event_based_prn_structure(sig: str) -> bool:
    sig_lower = sig.lower()

    event_based_terms = [
        "at onset",
        "onset of migraine",
        "at first sign",
        "for migraine",
        "migraine",
        "may repeat",
        "as needed",
        "prn",
    ]

    return any(term in sig_lower for term in event_based_terms)

def generate_ready_to_send_message(drug: str, sig: str, quantity: int | str, issue_text: str = "") -> str:
    """
    Creates concise pharmacist-to-prescriber clarification messages.
    Avoids vague language like 'may benefit from documentation.'
    """

    drug_lower = drug.lower()
    sig_lower = sig.lower()
    issue_lower = issue_text.lower()

    # Quantity exceeds single-dose regimen
    if "once" in sig_lower and str(quantity).isdigit() and int(quantity) > 2:
        return (
            "The quantity exceeds a single-dose regimen. "
            "Please confirm if additional dosing is intended, such as repeat dosing or partner therapy."
        )

    # Migraine / triptan missing repeat limits
    if any(term in drug_lower for term in ["sumatriptan", "rizatriptan", "zolmitriptan", "naratriptan", "eletriptan"]):
        if "may repeat" in sig_lower and not any(term in sig_lower for term in ["max", "maximum", "24 hours", "per day"]):
            return (
                "Repeat dosing limits are incomplete. "
                "Please confirm the repeat interval and maximum daily dose."
            )

    # Metoprolol tartrate once daily
    if "metoprolol tartrate" in drug_lower and any(term in sig_lower for term in ["daily", "once daily", "qd"]):
        return (
            "The dosing schedule may not align with the intended formulation. "
            "Please confirm whether metoprolol tartrate once daily is intended or if a different formulation/frequency was meant."
        )

    # Quantity/duration mismatch
    if any(term in issue_lower for term in ["quantity mismatch", "qty mismatch", "quantity does not match", "math mismatch"]):
        return (
            "The quantity does not match the written directions and duration. "
            "Please confirm the intended quantity or treatment length."
        )

    # Missing duration
    if any(term in issue_lower for term in ["missing duration", "duration missing", "treatment length"]):
        return (
            "Treatment duration is not specified. "
            "Please confirm the intended length of therapy."
        )

    # PRN missing max dose
    if any(term in sig_lower for term in ["prn", "as needed"]) and not any(term in sig_lower for term in ["max", "maximum", "per day", "24 hours"]):
        return (
            "As-needed dosing limits are incomplete. "
            "Please confirm the maximum daily dose or use limit."
        )

    # Conflicting regimen
    if any(term in issue_lower for term in ["conflicting", "multiple regimens", "scheduled and prn"]):
        return (
            "The directions contain conflicting use patterns. "
            "Please confirm the intended regimen so the patient receives one clear set of instructions."
        )

    # Indication needed
    if any(term in issue_lower for term in ["indication", "intent"]):
        return (
            "Indication is needed to confirm the intended dosing pattern. "
            "Please confirm what this medication is being used to treat."
        )

    # Fallback: still specific, not vague
    return (
        "The directions are unclear as written. "
        "Please confirm the intended dosing instructions."
    )