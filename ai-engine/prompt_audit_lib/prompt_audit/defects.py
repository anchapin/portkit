"""
Defect Taxonomy - Categorize and Track Prompt Audit Issues

Issue: #1607 (T5) - Defect taxonomy + fix tracking for prompt audit

Provides a structured taxonomy for categorizing prompt defects:
- Type: What kind of issue
- Severity: How critical
- Status: Fix progress
- Fix tracking: Resolution steps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DefectType(Enum):
    """Types of prompt defects."""
    # Completeness
    MISSING_NAME = "missing_name"
    MISSING_DESCRIPTION = "missing_description"
    MISSING_EXAMPLES = "missing_examples"
    MISSING_CONSTRAINTS = "missing_constraints"
    
    # Consistency
    INCONSISTENT_TERMINOLOGY = "inconsistent_terminology"
    INCONSISTENT_CASING = "inconsistent_casing"
    INCONSISTENT_FORMAT = "inconsistent_format"
    CONTRADICTORY_INSTRUCTIONS = "contradictory_instructions"
    
    # Effectiveness
    UNCLEAR_TASK = "unclear_task"
    MISSING_OUTPUT_FORMAT = "missing_output_format"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    MISSING_EDGE_CASE_HANDLING = "missing_edge_case_handling"
    
    # Security
    HARDCODED_SECRET = "hardcoded_secret"
    PII_LEAKAGE = "pii_leakage"
    
    # Style
    PROMPT_TOO_LONG = "prompt_too_long"
    POOR_STRUCTURE = "poor_structure"
    VAGUE_INSTRUCTIONS = "vague_instructions"


class DefectSeverity(Enum):
    """Severity levels for defects."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFO = 5


class DefectStatus(Enum):
    """Status of defect fixes."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    WONT_FIX = "wont_fix"
    VERIFIED = "verified"


@dataclass
class Defect:
    """A single prompt defect."""
    id: str
    type: DefectType
    severity: DefectSeverity
    status: DefectStatus
    
    # Location
    file_path: str
    line_number: int
    prompt_name: str
    
    # Details
    title: str
    description: str
    suggestion: str
    
    # Tracking
    discovered_round: int
    discovered_at: datetime = field(default_factory=datetime.now)
    fixed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    
    # Related
    related_defects: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self) -> int:
        return hash(self.id)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Defect):
            return False
        return self.id == other.id


class DefectTaxonomy:
    """
    Taxonomy for categorizing and tracking prompt defects.
    
    Provides:
    - Defect categorization by type and severity
    - Fix tracking with status
    - Statistics and reporting
    - Fix suggestions
    """
    
    # Severity labels
    SEVERITY_LABELS = {
        DefectSeverity.CRITICAL: "CRITICAL",
        DefectSeverity.HIGH: "HIGH",
        DefectSeverity.MEDIUM: "MEDIUM",
        DefectSeverity.LOW: "LOW",
        DefectSeverity.INFO: "INFO",
    }
    
    # Type categories
    TYPE_CATEGORIES = {
        "completeness": [
            DefectType.MISSING_NAME,
            DefectType.MISSING_DESCRIPTION,
            DefectType.MISSING_EXAMPLES,
            DefectType.MISSING_CONSTRAINTS,
        ],
        "consistency": [
            DefectType.INCONSISTENT_TERMINOLOGY,
            DefectType.INCONSISTENT_CASING,
            DefectType.INCONSISTENT_FORMAT,
            DefectType.CONTRADICTORY_INSTRUCTIONS,
        ],
        "effectiveness": [
            DefectType.UNCLEAR_TASK,
            DefectType.MISSING_OUTPUT_FORMAT,
            DefectType.INSUFFICIENT_CONTEXT,
            DefectType.MISSING_EDGE_CASE_HANDLING,
        ],
        "security": [
            DefectType.HARDCODED_SECRET,
            DefectType.PII_LEAKAGE,
        ],
        "style": [
            DefectType.PROMPT_TOO_LONG,
            DefectType.POOR_STRUCTURE,
            DefectType.VAGUE_INSTRUCTIONS,
        ],
    }
    
    # Fix templates by type
    FIX_TEMPLATES = {
        DefectType.MISSING_NAME: "Add a descriptive name at the start of the prompt file",
        DefectType.MISSING_DESCRIPTION: "Add a description explaining the prompt's purpose",
        DefectType.MISSING_EXAMPLES: "Add few-shot examples showing expected input/output",
        DefectType.MISSING_CONSTRAINTS: "Add clear output constraints (format, length, etc.)",
        DefectType.INCONSISTENT_TERMINOLOGY: "Use consistent terminology throughout",
        DefectType.INCONSISTENT_CASING: "Match the casing used in ConversionState field definitions",
        DefectType.INCONSISTENT_FORMAT: "Follow the standard prompt format: [Role] [Task] [Output Format]",
        DefectType.CONTRADICTORY_INSTRUCTIONS: "Review and resolve conflicting instructions",
        DefectType.UNCLEAR_TASK: "Clarify the exact task and expected behavior",
        DefectType.MISSING_OUTPUT_FORMAT: "Specify the output format (JSON, Markdown, etc.)",
        DefectType.INSUFFICIENT_CONTEXT: "Add more context about the domain and constraints",
        DefectType.MISSING_EDGE_CASE_HANDLING: "Add handling for edge cases and error conditions",
        DefectType.HARDCODED_SECRET: "Remove hardcoded secrets and use environment variables",
        DefectType.PII_LEAKAGE: "Remove or anonymize any personally identifiable information",
        DefectType.PROMPT_TOO_LONG: "Consider splitting into smaller, focused prompts",
        DefectType.POOR_STRUCTURE: "Reorganize with clear sections: Role, Task, Constraints, Format",
        DefectType.VAGUE_INSTRUCTIONS: "Replace vague language with specific, actionable instructions",
    }
    
    def __init__(self):
        self.defects: List[Defect] = []
        self._id_counter: int = 0
    
    def add_defect(
        self,
        defect_type: DefectType,
        severity: DefectSeverity,
        file_path: str,
        line_number: int,
        prompt_name: str,
        title: str,
        description: str,
        discovered_round: int = 1,
        suggestion: Optional[str] = None,
    ) -> Defect:
        """Add a new defect to the taxonomy."""
        self._id_counter += 1
        defect_id = f"DEF-{self._id_counter:04d}"
        
        suggestion = suggestion or self.FIX_TEMPLATES.get(defect_type, "Review and fix")
        
        defect = Defect(
            id=defect_id,
            type=defect_type,
            severity=severity,
            status=DefectStatus.OPEN,
            file_path=file_path,
            line_number=line_number,
            prompt_name=prompt_name,
            title=title,
            description=description,
            suggestion=suggestion,
            discovered_round=discovered_round,
        )
        
        self.defects.append(defect)
        return defect
    
    def update_status(
        self, defect_id: str, new_status: DefectStatus
    ) -> bool:
        """Update the status of a defect."""
        for defect in self.defects:
            if defect.id == defect_id:
                defect.status = new_status
                if new_status == DefectStatus.FIXED:
                    defect.fixed_at = datetime.now()
                elif new_status == DefectStatus.VERIFIED:
                    defect.verified_at = datetime.now()
                return True
        return False
    
    def get_by_severity(self, severity: DefectSeverity) -> List[Defect]:
        """Get all defects of a specific severity."""
        return [d for d in self.defects if d.severity == severity]
    
    def get_by_type(self, defect_type: DefectType) -> List[Defect]:
        """Get all defects of a specific type."""
        return [d for d in self.defects if d.type == defect_type]
    
    def get_by_status(self, status: DefectStatus) -> List[Defect]:
        """Get all defects with a specific status."""
        return [d for d in self.defects if d.status == status]
    
    def get_by_category(self, category: str) -> List[Defect]:
        """Get all defects in a category."""
        types = self.TYPE_CATEGORIES.get(category, [])
        return [d for d in self.defects if d.type in types]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the defects."""
        return {
            "total": len(self.defects),
            "by_severity": {
                self.SEVERITY_LABELS[sev]: len(self.get_by_severity(sev))
                for sev in DefectSeverity
            },
            "by_type": {
                dt.value: len(self.get_by_type(dt))
                for dt in DefectType
            },
            "by_status": {
                st.value: len(self.get_by_status(st))
                for st in DefectStatus
            },
            "open": len(self.get_by_status(DefectStatus.OPEN)),
            "fixed": len(self.get_by_status(DefectStatus.FIXED)),
            "verified": len(self.get_by_status(DefectStatus.VERIFIED)),
        }
    
    def get_fix_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of fixes needed, grouped by file."""
        fix_summary: Dict[str, List[Dict[str, Any]]] = {}
        
        for defect in self.defects:
            if defect.status in [DefectStatus.OPEN, DefectStatus.IN_PROGRESS]:
                if defect.file_path not in fix_summary:
                    fix_summary[defect.file_path] = []
                fix_summary[defect.file_path].append({
                    "id": defect.id,
                    "type": defect.type.value,
                    "severity": self.SEVERITY_LABELS[defect.severity],
                    "line": defect.line_number,
                    "title": defect.title,
                    "suggestion": defect.suggestion,
                })
        
        return [
            {"file": fp, "issues": issues}
            for fp, issues in fix_summary.items()
        ]
    
    def convert_from_audit(
        self, audit_findings: List[Any], round_num: int = 1
    ) -> None:
        """Convert audit findings into defects."""
        finding_to_type = {
            "has_name": DefectType.MISSING_NAME,
            "has_description": DefectType.MISSING_DESCRIPTION,
            "has_examples": DefectType.MISSING_EXAMPLES,
            "has_constraints": DefectType.MISSING_CONSTRAINTS,
            "consistent_terminology": DefectType.INCONSISTENT_TERMINOLOGY,
            "consistent_casing": DefectType.INCONSISTENT_CASING,
            "consistent_format": DefectType.INCONSISTENT_FORMAT,
            "no_contradiction": DefectType.CONTRADICTORY_INSTRUCTIONS,
            "task_clarity": DefectType.UNCLEAR_TASK,
            "output_format_defined": DefectType.MISSING_OUTPUT_FORMAT,
            "context_sufficient": DefectType.INSUFFICIENT_CONTEXT,
            "edge_cases_handled": DefectType.MISSING_EDGE_CASE_HANDLING,
            "no_hardcoded_secrets": DefectType.HARDCODED_SECRET,
            "no_pii_leakage": DefectType.PII_LEAKAGE,
            "proper_length": DefectType.PROMPT_TOO_LONG,
            "clear_structure": DefectType.POOR_STRUCTURE,
            "instruction_clarity": DefectType.VAGUE_INSTRUCTIONS,
        }
        
        severity_map = {
            "critical": DefectSeverity.CRITICAL,
            "high": DefectSeverity.HIGH,
            "medium": DefectSeverity.MEDIUM,
            "low": DefectSeverity.LOW,
            "info": DefectSeverity.INFO,
        }
        
        for finding in audit_findings:
            if hasattr(finding, 'check_name'):
                defect_type = finding_to_type.get(finding.check_name)
                if defect_type:
                    severity = severity_map.get(
                        str(finding.severity).lower(),
                        DefectSeverity.MEDIUM
                    )
                    self.add_defect(
                        defect_type=defect_type,
                        severity=severity,
                        file_path=finding.file_path,
                        line_number=finding.line_number,
                        prompt_name=getattr(finding, 'prompt_name', 'unknown'),
                        title=f"Issue: {finding.check_name}",
                        description=finding.message,
                        discovered_round=round_num,
                        suggestion=getattr(finding, 'suggestion', None),
                    )