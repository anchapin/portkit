"""
Round 1 Auditor - Single-file Consistency Checks

Issue: #1603 (T3) - Round 1 audit - single-file consistency check

Performs consistency checks within individual prompt files:
- Variable naming consistency
- Formatting consistency
- Type consistency
- Template completeness
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .collector import PromptCollector, PromptSpec
from .checklist import AuditChecklist, AuditFinding, AuditCategory, AuditSeverity


@dataclass
class FileIssue:
    """Issue found in a single file."""

    file_path: str
    issue_type: str
    message: str
    line_number: Optional[int] = None
    severity: str = "medium"


class Round1Auditor:
    """
    Round 1 audit - single-file consistency checks.

    Performs intra-file consistency checks:
    - Variable naming consistency
    - Template formatting
    - Type consistency
    - Internal completeness
    """

    def __init__(self, collector: Optional[PromptCollector] = None):
        self.collector = collector or PromptCollector()
        self.checklist = AuditChecklist()
        self.issues: List[FileIssue] = []

    def run_audit(self) -> Dict[str, Any]:
        """Run Round 1 audit on all collected prompts."""
        prompts = self.collector.collect_all()

        # Group by file
        by_file: Dict[str, List[PromptSpec]] = {}
        for prompt in prompts:
            if prompt.file_path not in by_file:
                by_file[prompt.file_path] = []
            by_file[prompt.file_path].append(prompt)

        # Check each file
        for file_path, file_prompts in by_file.items():
            self._check_file_consistency(file_path, file_prompts)

        # Run standard checklist
        checklist_result = self.checklist.run_all_checks(prompts)

        return {
            "round": 1,
            "prompts_audited": len(prompts),
            "files_audited": len(by_file),
            "issues_found": len(self.issues),
            "checklist_result": checklist_result,
            "file_issues": [vars(i) for i in self.issues],
            "converged": len(self.issues) == 0 and checklist_result.passed,
        }

    def _check_file_consistency(self, file_path: str, prompts: List[PromptSpec]) -> None:
        """Check consistency within a single file."""

        # Check for duplicate variable names
        all_variables: Dict[str, List[int]] = {}
        for prompt in prompts:
            for var in prompt.variables:
                if var not in all_variables:
                    all_variables[var] = []
                all_variables[var].append(prompt.line_number)

        # Report duplicate variables
        for var, line_nums in all_variables.items():
            if len(line_nums) > 1:
                self.issues.append(
                    FileIssue(
                        file_path=file_path,
                        issue_type="duplicate_variable",
                        message=f"Variable '{var}' used in multiple prompts at lines {line_nums}",
                        line_number=line_nums[0],
                        severity="medium",
                    )
                )

        # Check for consistent prompt naming
        prompt_names = [p.name for p in prompts]
        if len(prompt_names) != len(set(prompt_names)):
            duplicates = [n for n in prompt_names if prompt_names.count(n) > 1]
            self.issues.append(
                FileIssue(
                    file_path=file_path,
                    issue_type="duplicate_prompt_name",
                    message=f"Duplicate prompt names: {set(duplicates)}",
                    severity="high",
                )
            )

        # Check for consistent template variable syntax
        template_pattern = re.compile(r"\{(\w+)\}")
        for prompt in prompts:
            if prompt.prompt_type == "template":
                variables_in_content = template_pattern.findall(prompt.content)
                missing_vars = set(prompt.variables) - set(variables_in_content)

                if missing_vars:
                    self.issues.append(
                        FileIssue(
                            file_path=file_path,
                            issue_type="undeclared_variable",
                            message=f"Prompt declares variables {missing_vars} but they don't appear in content",
                            line_number=prompt.line_number,
                            severity="high",
                        )
                    )

        # Check content consistency - ensure same terminology
        self._check_terminology_consistency(file_path, prompts)

        # Check for inconsistent line endings
        self._check_formatting_consistency(file_path, prompts)

    def _check_terminology_consistency(self, file_path: str, prompts: List[PromptSpec]) -> None:
        """Check for terminology consistency across prompts in a file."""

        # Key terms that should be consistent
        consistency_groups = [
            ["Minecraft", "minecraft"],
            ["Bedrock", "bedrock"],
            ["Java", "java"],
            ["Forge", "forge"],
            ["addon", "add-on", "add-on"],
        ]

        for group in consistency_groups:
            appearances: Dict[str, List[int]] = {}

            for prompt in prompts:
                content_lower = prompt.content.lower()
                for term in group:
                    if term.lower() in content_lower:
                        # Find actual casing used
                        idx = prompt.content.lower().find(term.lower())
                        actual_case = prompt.content[idx : idx + len(term)]
                        if actual_case not in appearances:
                            appearances[actual_case] = []
                        appearances[actual_case].append(prompt.line_number)

            if len(appearances) > 1:
                casings = list(appearances.keys())
                self.issues.append(
                    FileIssue(
                        file_path=file_path,
                        issue_type="inconsistent_casing",
                        message=f"Inconsistent casing for '{group[0]}': {casings}",
                        severity="low",
                    )
                )

    def _check_formatting_consistency(self, file_path: str, prompts: List[PromptSpec]) -> None:
        """Check for formatting consistency (indentation, line breaks, etc.)."""

        # Check for trailing whitespace
        for prompt in prompts:
            lines = prompt.content.split("\n")
            for i, line in enumerate(lines):
                if line.rstrip() != line:
                    self.issues.append(
                        FileIssue(
                            file_path=file_path,
                            issue_type="trailing_whitespace",
                            message=f"Line {i + 1} has trailing whitespace",
                            line_number=prompt.line_number + i,
                            severity="low",
                        )
                    )

        # Check for consistent quote usage in content
        # This is a simplified check
        has_double_quotes = any('"' in p.content for p in prompts)
        has_single_quotes = any("'" in p.content for p in prompts)

        # If content has quotes, ensure they're balanced
        for prompt in prompts:
            content = prompt.content
            if content.count('"') % 2 != 0 and content.count("'") % 2 != 0:
                self.issues.append(
                    FileIssue(
                        file_path=file_path,
                        issue_type="unbalanced_quotes",
                        message="Content has unbalanced quotes",
                        line_number=prompt.line_number,
                        severity="medium",
                    )
                )
