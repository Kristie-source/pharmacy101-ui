from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ParsedPrescription:
    raw_text: str
    drug: str
    sig: str
    quantity: int
    frequency: Optional[str] = None
    structure_pattern: str = "unclassified"
    structure_complete: bool = False
    structure_missing: List[str] = field(default_factory=list)


@dataclass
class StructuralResult:
    structural_issue: str
    affects: str
    clarification: str
    resolution: str
    drug_recognition_status: str
    drug_recognition_match: Optional[str] = None
    risk_severity: str = "LOW"
    immediate_usability: str = "YES"
    workflow_status: str = "Resolved"
    structure_assessment: str = "Structural concern"
    pattern_assessment: str = "Pattern not evaluated"
    pattern_issue: str = ""
    pattern_context_supported: bool = False
    decision_tags: Optional[dict] = field(default_factory=dict)
    pattern_confidence: str = "NONE"
    therapy_type: str = "UNKNOWN"


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
    risk_severity: str
    immediate_usability: str
    workflow_status: str


@dataclass
class KnowledgeResult:
    summary_points: List[str]
    conclusion: str


@dataclass
class DocumentationResult:
    note: str