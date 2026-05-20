"""
PortKit Prompt Audit Runner

Orchestrates the iterative prompt audit process across:
1. Collection of all prompt specs
2. Round 1 single-file consistency audit
3. Round 2+ cross-lane consistency audit (iterative)
4. Defect taxonomy generation
5. CI regression gate setup

Usage:
    python -m ai_engine.prompt_audit.runner
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from prompt_audit.collector import PromptCollector
from prompt_audit.checklist import AuditChecklist, AuditCategory, AuditSeverity, AuditFinding
from prompt_audit.round1 import Round1Auditor
from prompt_audit.round2 import Round2Auditor, ConvergenceChecker
from prompt_audit.defects import DefectTaxonomy, DefectType, DefectSeverity, DefectStatus
from prompt_audit.ci_gate import CIGate


class PromptAuditRunner:
    """
    Orchestrates the full prompt audit process.
    
    Runs iterative audits until convergence:
    - Round 1: Single-file consistency
    - Round 2+: Cross-lane consistency (until stable)
    """
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.collector = PromptCollector(base_path)
        self.checklist = AuditChecklist()
        self.round1 = Round1Auditor(self.collector)
        self.round2 = Round2Auditor(self.collector)
        self.convergence_checker = ConvergenceChecker()
        self.taxonomy = DefectTaxonomy()
        self.ci_gate = CIGate(base_path)
        
        self.audit_results: List[Dict[str, Any]] = []
    
    def run_full_audit(self, max_rounds: int = 5) -> Dict[str, Any]:
        """
        Run the full audit process with iterative rounds.
        
        Args:
            max_rounds: Maximum number of audit rounds
            
        Returns:
            Complete audit results with findings
        """
        print("=" * 60)
        print("PortKit Prompt Spec Audit")
        print("=" * 60)
        
        # Phase 1: Collection
        print("\n[1/5] Collecting prompt specs...")
        prompts = self.collector.collect_all()
        summary = self.collector.get_prompt_summary()
        print(f"  Found {summary['total']} prompts across {summary['files_with_prompts']} files")
        print(f"  By type: {summary['by_type']}")
        print(f"  By agent: {summary['by_agent']}")
        
        # Phase 2: Round 1 Audit
        print("\n[2/5] Running Round 1 audit (single-file consistency)...")
        round1_result = self.round1.run_audit()
        print(f"  Round 1 issues: {round1_result['issues_found']}")
        self.audit_results.append(round1_result)
        
        # Convert Round 1 findings to defects
        self._convert_round_to_defects(round1_result, round_num=1)
        
        # Phase 3: Round 2+ Audit (iterative)
        print("\n[3/5] Running Round 2+ audit (cross-lane consistency)...")
        round_num = 2
        converged = False
        
        while round_num <= max_rounds and not converged:
            print(f"\n  Round {round_num}...")
            round_result = self.round2.run_audit(round_num=round_num)
            
            issues_count = len(round_result.get('cross_lane_issues', []))
            print(f"    Cross-lane issues: {issues_count}")
            print(f"    Converged: {round_result.get('converged', False)}")
            
            self.audit_results.append(round_result)
            self._convert_round_to_defects(round_result, round_num=round_num)
            
            if round_result.get('converged', False):
                converged = True
                print(f"    ✓ Convergence achieved")
            else:
                round_num += 1
        
        # Phase 4: Defect Summary
        print("\n[4/5] Generating defect taxonomy...")
        stats = self.taxonomy.get_statistics()
        print(f"  Total defects: {stats['total']}")
        print(f"  By severity: {stats['by_severity']}")
        print(f"  By status: {stats['by_status']}")
        
        # Phase 5: CI Gate Setup
        print("\n[5/5] Setting up CI regression gate...")
        self.ci_gate.create_baseline()
        ci_report = self.ci_gate.get_ci_report()
        print(f"  Baseline created: {ci_report['metadata'].get('baseline_version', 'unknown')}")
        
        # Final summary
        print("\n" + "=" * 60)
        print("AUDIT COMPLETE")
        print("=" * 60)
        
        return {
            "prompts_summary": summary,
            "rounds_completed": len(self.audit_results),
            "defect_statistics": stats,
            "defect_fix_summary": self.taxonomy.get_fix_summary(),
            "ci_report": ci_report,
            "all_defects": [self._defect_to_dict(d) for d in self.taxonomy.defects],
        }
    
    def _convert_round_to_defects(self, round_result: Dict[str, Any], round_num: int) -> None:
        """Convert round findings to defect taxonomy."""
        # Convert file issues from round 1
        for issue in round_result.get('file_issues', []):
            self._add_defect_from_issue(issue, round_num)
        
        # Convert cross-lane issues from round 2+
        for issue in round_result.get('cross_lane_issues', []):
            self._add_cross_lane_defect(issue, round_num)
        
        # Convert checklist findings
        checklist_result = round_result.get('checklist_result')
        if checklist_result and hasattr(checklist_result, 'findings'):
            for finding in checklist_result.findings:
                self._add_checklist_defect(finding, round_num)
    
    def _add_defect_from_issue(self, issue: Dict[str, Any], round_num: int) -> None:
        """Add defect from file issue."""
        type_mapping = {
            "duplicate_variable": DefectType.INCONSISTENT_TERMINOLOGY,
            "duplicate_prompt_name": DefectType.MISSING_NAME,
            "undeclared_variable": DefectType.MISSING_CONSTRAINTS,
            "inconsistent_casing": DefectType.INCONSISTENT_CASING,
            "trailing_whitespace": DefectType.POOR_STRUCTURE,
            "unbalanced_quotes": DefectType.POOR_STRUCTURE,
        }
        
        defect_type = type_mapping.get(issue.get('issue_type', ''), DefectType.UNCLEAR_TASK)
        severity_map = {
            'critical': DefectSeverity.CRITICAL,
            'high': DefectSeverity.HIGH,
            'medium': DefectSeverity.MEDIUM,
            'low': DefectSeverity.LOW,
        }
        severity = severity_map.get(issue.get('severity', 'medium'), DefectSeverity.MEDIUM)
        
        self.taxonomy.add_defect(
            defect_type=defect_type,
            severity=severity,
            file_path=issue.get('file_path', 'unknown'),
            line_number=issue.get('line_number', 0),
            prompt_name='unknown',
            title=f"Round {round_num}: {issue.get('issue_type', 'unknown')}",
            description=issue.get('message', ''),
            discovered_round=round_num,
        )
    
    def _add_cross_lane_defect(self, issue: Dict[str, Any], round_num: int) -> None:
        """Add defect from cross-lane issue."""
        type_mapping = {
            "missing_lane_reference": DefectType.INSUFFICIENT_CONTEXT,
            "inconsistent_naming": DefectType.INCONSISTENT_TERMINOLOGY,
            "undefined_variable": DefectType.MISSING_CONSTRAINTS,
            "output_format_mismatch": DefectType.MISSING_OUTPUT_FORMAT,
        }
        
        defect_type = type_mapping.get(issue.get('issue_type', ''), DefectType.UNCLEAR_TASK)
        severity_map = {
            'critical': DefectSeverity.CRITICAL,
            'high': DefectSeverity.HIGH,
            'medium': DefectSeverity.MEDIUM,
            'low': DefectSeverity.LOW,
        }
        severity = severity_map.get(issue.get('severity', 'medium'), DefectSeverity.MEDIUM)
        
        self.taxonomy.add_defect(
            defect_type=defect_type,
            severity=severity,
            file_path=issue.get('source_file', 'unknown'),
            line_number=0,
            prompt_name='unknown',
            title=f"Cross-lane: {issue.get('issue_type', 'unknown')}",
            description=issue.get('message', ''),
            discovered_round=round_num,
            suggestion=f"Affects: {issue.get('affected_lanes', [])}",
        )
    
    def _add_checklist_defect(self, finding: AuditFinding, round_num: int) -> None:
        """Add defect from checklist finding."""
        type_mapping = {
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
        
        defect_type = type_mapping.get(finding.check_name, DefectType.UNCLEAR_TASK)
        severity_map = {
            AuditSeverity.CRITICAL: DefectSeverity.CRITICAL,
            AuditSeverity.HIGH: DefectSeverity.HIGH,
            AuditSeverity.MEDIUM: DefectSeverity.MEDIUM,
            AuditSeverity.LOW: DefectSeverity.LOW,
            AuditSeverity.INFO: DefectSeverity.INFO,
        }
        severity = severity_map.get(finding.severity, DefectSeverity.MEDIUM)
        
        self.taxonomy.add_defect(
            defect_type=defect_type,
            severity=severity,
            file_path=finding.file_path,
            line_number=finding.line_number,
            prompt_name='unknown',
            title=f"Audit: {finding.check_name}",
            description=finding.message,
            discovered_round=round_num,
            suggestion=finding.suggestion,
        )
    
    def _defect_to_dict(self, defect) -> Dict[str, Any]:
        """Convert defect to dictionary."""
        return {
            "id": defect.id,
            "type": defect.type.value,
            "severity": defect.severity.name,
            "status": defect.status.value,
            "file_path": defect.file_path,
            "line_number": defect.line_number,
            "prompt_name": defect.prompt_name,
            "title": defect.title,
            "description": defect.description,
            "suggestion": defect.suggestion,
            "discovered_round": defect.discovered_round,
            "discovered_at": defect.discovered_at.isoformat(),
        }


def main():
    """Run the prompt audit."""
    base_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    runner = PromptAuditRunner(base_path)
    results = runner.run_full_audit()
    
    # Output results
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    
    print(f"\nPrompts audited: {results['prompts_summary']['total']}")
    print(f"Rounds completed: {results['rounds_completed']}")
    print(f"Total defects: {results['defect_statistics']['total']}")
    
    # Output JSON for tooling
    output_path = Path(base_path) / "prompt_audit_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nFull results saved to: {output_path}")
    
    # Return exit code based on critical issues
    critical_count = results['defect_statistics']['by_severity'].get('CRITICAL', 0)
    return 1 if critical_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())