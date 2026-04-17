import re
from models import ParsedPrescription
from typing import Optional


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

    # Common frequency patterns
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

    return None


def parse_prescription_line(raw_text: str) -> ParsedPrescription:
    """
    Expected example:
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
        sig_start = re.search(r"\b(take|use|apply|inhale|instill|inject)\b", normalized_text, flags=re.IGNORECASE)
        if not sig_start:
            raise ValueError(
                "Could not find SIG directions. Add directions starting with take/use/apply/inhale/instill/inject. "
                "Example: Valacyclovir 1 gm take 1 tablet by mouth every 12 hours qty 28"
            )
        drug = normalized_text[:sig_start.start()].strip(" -")
        right_side = normalized_text[sig_start.start():].strip()

    if not drug:
        raise ValueError("Could not identify the drug segment before SIG directions.")

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
    
    # Parse frequency from SIG
    frequency = parse_frequency(sig)

    return ParsedPrescription(
        raw_text=text,
        drug=drug,
        sig=sig,
        quantity=quantity,
        frequency=frequency,
    )