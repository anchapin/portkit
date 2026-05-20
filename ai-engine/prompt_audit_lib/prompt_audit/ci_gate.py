"""
CI Regression Gate - Prevent Prompt Drift

Issue: #1608 (T6) - Lock prompt specs + add CI regression gate

Provides CI integration for preventing prompt specification drift:
- Prompt hash verification
- Baseline locking
- Regression detection
- CI integration hooks
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .collector import PromptCollector, PromptSpec


@dataclass
class RegressionCheck:
    """Result of a regression check."""
    passed: bool
    new_prompts: List[str] = field(default_factory=list)
    modified_prompts: List[str] = field(default_factory=list)
    removed_prompts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class PromptBaseline:
    """Baseline for prompt specs."""
    version: str
    created_at: datetime
    prompts: Dict[str, str]  # path -> hash
    metadata: Dict[str, Any] = field(default_factory=dict)


class CIGate:
    """
    CI Regression Gate for prompt specs.
    
    Prevents prompt drift by:
    - Hashing all prompt specs
    - Comparing against baseline
    - Failing CI if unauthorized changes detected
    - Allowing authorized updates via approval process
    """
    
    BASELINE_DIR = ".prompt_baseline"
    BASELINE_FILE = "baseline.json"
    APPROVED_CHANGES_FILE = "approved_changes.json"
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.baseline_dir = self.base_path / self.BASELINE_DIR
        self.baseline_file = self.baseline_dir / self.BASELINE_FILE
        self.approved_file = self.baseline_dir / self.APPROVED_CHANGES_FILE
        self.collector = PromptCollector(base_path)
    
    def compute_prompt_hash(self, prompt: PromptSpec) -> str:
        """Compute SHA256 hash of a prompt."""
        content = prompt.content.encode('utf-8')
        return hashlib.sha256(content).hexdigest()[:16]
    
    def compute_all_hashes(self) -> Dict[str, str]:
        """Compute hashes for all prompts."""
        prompts = self.collector.collect_all()
        return {
            f"{p.file_path}:{p.line_number}": self.compute_prompt_hash(p)
            for p in prompts
        }
    
    def create_baseline(self, version: str = "1.0.0") -> PromptBaseline:
        """Create a new baseline from current prompts."""
        self.baseline_dir.mkdir(exist_ok=True)
        
        hashes = self.compute_all_hashes()
        
        baseline = PromptBaseline(
            version=version,
            created_at=datetime.now(),
            prompts=hashes,
        )
        
        # Save baseline
        with open(self.baseline_file, 'w') as f:
            json.dump({
                "version": baseline.version,
                "created_at": baseline.created_at.isoformat(),
                "prompts": baseline.prompts,
                "metadata": baseline.metadata,
            }, f, indent=2)
        
        return baseline
    
    def load_baseline(self) -> Optional[PromptBaseline]:
        """Load existing baseline."""
        if not self.baseline_file.exists():
            return None
        
        with open(self.baseline_file, 'r') as f:
            data = json.load(f)
        
        return PromptBaseline(
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            prompts=data["prompts"],
            metadata=data.get("metadata", {}),
        )
    
    def check_regression(self) -> RegressionCheck:
        """
        Check for prompt regression against baseline.
        
        Returns:
            RegressionCheck with pass/fail and details
        """
        current_hashes = self.compute_all_hashes()
        baseline = self.load_baseline()
        
        if baseline is None:
            # No baseline exists - create one
            baseline = self.create_baseline()
            return RegressionCheck(
                passed=True,
                new_prompts=list(current_hashes.keys()),
                metadata={"note": "Created initial baseline"},
            )
        
        # Compare
        baseline_prompts = set(baseline.prompts.keys())
        current_prompts = set(current_hashes.keys())
        
        new_prompts = current_prompts - baseline_prompts
        removed_prompts = baseline_prompts - current_prompts
        
        modified_prompts = []
        for prompt_key in baseline_prompts & current_prompts:
            if baseline.prompts[prompt_key] != current_hashes[prompt_key]:
                modified_prompts.append(prompt_key)
        
        # Check for changes
        has_changes = bool(new_prompts or removed_prompts or modified_prompts)
        
        # Check if changes are approved
        approved_changes = self._load_approved_changes()
        
        unapproved_new = [p for p in new_prompts if p not in approved_changes]
        unapproved_modified = [p for p in modified_prompts if p not in approved_changes]
        unapproved_removed = [p for p in removed_prompts if p not in approved_changes]
        
        passed = not (unapproved_new or unapproved_modified or unapproved_removed)
        
        return RegressionCheck(
            passed=passed,
            new_prompts=list(new_prompts),
            modified_prompts=list(modified_prompts),
            removed_prompts=list(removed_prompts),
            errors=[
                f"New prompts not approved: {unapproved_new}" if unapproved_new else "",
                f"Modified prompts not approved: {unapproved_modified}" if unapproved_modified else "",
                f"Removed prompts not approved: {unapproved_removed}" if unapproved_removed else "",
            ],
            metadata={
                "baseline_version": baseline.version,
                "total_current_prompts": len(current_hashes),
                "total_baseline_prompts": len(baseline.prompts),
            }
        )
    
    def _load_approved_changes(self) -> Dict[str, Any]:
        """Load approved changes."""
        if not self.approved_file.exists():
            return {}
        
        with open(self.approved_file, 'r') as f:
            return json.load(f)
    
    def approve_change(self, prompt_key: str, approved_by: str = "system") -> None:
        """Approve a specific prompt change."""
        approved = self._load_approved_changes()
        approved[prompt_key] = {
            "approved_by": approved_by,
            "approved_at": datetime.now().isoformat(),
        }
        
        self.baseline_dir.mkdir(exist_ok=True)
        with open(self.approved_file, 'w') as f:
            json.dump(approved, f, indent=2)
    
    def update_baseline(self, version: Optional[str] = None) -> None:
        """Update baseline with current prompts."""
        baseline = self.load_baseline()
        if baseline and version:
            baseline.version = version
        elif baseline is None:
            baseline = PromptBaseline(
                version=version or "1.0.0",
                created_at=datetime.now(),
                prompts={},
            )
        
        baseline.prompts = self.compute_all_hashes()
        baseline.created_at = datetime.now()
        
        self.baseline_dir.mkdir(exist_ok=True)
        with open(self.baseline_file, 'w') as f:
            json.dump({
                "version": baseline.version,
                "created_at": baseline.created_at.isoformat(),
                "prompts": baseline.prompts,
                "metadata": baseline.metadata,
            }, f, indent=2)
    
    def get_ci_report(self) -> Dict[str, Any]:
        """Get CI report for integration."""
        check = self.check_regression()
        
        return {
            "passed": check.passed,
            "timestamp": check.timestamp.isoformat(),
            "summary": {
                "new_prompts": len(check.new_prompts),
                "modified_prompts": len(check.modified_prompts),
                "removed_prompts": len(check.removed_prompts),
            },
            "details": {
                "new_prompts": check.new_prompts,
                "modified_prompts": check.modified_prompts,
                "removed_prompts": check.removed_prompts,
            },
            "errors": [e for e in check.errors if e],
            "metadata": check.metadata,
        }
    
    def generate_ci_script(self) -> str:
        """Generate a CI script for the regression gate."""
        return '''#!/bin/bash
# Prompt Spec Regression Gate CI Script
# Generated by PortKit prompt_audit module

set -e

echo "Running prompt spec regression checks..."

python -c "
from ai_engine.ai_engine.prompt_audit.ci_gate import CIGate
gate = CIGate()
report = gate.get_ci_report()
print(f'Passed: {report[\"passed\"]}')
print(f'New prompts: {report[\"summary\"][\"new_prompts\"]}')
print(f'Modified prompts: {report[\"summary\"][\"modified_prompts\"]}')
print(f'Removed prompts: {report[\"summary\"][\"removed_prompts\"]}')
if not report['passed']:
    print('ERRORS:')
    for error in report['errors']:
        print(f'  - {error}')
    exit(1)
"

echo "Prompt regression checks passed."
'''