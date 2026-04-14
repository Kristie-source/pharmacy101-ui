from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ParsedPrescription:
    raw_text: str
    drug: str
    sig: str
    quantity: int
    frequency: Optional[str] = None


@dataclass
class StructuralResult:
    structural_issue: str
    affects: str
    clarification: str
    resolution: str
    drug_recognition_status: str
    drug_recognition_match: Optional[str] = None


@dataclass
class PatternResult:
    pattern_name: str
    structural_issue: str
    affects: str
    clarification: str


@dataclass
class ClassificationResult:
    pattern_name: str
    resolution: str
    safe_to_verify: str
    follow_up_need: str
    action: str
    severity: str
    risk_score: int
    ui_priority: str
    override_risk: str


@dataclass
class KnowledgeResult:
    summary_points: List[str]
    conclusion: str


@dataclass
class DocumentationResult:
    note: str