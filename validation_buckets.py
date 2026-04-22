from dataclasses import dataclass
from typing import Callable, Optional

from models import ParsedPrescription, PatternResult
from parser import parse_prescription_line
from patterns import (
    detect_acute_use_chronic_quantity,
    detect_dose_unit_formulation_inconsistency,
    detect_duration_central_missing_duration,
    detect_formulation_frequency_mismatch,
    detect_pattern_families,
    is_lisinopril_standard_daily_verify,
)


INVALID_BUCKET = "INVALID"
FLAG_BUCKET = "FLAG"
VERIFY_AS_ENTERED_BUCKET = "VERIFY_AS_ENTERED"


@dataclass(frozen=True)
class InvalidBucketOutcome:
    parsed: Optional[ParsedPrescription]
    error: Optional[str] = None

    @property
    def is_invalid(self) -> bool:
        return self.parsed is None


SPECIFIC_FLAG_RULE_DETECTORS: tuple[Callable[[ParsedPrescription], Optional[PatternResult]], ...] = (
    detect_dose_unit_formulation_inconsistency,
    detect_formulation_frequency_mismatch,
    detect_acute_use_chronic_quantity,
    detect_duration_central_missing_duration,
)

GENERIC_STRUCTURAL_RULE_DETECTORS: tuple[Callable[[ParsedPrescription], Optional[PatternResult]], ...] = (
    detect_pattern_families,
)

VERIFY_RULE_CHECKS: tuple[Callable[[ParsedPrescription], bool], ...] = (
    is_lisinopril_standard_daily_verify,
)


def run_invalid_bucket(raw_text: str) -> InvalidBucketOutcome:
    """INVALID bucket.

    Parsing and completeness checks remain the active invalid gate.
    This wrapper centralizes the bucket without changing parser behavior.
    """
    try:
        return InvalidBucketOutcome(parsed=parse_prescription_line(raw_text))
    except ValueError as exc:
        return InvalidBucketOutcome(parsed=None, error=str(exc))


def run_specific_flag_bucket(parsed: ParsedPrescription) -> Optional[PatternResult]:
    """SPECIFIC FLAG bucket.

    Add future specific structural/clinical pattern rules here.
    Rules are evaluated in order and the first match wins.
    """
    for detector in SPECIFIC_FLAG_RULE_DETECTORS:
        result = detector(parsed)
        if result:
            return result
    return None


def run_generic_structural_bucket(parsed: ParsedPrescription) -> Optional[PatternResult]:
    """GENERIC STRUCTURAL bucket.

    Runs only when no specific FLAG rule matched.
    Rules are evaluated in order and the first match wins.
    """
    for detector in GENERIC_STRUCTURAL_RULE_DETECTORS:
        result = detector(parsed)
        if result:
            return result
    return None


def run_flag_bucket(parsed: ParsedPrescription) -> Optional[PatternResult]:
    """Backward-compatible alias for specific FLAG bucket."""
    return run_specific_flag_bucket(parsed)


def is_verify_as_entered_bucket(
    parsed: ParsedPrescription,
    specific_flag_pattern: Optional[PatternResult],
    generic_structural_pattern: Optional[PatternResult],
    generic_case_pattern: Optional[object],
) -> bool:
    """VERIFY_AS_ENTERED bucket.

    This bucket is reached only when:
    - no specific FLAG rule matches
    - no generic structural rule matches
    - no generic case-library structural pattern matches

    Explicit positive-pass rules can be layered here without overriding INVALID/FLAG.
    """
    if specific_flag_pattern is not None:
        return False
    if generic_structural_pattern is not None:
        return False
    if generic_case_pattern is not None:
        return False

    # Explicit verify-as-entered rule(s) are evaluated first.
    if any(check(parsed) for check in VERIFY_RULE_CHECKS):
        return True

    # Preserve existing behavior: no FLAG pattern means verify as entered.
    return True