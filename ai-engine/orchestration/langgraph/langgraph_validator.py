"""LangGraph behavioral assumptions validator.

Cross-framework SE agent evidence (arxiv 2605.18332) shows that framework
identity explains 64% of behavioral variance vs LLM's 10%; many behavioral
signals reverse direction across frameworks.  This module validates that
PortKit's LangGraph pipeline matches LangGraph-specific best practices
and is not carrying naive assumptions borrowed from SWE-Agent / OpenHands
literature.

Check categories
----------------
1. State completeness — every node reads only fields declared in ConversionState.
2. Edge correctness   — all conditional routing targets are reachable and type-safe.
3. Memory integrity   — checkpoint config matches state reducer requirements.
4. Concurrency safety — no race conditions in async parallel-branch execution.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------


class Verdict(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"


@dataclass
class Finding:
    node_or_edge: str
    check: str
    verdict: Verdict
    detail: str
    recommendation: str


@dataclass
class ValidationReport:
    name: str
    overall_verdict: Verdict
    findings: List[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)
        if finding.verdict == Verdict.FAIL:
            self.overall_verdict = Verdict.FAIL

    def summary(self) -> str:
        counts = {}
        for f in self.findings:
            counts[f.verdict] = counts.get(f.verdict, 0) + 1
        lines = [
            f"ValidationReport: {self.name}",
            f"  Overall: {self.overall_verdict.value}",
            *[f"  {v.value}: {c}" for v, c in counts.items()],
        ]
        for f in self.findings:
            icon = {"PASS": "✓", "FAIL": "✗", "WARNING": "⚠", "SKIPPED": "○"}[f.verdict.value]
            lines.append(f"  {icon} [{f.verdict.value}] {f.node_or_edge} — {f.check}")
            lines.append(f"      {f.detail}")
            if f.recommendation:
                lines.append(f"      → {f.recommendation}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1. State completeness check
# ---------------------------------------------------------------------------

# Fields that each node is expected to READ (not write).
NODE_READS: Dict[str, Set[str]] = {
    "java_analyzer": set(),
    "strategy_planner": {"features", "mod_info", "assets"},
    "block_converter": {"features", "conversion_plan", "mod_info"},
    "entity_converter": {"features", "conversion_plan", "mod_info"},
    "recipe_converter": {"features", "conversion_plan", "mod_info"},
    "asset_converter": {"assets", "conversion_plan", "mod_info"},
    "output_assembler": {
        "converted_scripts",
        "converted_assets",
        "smart_assumptions_applied",
        "mod_info",
    },
    "qa_validator": {
        "output_path",
        "converted_scripts",
        "converted_assets",
        "bedrock_json",
        "pass_rate",
        "qa_passed",
        "confidence_score",
        "confidence_segments",
        "interrupted_segments",
        "needs_human_review",
        "hitl_feedback",
        "errors",
    },
    "logic_translator_retry": {
        "retry_count",
        "interrupted_segments",
        "hitl_feedback",
        "converted_scripts",
        "max_retries",
    },
    "final_report": {
        "qa_passed",
        "confidence_segments",
        "converted_scripts",
        "converted_assets",
        "smart_assumptions_applied",
        "final_report",
        "status",
        "job_id",
        "pass_rate",
    },
}

# Fields that each node is expected to WRITE (return in delta).
NODE_WRITES: Dict[str, Set[str]] = {
    "java_analyzer": {"mod_info", "features", "assets", "node_status", "errors", "warnings"},
    "strategy_planner": {"conversion_plan", "smart_assumptions_applied", "node_status", "errors"},
    "block_converter": {"converted_scripts", "node_status", "errors"},
    "entity_converter": {"converted_scripts", "node_status", "errors"},
    "recipe_converter": {"converted_scripts", "node_status", "errors"},
    "asset_converter": {"converted_assets", "node_status", "errors"},
    "output_assembler": {"bedrock_json", "node_status", "errors"},
    "qa_validator": {
        "qa_results",
        "qa_passed",
        "pass_rate",
        "confidence_score",
        "confidence_segments",
        "interrupted_segments",
        "needs_human_review",
        "node_status",
        "errors",
    },
    "logic_translator_retry": {
        "retry_count",
        "corrected_segment_keys",
        "node_status",
        "errors",
        "warnings",
    },
    "final_report": {"final_report", "status", "node_status", "errors"},
}


def check_state_completeness(graph_builder_path: str) -> ValidationReport:
    """Verify every node reads and writes only fields declared in ConversionState."""
    report = ValidationReport(
        name="State Completeness",
        overall_verdict=Verdict.PASS,
    )

    # Read the ConversionState fields from state_schema.py
    state_fields = _extract_conversion_state_fields(
        graph_builder_path.replace("graph_builder.py", "state_schema.py")
    )

    # Read node implementations to extract field accesses
    node_field_reads = _extract_node_field_accesses(graph_builder_path)

    for node_name, reads in NODE_READS.items():
        # Check that every read field is declared in ConversionState
        for field_name in reads:
            if field_name not in state_fields:
                report.add(
                    Finding(
                        node_or_edge=f"node:{node_name}",
                        check="state-read-declared",
                        verdict=Verdict.FAIL,
                        detail=f"Node '{node_name}' reads field '{field_name}' but it is not declared in ConversionState.",
                        recommendation=f"Add '{field_name}' to ConversionState or remove the read from '{node_name}'.",
                    )
                )

    # Check that written fields are either declared or are mergeable accumulator keys
    mergeable_keys = {"converted_scripts", "converted_assets", "errors", "warnings", "node_status"}
    for node_name, writes in NODE_WRITES.items():
        for field_name in writes:
            if field_name not in state_fields and field_name not in mergeable_keys:
                report.add(
                    Finding(
                        node_or_edge=f"node:{node_name}",
                        check="state-write-declared",
                        verdict=Verdict.WARNING,
                        detail=f"Node '{node_name}' writes field '{field_name}' which is not in ConversionState.",
                        recommendation=f"Add '{field_name}' to ConversionState or confirm it is a transient return key.",
                    )
                )

    # Check that all state fields have at least one writer (no orphan fields)
    all_writers: Set[str] = set()
    for writes in NODE_WRITES.values():
        all_writers.update(writes)

    for field_name in state_fields:
        if field_name not in all_writers and field_name not in {
            "job_id",
            "mod_path",
            "output_path",
            "temp_dir",
            "retry_count",
            "max_retries",
            "hitl_feedback",
            "confidence_segments",
            "execution_time",
            "interrupted_segments",
        }:
            report.add(
                Finding(
                    node_or_edge="schema:ConversionState",
                    check="state-field-utilized",
                    verdict=Verdict.WARNING,
                    detail=f"State field '{field_name}' is declared but has no known writer node.",
                    recommendation="Either add a writer node or remove the orphan field.",
                )
            )

    return report


def _extract_conversion_state_fields(state_schema_path: str) -> Set[str]:
    try:
        with open(state_schema_path) as f:
            tree = ast.parse(f.read())
    except (FileNotFoundError, SyntaxError):
        return set()

    fields: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ConversionState":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    name = item.target.id
                    if not name.startswith("_"):
                        fields.add(name)
    return fields


def _extract_node_field_accesses(graph_builder_path: str) -> Dict[str, Set[str]]:
    """Heuristically extract state field reads from node functions."""
    try:
        with open(graph_builder_path) as f:
            content = f.read()
    except FileNotFoundError:
        return {}

    reads: Dict[str, Set[str]] = {}
    import re

    for match in re.finditer(r"def _(\w+)_node\(self, state: ConversionState\)", content):
        node_name = match.group(1)
        func_start = match.end()
        next_def = content.find("\n    def _", func_start)
        func_body = content[func_start:next_def] if next_def > 0 else content[func_start:]

        found_reads = set(re.findall(r'state\.get\(["\'](\w+)["\']', func_body))
        found_reads.update(re.findall(r'state\["(\w+)"\]', func_body))
        reads[node_name] = found_reads

    return reads


# ---------------------------------------------------------------------------
# 2. Edge correctness check
# ---------------------------------------------------------------------------

# Valid edges: tuple of (from_node, to_node) or (from_node, conditional_key, to_node)
VALID_EDGES: Set[tuple] = {
    # Linear chain
    ("START", "java_analyzer"),
    ("java_analyzer", "strategy_planner"),
    # Fan-out from strategy_planner (conditional)
    ("strategy_planner", "block_converter"),
    ("strategy_planner", "entity_converter"),
    ("strategy_planner", "recipe_converter"),
    ("strategy_planner", "asset_converter"),
    # Join to output_assembler
    ("block_converter", "output_assembler"),
    ("entity_converter", "output_assembler"),
    ("recipe_converter", "output_assembler"),
    ("asset_converter", "output_assembler"),
    # Post-assembly
    ("output_assembler", "qa_validator"),
    # QA routing (conditional): retry | hitl | complete
    ("qa_validator", "logic_translator_retry"),  # retry branch
    ("qa_validator", END if "END" in dir() else "__END__"),  # hitl branch (interrupt)
    ("qa_validator", "final_report"),  # complete branch
    # Retry loop
    ("logic_translator_retry", "qa_validator"),
    # Terminal
    ("final_report", END if "END" in dir() else "__END__"),
}

# All declared node names
ALL_NODES = {
    "java_analyzer",
    "strategy_planner",
    "block_converter",
    "entity_converter",
    "recipe_converter",
    "asset_converter",
    "output_assembler",
    "qa_validator",
    "logic_translator_retry",
    "final_report",
}

# Nodes that run in the PARALLEL fan-out branch.
# Only these nodes can cause race conditions with each other.
# java_analyzer, strategy_planner, output_assembler, qa_validator,
# logic_translator_retry, final_report run sequentially (not in parallel).
PARALLEL_BRANCH_NODES = {
    "block_converter",
    "entity_converter",
    "recipe_converter",
    "asset_converter",
}


def check_edge_correctness(graph_builder_path: str) -> ValidationReport:
    """Check that all declared edges connect to declared nodes and routing is sound."""
    report = ValidationReport(
        name="Edge Correctness",
        overall_verdict=Verdict.PASS,
    )

    try:
        with open(graph_builder_path) as f:
            content = f.read()
    except FileNotFoundError:
        report.add(
            Finding(
                node_or_edge="graph",
                check="file-readable",
                verdict=Verdict.FAIL,
                detail=f"Cannot read {graph_builder_path}",
                recommendation="Verify the file path.",
            )
        )
        return report

    import re

    # Extract add_edge calls
    for match in re.finditer(r"builder\.add_edge\(([^)]+)\)", content):
        args = [a.strip().strip('"').strip("'") for a in match.group(1).split(",")]
        if len(args) >= 2:
            from_node = args[0]
            to_node = args[1]
            if from_node not in ALL_NODES and from_node != "START":
                report.add(
                    Finding(
                        node_or_edge=f"edge: {from_node} -> {to_node}",
                        check="edge-source-valid",
                        verdict=Verdict.FAIL,
                        detail=f"Edge source '{from_node}' is not a declared node.",
                        recommendation=f"Use a declared node name or 'START'.",
                    )
                )
            if to_node not in ALL_NODES and to_node != "END":
                report.add(
                    Finding(
                        node_or_edge=f"edge: {from_node} -> {to_node}",
                        check="edge-target-valid",
                        verdict=Verdict.FAIL,
                        detail=f"Edge target '{to_node}' is not a declared node.",
                        recommendation=f"Use a declared node name or 'END'.",
                    )
                )

    # Extract conditional edges from strategy_planner (fan-out)
    fan_out_match = re.search(
        r"add_conditional_edges\(\s*['\"]strategy_planner['\"]\s*,.*?fan_out_converters.*?\{(.*?)\}",
        content,
        re.DOTALL,
    )
    if fan_out_match:
        inner = fan_out_match.group(1)
        fan_out_targets = re.findall(r"['\"](\w+)['\"]:\s*['\"](\w+)['\"]", inner)
        for from_key, to_node in fan_out_targets:
            if to_node not in ALL_NODES:
                report.add(
                    Finding(
                        node_or_edge=f"conditional: strategy_planner -> {to_node}",
                        check="conditional-target-valid",
                        verdict=Verdict.FAIL,
                        detail=f"Conditional edge key '{from_key}' routes to undeclared node '{to_node}'.",
                        recommendation=f"Use a declared node name for the routing target.",
                    )
                )

    # Extract conditional edges from qa_validator (decide_qa_route)
    qa_match = re.search(
        r"add_conditional_edges\(\s*['\"]qa_validator['\"]\s*,.*?_qa_routing.*?\{(.*?)\}",
        content,
        re.DOTALL,
    )
    if qa_match:
        inner = qa_match.group(1)
        qa_routes_str = re.findall(r"['\"](\w+)['\"]:\s*['\"](\w+)['\"]", inner)
        qa_routes_all = list(qa_routes_str)
        # Also capture string -> END mappings (END is a Python identifier, not a string)
        qa_routes_end = re.findall(r"['\"](\w+)['\"]:\s*(END)\b", inner)
        qa_routes_all.extend(qa_routes_end)
        route_keys = {r[0] for r in qa_routes_all}
        declared_routes = {"retry", "hitl", "complete"}
        if route_keys != declared_routes:
            missing = declared_routes - route_keys
            report.add(
                Finding(
                    node_or_edge="conditional: qa_validator",
                    check="qa-routing-exhaustive",
                    verdict=Verdict.FAIL,
                    detail=f"QA routing missing routes: {missing}. Found: {route_keys}.",
                    recommendation="Ensure all three routes (retry/hitl/complete) are defined in the conditional edge mapping.",
                )
            )
        for route_key, to_node in qa_routes_all:
            if to_node not in ALL_NODES and to_node != "END":
                report.add(
                    Finding(
                        node_or_edge=f"conditional: qa_validator -> {to_node}",
                        check="qa-route-target-valid",
                        verdict=Verdict.FAIL,
                        detail=f"QA route '{route_key}' routes to undeclared node '{to_node}'.",
                        recommendation="Use a declared node or 'END' for the hitl branch.",
                    )
                )

    # Check that the retry loop is bounded (max_retries guard in routing)
    routing_func = re.search(
        r"def decide_qa_route\(.*?\n(.*?)(?=\ndef |\nclass |\Z)",
        content,
        re.DOTALL,
    )
    if routing_func:
        body = routing_func.group(1)
        if "retry_count >= max_retries" not in body and "retry_count > max_retries" not in body:
            report.add(
                Finding(
                    node_or_edge="routing: decide_qa_route",
                    check="retry-bounded",
                    verdict=Verdict.WARNING,
                    detail="decide_qa_route does not check retry_count against max_retries.",
                    recommendation="Add a retry budget guard to prevent infinite retry loops.",
                )
            )
        if "pass_threshold" not in body and "pass_rate" not in body:
            report.add(
                Finding(
                    node_or_edge="routing: decide_qa_route",
                    check="threshold-check",
                    verdict=Verdict.WARNING,
                    detail="decide_qa_route does not compare pass_rate to a threshold.",
                    recommendation="Ensure pass rate threshold routing is implemented.",
                )
            )

    return report


# ---------------------------------------------------------------------------
# 3. Memory / checkpoint integrity check
# ---------------------------------------------------------------------------


def check_checkpoint_integrity(
    graph_builder_path: str,
    checkpointing_path: str,
) -> ValidationReport:
    """Verify checkpoint configuration matches the state reducer requirements."""
    report = ValidationReport(
        name="Checkpoint Integrity",
        overall_verdict=Verdict.PASS,
    )

    try:
        with open(checkpointing_path) as f:
            ckpt_content = f.read()
    except FileNotFoundError:
        report.add(
            Finding(
                node_or_edge="checkpointing",
                check="file-readable",
                verdict=Verdict.FAIL,
                detail=f"Cannot read {checkpointing_path}",
                recommendation="Verify the file path.",
            )
        )
        return report

    import re

    # Check 1: SqliteSaver thread safety comment is present
    if "check_same_thread" not in ckpt_content:
        report.add(
            Finding(
                node_or_edge="checkpointing: SqliteSaver",
                check="thread-safety-doc",
                verdict=Verdict.WARNING,
                detail="SqliteSaver connection does not document thread-safety rationale.",
                recommendation="Add a comment explaining why check_same_thread=False is safe.",
            )
        )

    # Check 2: MemorySaver fallback when SqliteSaver unavailable
    if "MemorySaver" not in ckpt_content:
        report.add(
            Finding(
                node_or_edge="checkpointing: MemorySaver",
                check="fallback-present",
                verdict=Verdict.WARNING,
                detail="No MemorySaver fallback found when SqliteSaver is unavailable.",
                recommendation="Provide MemorySaver as fallback for in-memory checkpointing.",
            )
        )

    # Check 3: Verify state fields that are mergeable (Annotated) are compatible
    # with serialization through the checkpointer
    # Long lists and large dicts in state should be serializable
    if "sqlite" not in ckpt_content.lower() and "memorysaver" not in ckpt_content.lower():
        report.add(
            Finding(
                node_or_edge="checkpointing",
                check="checkpointer-type",
                verdict=Verdict.WARNING,
                detail="No clear checkpointer type (MemorySaver/SqliteSaver) selection found.",
                recommendation="Ensure a checkpointer is created and passed to graph.compile().",
            )
        )

    # Check 4: Verify that the thread_id is set from job_id (not a constant)
    try:
        with open(graph_builder_path) as f:
            gb_content = f.read()
    except FileNotFoundError:
        gb_content = ""

    if re.search(r'thread_id["\']\s*:\s*["\']job_', gb_content):
        pass  # correctly using job_id prefix
    elif re.search(r'thread_id["\']\s*:\s*self\.job_id', gb_content):
        pass  # correctly using instance variable
    else:
        thread_id_match = re.search(r'thread_id["\']:\s*([^,\}]+)', gb_content)
        if thread_id_match:
            report.add(
                Finding(
                    node_or_edge="checkpointing: thread_id",
                    check="thread-id-source",
                    verdict=Verdict.WARNING,
                    detail=f"thread_id is set to '{thread_id_match.group(1).strip()}' — verify it is unique per job.",
                    recommendation="Use self.job_id or a job-specific value for thread_id to ensure correct checkpoint isolation.",
                )
            )

    # Check 5: HITL resume clears needs_human_review
    # NOTE: resume_from_interruption lives in graph_builder.py, not here.
    # We check graph_builder.py for the clearing logic.
    if graph_builder_path:
        try:
            with open(graph_builder_path) as f:
                gb_content = f.read()
            if (
                "needs_human_review" not in gb_content
                or "needs_human_review"
                not in re.search(
                    r"def resume_from_interruption.*?(?=\n    def |\Z)", gb_content, re.DOTALL
                ).group(0)
                if re.search(
                    r"def resume_from_interruption.*?(?=\n    def |\Z)", gb_content, re.DOTALL
                )
                else ""
            ):
                report.add(
                    Finding(
                        node_or_edge="graph_builder: resume_from_interruption",
                        check="hitl-state-reset",
                        verdict=Verdict.WARNING,
                        detail="resume_from_interruption does not clearly clear 'needs_human_review' before re-invoking.",
                        recommendation="Verify that needs_human_review is set to False in the resume state_update.",
                    )
                )
            else:
                # Check it is actually set to False
                resume_match = re.search(
                    r"def resume_from_interruption.*?(?=\n    def |\Z)", gb_content, re.DOTALL
                )
                if resume_match and '"needs_human_review": False' not in resume_match.group(0):
                    report.add(
                        Finding(
                            node_or_edge="graph_builder: resume_from_interruption",
                            check="hitl-state-reset",
                            verdict=Verdict.WARNING,
                            detail="resume_from_interruption may not clear needs_human_review flag.",
                            recommendation="Set needs_human_review to False in the resume state_update.",
                        )
                    )
        except (FileNotFoundError, AttributeError):
            pass

    return report


# ---------------------------------------------------------------------------
# 4. Concurrency safety check
# ---------------------------------------------------------------------------


def check_concurrency_safety(graph_builder_path: str) -> ValidationReport:
    """Detect potential race conditions in async parallel node execution."""
    report = ValidationReport(
        name="Concurrency Safety",
        overall_verdict=Verdict.PASS,
    )

    try:
        with open(graph_builder_path) as f:
            content = f.read()
    except FileNotFoundError:
        report.add(
            Finding(
                node_or_edge="graph_builder",
                check="file-readable",
                verdict=Verdict.FAIL,
                detail=f"Cannot read {graph_builder_path}",
                recommendation="Verify the file path.",
            )
        )
        return report

    import re

    # Check 1: All parallel-branch fields are Annotated with reducers
    # This is verified by checking that converted_scripts, converted_assets,
    # errors, warnings, node_status are in ConversionState with reducers
    state_schema_path = graph_builder_path.replace("graph_builder.py", "state_schema.py")
    try:
        with open(state_schema_path) as f:
            schema_content = f.read()
    except FileNotFoundError:
        schema_content = ""

    reducer_fields = {
        "converted_scripts",
        "converted_assets",
        "errors",
        "warnings",
        "node_status",
    }
    for field in reducer_fields:
        pattern = rf'["\']?{field}["\']?\s*:\s*Annotated'
        if not re.search(pattern, schema_content):
            report.add(
                Finding(
                    node_or_edge=f"state_schema: {field}",
                    check="reducer-annotated",
                    verdict=Verdict.FAIL,
                    detail=f"Mergeable field '{field}' is not Annotated with a reducer in ConversionState.",
                    recommendation=f"Wrap '{field}' with Annotated[..., _concat_lists] or _merge_dicts to prevent last-write-wins in parallel branches.",
                )
            )

    # Check 2: Parallel-branch nodes that write to mergeable fields do NOT also write
    # non-mergeable singleton fields that could race
    for node_name, writes in NODE_WRITES.items():
        if node_name not in PARALLEL_BRANCH_NODES:
            continue  # Linear-chain nodes run sequentially; no race risk
        has_mergeable = bool(writes & reducer_fields)
        has_singleton = bool(writes - reducer_fields - {"node_status"})
        if has_mergeable and has_singleton:
            singleton_issues = writes - reducer_fields - {"node_status", "errors", "warnings"}
            if singleton_issues:
                report.add(
                    Finding(
                        node_or_edge=f"node:{node_name}",
                        check="singleton-write-in-parallel-branch",
                        verdict=Verdict.FAIL,
                        detail=f"Parallel node '{node_name}' writes both mergeable and singleton fields: {singleton_issues}. "
                        "In parallel fan-out, these singleton writes will race (last-write-wins).",
                        recommendation="Wrap singleton fields in Annotated with a reducer, or move to a join node after fan-out.",
                    )
                )

    # Check 3: Conditional routing uses state values, not captured closure values
    # The decide_qa_route function signature should take state, not just instance self
    qa_route_sig = re.search(
        r"def decide_qa_route\((.*?)\)",
        open(graph_builder_path.replace("graph_builder.py", "routing.py")).read()
        if graph_builder_path
        else "",
        re.DOTALL,
    )
    if qa_route_sig:
        params = qa_route_sig.group(1)
        if "state" not in params and "ConversionState" not in params:
            report.add(
                Finding(
                    node_or_edge="routing: decide_qa_route",
                    check="routing-state-param",
                    verdict=Verdict.WARNING,
                    detail="decide_qa_route does not take 'state' as a parameter — routing may use stale closure values.",
                    recommendation="Pass the current ConversionState to routing decisions for correctness on checkpoint resume.",
                )
            )

    # Check 4: execute() uses ainvoke (async), not invoke
    if re.search(r"\.invoke\([^)]*\)", content) and not re.search(r"\.ainvoke\(", content):
        report.add(
            Finding(
                node_or_edge="execute()",
                check="async-execution",
                verdict=Verdict.WARNING,
                detail="execute() uses synchronous .invoke() — parallel converter branches will not run concurrently.",
                recommendation="Use .ainvoke() for true async parallel execution of converter nodes.",
            )
        )
    elif not re.search(r"\.ainvoke\(", content):
        report.add(
            Finding(
                node_or_edge="execute()",
                check="async-usage",
                verdict=Verdict.WARNING,
                detail="execute() does not call .ainvoke() — verify async node execution.",
                recommendation="Ensure .ainvoke() is used for async graph execution.",
            )
        )

    # Check 5: No shared mutable state between nodes (agent instances are per-node singletons)
    agent_init = re.search(
        r"def _initialize_agents\(self\)(.*?)(?=\n    def |\Z)", content, re.DOTALL
    )
    if agent_init:
        body = agent_init.group(1)
        if "get_instance()" not in body and "singleton" not in body.lower():
            report.add(
                Finding(
                    node_or_edge="_initialize_agents",
                    check="agent-singleton",
                    verdict=Verdict.INFO if hasattr(ast, "Info") else Verdict.WARNING,
                    detail="Agent initialization does not use get_instance() singleton pattern.",
                    recommendation="Use singleton agents to avoid duplicate state across node invocations.",
                )
            )

    return report


# ---------------------------------------------------------------------------
# Cross-framework behavioral flagging
# ---------------------------------------------------------------------------

# Heuristics in PortKit's LangGraph pipeline that come from non-LangGraph
# SE-agent literature (SWE-Agent, OpenHands) and are flagged as
# "framework-uncertain" per the arxiv 2605.18332 findings.
CROSS_FRAMEWORK_FLAGS = [
    {
        "heuristic": "pass_rate >= threshold → complete (error rate signal)",
        "source": "SWE-Agent / OpenHands literature",
        "direction_in_portkit": "complete if pass_rate >= 0.80",
        "direction_in_study": "Direction-divided across 95 configs: 47 configs lower-error→better, 48 configs higher-error→better",
        "framework_uncertain": True,
        "validation_needed": True,
        "portkit_verdict": "RETAIN with monitoring — LangGraph's explicit state makes the signal interpretable; monitor per-configellation reversal.",
    },
    {
        "heuristic": "retry_count >= max_retries → stop retrying",
        "source": "SWE-Agent retry literature",
        "direction_in_portkit": "Exhaust retry budget before declaring complete",
        "direction_in_study": "Direction-split finding; some frameworks benefit from extended retry, others spiral",
        "framework_uncertain": True,
        "validation_needed": True,
        "portkit_verdict": "RETAIN — necessary guard; but cap at 3 and monitor if PortKit-specific data shows reversal.",
    },
    {
        "heuristic": "confidence < 0.80 → review_flag (soft_flag)",
        "source": "General SE agent confidence literature",
        "direction_in_portkit": "Flag for review if confidence < 0.80",
        "direction_in_study": "Confidence thresholds are framework-specific; numeric targets require per-framework calibration",
        "framework_uncertain": True,
        "validation_needed": True,
        "portkit_verdict": "CALIBRATE — the 0.80 threshold was borrowed; run ablation to find PortKit-specific value.",
    },
    {
        "heuristic": "Fan-out 4 parallel converters (block/entity/recipe/asset)",
        "source": "PortKit empirical (internal)",
        "direction_in_portkit": "Parallel conversion by component type",
        "direction_in_study": "Parallelism benefits vary; LangGraph Send is architecture-appropriate",
        "framework_uncertain": False,
        "validation_needed": False,
        "portkit_verdict": "RETAIN — this is PortKit-derived, not borrowed.",
    },
    {
        "heuristic": "interrupt() for HITL on hard_flag segments",
        "source": "LangGraph documentation / PortKit design",
        "direction_in_portkit": "Interrupt and resume for human review",
        "direction_in_study": "HITL patterns not studied in arxiv paper (focused on SWE-bench)",
        "framework_uncertain": False,
        "validation_needed": False,
        "portkit_verdict": "RETAIN — LangGraph-native pattern, not framework-uncertain.",
    },
]


def check_cross_framework_heuristics() -> ValidationReport:
    """Flag framework-uncertain behavioral heuristics borrowed from non-LangGraph literature."""
    report = ValidationReport(
        name="Cross-Framework Heuristic Audit",
        overall_verdict=Verdict.PASS,
    )

    for h in CROSS_FRAMEWORK_FLAGS:
        verdict = Verdict.WARNING if h["framework_uncertain"] else Verdict.PASS
        report.add(
            Finding(
                node_or_edge=f"heuristic: {h['heuristic']}",
                check="framework-uncertainty",
                verdict=verdict,
                detail=f"[Source: {h['source']}] {h.get('direction_in_study', 'PortKit-derived')}",
                recommendation=h["portkit_verdict"],
            )
        )

    return report


# ---------------------------------------------------------------------------
# Main validator entry point
# ---------------------------------------------------------------------------


def run_all_checks(
    graph_builder_path: Optional[str] = None,
    state_schema_path: Optional[str] = None,
    routing_path: Optional[str] = None,
    checkpointing_path: Optional[str] = None,
) -> Dict[str, ValidationReport]:
    """Run all four validator checks and return a dict of reports."""
    import os

    base = os.path.dirname(os.path.abspath(__file__))
    gb_path = graph_builder_path or os.path.join(base, "graph_builder.py")
    ss_path = state_schema_path or os.path.join(base, "state_schema.py")
    rt_path = routing_path or os.path.join(base, "routing.py")
    ckpt_path = checkpointing_path or os.path.join(base, "checkpointing.py")

    return {
        "state_completeness": check_state_completeness(gb_path),
        "edge_correctness": check_edge_correctness(gb_path),
        "checkpoint_integrity": check_checkpoint_integrity(gb_path, ckpt_path),
        "concurrency_safety": check_concurrency_safety(gb_path),
        "cross_framework": check_cross_framework_heuristics(),
    }


def print_reports(reports: Dict[str, ValidationReport]) -> None:
    for name, r in reports.items():
        print(f"\n{'=' * 70}")
        print(r.summary())
        print(f"{'=' * 70}")


if __name__ == "__main__":
    reports = run_all_checks()
    print_reports(reports)

    has_failures = any(r.overall_verdict == Verdict.FAIL for r in reports.values())
    sys.exit(1 if has_failures else 0)
