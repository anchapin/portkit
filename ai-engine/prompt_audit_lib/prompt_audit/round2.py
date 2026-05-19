"""
Round 2+ Auditor - Cross-Lane Consistency Checks

Issue: #1606 (T4) - Round 2+ audit - cross-lane consistency (iterative until convergence)

Performs cross-lane consistency checks between pipeline lanes:
- Semantic consistency across agent nodes
- Output format consistency
- State management consistency
- Variable passing consistency
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .collector import PromptCollector, PromptSpec
from .round1 import Round1Auditor, FileIssue


@dataclass
class CrossLaneIssue:
    """Issue found across lanes."""
    source_file: str
    target_file: str
    issue_type: str
    message: str
    affected_lanes: List[str] = field(default_factory=list)
    severity: str = "medium"


class ConvergenceChecker:
    """
    Checks for convergence across audit rounds.
    
    Convergence is achieved when:
    - No new issues found in consecutive rounds
    - All high/critical issues are resolved
    - Cross-lane references are consistent
    """
    
    def __init__(self, max_rounds: int = 10):
        self.max_rounds = max_rounds
        self.round_results: List[Dict[str, Any]] = []
        self._issue_signature: Set[str] = set()
    
    def add_round_result(self, result: Dict[str, Any]) -> bool:
        """
        Add a round result and check for convergence.
        
        Returns True if converged (stable state reached).
        """
        self.round_results.append(result)
        
        # Generate issue signature for this round
        new_signatures = set()
        for issue in result.get("cross_lane_issues", []):
            sig = f"{issue['issue_type']}:{issue['source_file']}:{issue.get('target_file', '')}"
            new_signatures.add(sig)
        
        # Check convergence criteria
        if len(self.round_results) >= 2:
            # Check if new issues are subset of previous
            previous_signatures = set()
            for prev_result in self.round_results[:-1]:
                for issue in prev_result.get("cross_lane_issues", []):
                    sig = f"{issue['issue_type']}:{issue['source_file']}:{issue.get('target_file', '')}"
                    previous_signatures.add(sig)
            
            # Convergence: no new issues outside previous rounds
            novel_issues = new_signatures - previous_signatures
            self._issue_signature = previous_signatures | new_signatures
            
            # Also check that we're not introducing new issues each round
            if len(self.round_results) >= 3:
                recent_new_issues = []
                for i in range(1, len(self.round_results)):
                    prev_sigs = set()
                    for issue in self.round_results[i-1].get("cross_lane_issues", []):
                        sig = f"{issue['issue_type']}:{issue['source_file']}:{issue.get('target_file', '')}"
                        prev_sigs.add(sig)
                    
                    curr_sigs = set()
                    for issue in self.round_results[i].get("cross_lane_issues", []):
                        sig = f"{issue['issue_type']}:{issue['source_file']}:{issue.get('target_file', '')}"
                        curr_sigs.add(sig)
                    
                    novel = curr_sigs - prev_sigs
                    recent_new_issues.append(len(novel))
                
                # If new issues are decreasing, we're converging
                if all(recent_new_issues[i] <= recent_new_issues[i-1] for i in range(1, len(recent_new_issues))):
                    return True
        
        # Check if we've reached max rounds
        if len(self.round_results) >= self.max_rounds:
            return True
        
        # Check if no critical issues remain
        critical_issues = [i for i in result.get("cross_lane_issues", []) if i.get("severity") == "critical"]
        if len(critical_issues) == 0 and len(new_signatures - self._issue_signature) == 0:
            return True
        
        return False
    
    def get_convergence_status(self) -> Dict[str, Any]:
        """Get current convergence status."""
        if not self.round_results:
            return {"converged": False, "rounds": 0, "reason": "No rounds completed"}
        
        rounds = len(self.round_results)
        latest = self.round_results[-1]
        
        return {
            "converged": self.add_round_result.__wrapped__(self, latest) if rounds > 0 else False,
            "rounds_completed": rounds,
            "total_issues": sum(len(r.get("cross_lane_issues", [])) for r in self.round_results),
            " critical_issues": sum(
                1 for r in self.round_results
                for i in r.get("cross_lane_issues", [])
                if i.get("severity") == "critical"
            ),
        }


class Round2Auditor:
    """
    Round 2+ audit - cross-lane consistency checks.
    
    Performs inter-lane consistency checks across the LangGraph pipeline:
    - Java Analyzer → Strategy Planner → Converters → QA Validator
    - Ensures variable names and formats are consistent across boundaries
    """
    
    LANE_ORDER = [
        "java_analyzer",
        "strategy_planner", 
        "block_converter",
        "entity_converter",
        "recipe_converter",
        "asset_converter",
        "qa_validator",
        "logic_translator_retry",
    ]
    
    def __init__(self, collector: Optional[PromptCollector] = None):
        self.collector = collector or PromptCollector()
        self.round1 = Round1Auditor(collector)
        self.issues: List[CrossLaneIssue] = []
        self.convergence_checker = ConvergenceChecker()
    
    def run_audit(self, round_num: int = 2) -> Dict[str, Any]:
        """
        Run Round N audit (N >= 2) with cross-lane checks.
        
        Args:
            round_num: Current round number
            
        Returns:
            Audit results with cross-lane issues
        """
        prompts = self.collector.collect_all()
        
        # Run Round 1 checks first
        round1_result = self.round1.run_audit()
        
        # Perform cross-lane checks
        self._check_lane_boundaries(prompts)
        self._check_state_consistency(prompts)
        self._check_variable_flow_consistency(prompts)
        self._check_output_format_consistency(prompts)
        
        result = {
            "round": round_num,
            "prompts_audited": len(prompts),
            "cross_lane_issues": [vars(i) for i in self.issues],
            "round1_issues": round1_result.get("issues_found", 0),
            "converged": self.convergence_checker.add_round_result({
                "cross_lane_issues": [vars(i) for i in self.issues]
            }),
        }
        
        return result
    
    def _check_lane_boundaries(self, prompts: List[PromptSpec]) -> None:
        """Check consistency at lane boundaries."""
        
        # Group prompts by agent/lane
        by_agent: Dict[str, List[PromptSpec]] = {}
        for prompt in prompts:
            if prompt.agent_name not in by_agent:
                by_agent[prompt.agent_name] = []
            by_agent[prompt.agent_name].append(prompt)
        
        # Check for missing lane connections
        for i, lane in enumerate(self.LANE_ORDER[:-1]):
            next_lane = self.LANE_ORDER[i + 1]
            
            # Find prompts that reference the next lane
            lane_prompts = by_agent.get(lane, [])
            next_lane_prompts = by_agent.get(next_lane, [])
            
            if lane_prompts and not next_lane_prompts:
                # Check if lane mentions next lane
                mentions_next = False
                for prompt in lane_prompts:
                    if next_lane.replace("_", " ") in prompt.content.lower():
                        mentions_next = True
                        break
                
                if not mentions_next:
                    self.issues.append(CrossLaneIssue(
                        source_file=lane,
                        target_file=next_lane,
                        issue_type="missing_lane_reference",
                        message=f"Lane '{lane}' does not reference '{next_lane}' in prompts",
                        affected_lanes=[lane, next_lane],
                        severity="medium",
                    ))
    
    def _check_state_consistency(self, prompts: List[PromptSpec]) -> None:
        """Check for ConversionState field consistency across lanes."""
        
        # Known state fields from langgraph_pipeline.py
        state_fields = {
            "job_id", "mod_path", "output_path", "temp_dir",
            "mod_info", "features", "assets", "conversion_plan",
            "smart_assumptions_applied", "converted_scripts", "converted_assets",
            "bedrock_json", "qa_results", "qa_passed", "pass_rate",
            "confidence_score", "hitl_feedback", "needs_human_review",
            "errors", "warnings", "node_status", "retry_count",
            "max_retries", "confidence_segments", "execution_time",
            "interrupted_segments", "final_report", "status"
        }
        
        # Check that prompts reference state fields consistently
        for prompt in prompts:
            content = prompt.content
            
            # Find field references
            for field in state_fields:
                # Check for variations (snake_case vs camelCase)
                snake_case = field
                camel_case = ''.join(w.capitalize() if i > 0 else w for i, w in enumerate(field.split('_')))
                
                # Check if both are used
                has_snake = snake_case in content
                has_camel = camel_case in content
                
                if has_snake and has_camel:
                    self.issues.append(CrossLaneIssue(
                        source_file=prompt.file_path,
                        target_file="ConversionState",
                        issue_type="inconsistent_naming",
                        message=f"Prompt uses both '{snake_case}' and '{camel_case}' for same field",
                        affected_lanes=[prompt.agent_name],
                        severity="low",
                    ))
    
    def _check_variable_flow_consistency(self, prompts: List[PromptSpec]) -> None:
        """Check for consistency in variable names passed between lanes."""
        
        # Known variables that flow between lanes
        flow_variables = [
            "job_id", "mod_path", "features", "assets", "conversion_plan",
            "converted_scripts", "converted_assets", "qa_results", "pass_rate"
        ]
        
        # Group by lane
        by_lane: Dict[str, List[PromptSpec]] = {}
        for prompt in prompts:
            if prompt.agent_name not in by_lane:
                by_lane[prompt.agent_name] = []
            by_lane[prompt.agent_name].append(prompt)
        
        # Check that variables are defined before use
        for lane in self.LANE_ORDER:
            lane_prompts = by_lane.get(lane, [])
            
            for prompt in lane_prompts:
                for var in prompt.variables:
                    # Check if this is a state field that should be defined
                    if var in flow_variables:
                        # Find where it's defined (should be earlier in pipeline)
                        var_defined = False
                        for prev_lane in self.LANE_ORDER:
                            if prev_lane == lane:
                                break
                            prev_prompts = by_lane.get(prev_lane, [])
                            for prev_prompt in prev_prompts:
                                if var in prev_prompt.variables or var in prev_prompt.content:
                                    var_defined = True
                                    break
                            if var_defined:
                                break
                        
                        if not var_defined:
                            self.issues.append(CrossLaneIssue(
                                source_file=prompt.file_path,
                                target_file="upstream",
                                issue_type="undefined_variable",
                                message=f"Variable '{var}' used in '{lane}' but not defined in upstream lanes",
                                affected_lanes=[lane],
                                severity="medium",
                            ))
    
    def _check_output_format_consistency(self, prompts: List[PromptSpec]) -> None:
        """Check for consistent output formats across lanes."""
        
        # Check that output format instructions are consistent
        output_keywords = ["Respond with", "Return", "Output", "Format", "JSON"]
        
        by_lane: Dict[str, List[PromptSpec]] = {}
        for prompt in prompts:
            if prompt.agent_name not in by_lane:
                by_lane[prompt.agent_name] = []
            by_lane[prompt.agent_name].append(prompt)
        
        # Find JSON output expectations
        json_expectations: Dict[str, List[str]] = {}
        for lane, lane_prompts in by_lane.items():
            for prompt in lane_prompts:
                for keyword in output_keywords:
                    if keyword in prompt.content:
                        if lane not in json_expectations:
                            json_expectations[lane] = []
                        json_expectations[lane].append(keyword)
        
        # Check for consistency in JSON handling
        for lane in self.LANE_ORDER:
            expectations = json_expectations.get(lane, [])
            if "JSON" in expectations or "Respond with" in expectations:
                # Check that downstream lanes handle JSON similarly
                for next_lane in self.LANE_ORDER:
                    if self.LANE_ORDER.index(next_lane) <= self.LANE_ORDER.index(lane):
                        continue
                    next_expectations = json_expectations.get(next_lane, [])
                    if not next_expectations:
                        self.issues.append(CrossLaneIssue(
                            source_file=lane,
                            target_file=next_lane,
                            issue_type="output_format_mismatch",
                            message=f"Lane '{lane}' expects JSON but '{next_lane}' has no JSON output instructions",
                            affected_lanes=[lane, next_lane],
                            severity="low",
                        ))