from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
import re


@dataclass(frozen=True)
class StructurePatternClassification:
    pattern_name: str
    structurally_complete: bool
    missing_elements: List[str] = field(default_factory=list)
    requires_frequency: bool = True
    requires_duration: bool = False
    frequency_satisfied: bool = False
    duration_satisfied: bool = False


def _has_dose_amount(sig: str) -> bool:
    return bool(
        re.search(
            r"\b\d+\s*(?:tablets?|tabs?|capsules?|caps?|puffs?|drops?|teaspoons?|tsp|ml|mL)\b",
            str(sig or ""),
            flags=re.IGNORECASE,
        )
    )


def _has_duration(sig: str) -> bool:
    return bool(
        re.search(
            r"\b(?:for\s+\d+\s*(?:days?|weeks?|months?)|x\s*\d+\s*(?:days?|weeks?|months?))\b",
            str(sig or "").lower(),
        )
    )


def _is_single_dose(sig: str) -> bool:
    sig_lower = str(sig or "").lower().strip()
    if not sig_lower:
        return False

    explicit_patterns = [
        r"\bfor\s+(?:one|1)\s+dose\b",
        r"\bsingle\s*dose\b",
        r"\bone[-\s]?time\b",
        r"\bx\s*1\b",
    ]
    if any(re.search(pattern, sig_lower) for pattern in explicit_patterns):
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


def _has_scheduled_frequency(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    return bool(
        re.search(
            r"\b(?:daily|once\s+daily|once\s+a\s+day|twice\s+daily|three\s+times\s+daily|four\s+times\s+daily|bid|tid|qid|every\s+\d+\s+hours?|q\d+h|weekly|every\s+other\s+day)\b",
            sig_lower,
        )
    )


def _is_prn(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    return "prn" in sig_lower or "as needed" in sig_lower


def _has_prn_bounds(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    return bool(
        re.search(
            r"\b(?:max(?:imum)?\b|not\s+to\s+exceed|up\s+to\s+\d+\s*(?:tablets?|capsules?|doses?)|every\s+\d+\s+hours?|q\d+h|no\s+more\s+than|\d+\s+times\s+(?:daily|a\s+day))",
            sig_lower,
        )
    )


def _is_episode_based_prn(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    triggers = [
        "at onset",
        "when symptoms start",
        "before travel",
        "before flying",
        "before procedure",
        "before intercourse",
        "for migraine",
        "for headache",
    ]
    return _is_prn(sig_lower) and any(trigger in sig_lower for trigger in triggers)


def _is_taper(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    has_step_words = any(token in sig_lower for token in ["then", "taper", "decrease", "reduce", "followed by"])
    dose_mentions = re.findall(r"\b\d+\s*(?:tablets?|tabs?|capsules?|caps?|mg|mcg|g|gm)\b", sig_lower)
    return has_step_words and len(dose_mentions) >= 2


def _is_weekly_variable_day(sig: str) -> bool:
    sig_lower = str(sig or "").lower()
    weekday_tokens = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    has_weekday_mapping = sum(1 for token in weekday_tokens if token in sig_lower) >= 2
    variable_tokens = ["every other day", "alternating", "alternate days", "weekly", "twice weekly", "three times weekly"]
    return has_weekday_mapping or any(token in sig_lower for token in variable_tokens)


def classify_structure_pattern(sig: str) -> StructurePatternClassification:
    has_dose = _has_dose_amount(sig)
    has_duration = _has_duration(sig)
    has_scheduled_frequency = _has_scheduled_frequency(sig)
    is_prn = _is_prn(sig)

    if _is_single_dose(sig):
        missing = [] if has_dose else ["dose_amount"]
        return StructurePatternClassification(
            pattern_name="single_dose",
            structurally_complete=not missing,
            missing_elements=missing,
            requires_frequency=False,
            requires_duration=False,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    if _is_taper(sig):
        missing = [] if has_dose else ["dose_amount"]
        return StructurePatternClassification(
            pattern_name="taper",
            structurally_complete=not missing,
            missing_elements=missing,
            requires_frequency=False,
            requires_duration=False,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    if _is_weekly_variable_day(sig):
        missing = []
        if not has_dose:
            missing.append("dose_amount")
        return StructurePatternClassification(
            pattern_name="weekly_variable_day",
            structurally_complete=not missing,
            missing_elements=missing,
            requires_frequency=False,
            requires_duration=False,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    if _is_episode_based_prn(sig):
        missing = []
        if not has_dose:
            missing.append("dose_amount")
        if not _has_prn_bounds(sig):
            missing.append("prn_bounds")
        return StructurePatternClassification(
            pattern_name="episode_based_prn",
            structurally_complete=not missing,
            missing_elements=missing,
            requires_frequency=False,
            requires_duration=False,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    if is_prn:
        if _has_prn_bounds(sig):
            missing = [] if has_dose else ["dose_amount"]
            return StructurePatternClassification(
                pattern_name="prn_bounded",
                structurally_complete=not missing,
                missing_elements=missing,
                requires_frequency=False,
                requires_duration=False,
                frequency_satisfied=True,
                duration_satisfied=True,
            )

        missing = [] if has_dose else ["dose_amount"]
        missing.append("prn_bounds")
        return StructurePatternClassification(
            pattern_name="prn_unbounded",
            structurally_complete=False,
            missing_elements=missing,
            requires_frequency=False,
            requires_duration=False,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    if has_scheduled_frequency and has_duration:
        missing = [] if has_dose else ["dose_amount"]
        return StructurePatternClassification(
            pattern_name="fixed_duration_scheduled",
            structurally_complete=not missing,
            missing_elements=missing,
            requires_frequency=True,
            requires_duration=True,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    if has_scheduled_frequency and not has_duration:
        missing = [] if has_dose else ["dose_amount"]
        return StructurePatternClassification(
            pattern_name="ongoing_scheduled",
            structurally_complete=not missing,
            missing_elements=missing,
            requires_frequency=True,
            requires_duration=False,
            frequency_satisfied=True,
            duration_satisfied=True,
        )

    missing = []
    if not has_dose:
        missing.append("dose_amount")
    if not has_scheduled_frequency:
        missing.append("frequency")
    return StructurePatternClassification(
        pattern_name="unclassified",
        structurally_complete=False,
        missing_elements=missing,
        requires_frequency=True,
        requires_duration=False,
        frequency_satisfied=False,
        duration_satisfied=has_duration,
    )