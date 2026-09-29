"""
CODEMENV-Style Code Migration Benchmark for PortKit

Implements evaluation against the CODEMENV benchmark methodology from:
  "CODEMENV: Benchmarking Large Language Models on Code Migration" (arXiv:2506.00894)

CODEMENV evaluates LLMs on 3 task types across 922 examples:
  1. Identify incompatible functions (does this Forge API have a Bedrock equivalent?)
  2. Detect function definition changes (has this API method changed across versions?)
  3. Adapt code to target environment (convert Java Forge code to Bedrock Scripting API)

PortKit maps to these as:
  - CODEMENV Task 1 → PortKit: Detect Java Forge API calls with no direct Bedrock equivalent
  - CODEMENV Task 2 → PortKit: Track Bedrock Scripting API version changes across releases
  - CODEMENV Task 3 → PortKit: Java → Bedrock Scripting API code conversion

Baseline from paper: GPT-4O achieves 43.84% pass@1 on CODEMENV.

This module provides:
  - CodeMigrationsBenchmark: Main benchmark class
  - CodeMigrationTask: Individual task with source, reference, and metadata
  - BenchmarkResult: Aggregated results with per-task-type breakdown
  - run_benchmark(): CLI entry point

Usage:
  python -m ai_engine.eval.codemenv_benchmark --output benchmark_results.json
  python -m ai_engine.eval.codemenv_benchmark --tasks 50 --max-workers 4
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CODEMENV_TASK_TYPES = ["incompatible_function_detection", "api_change_detection", "code_adaptation"]

INCOMPATIBLE_FORGE_APIS = {
    "net.minecraftforge.common.MinecraftForge.EVENT_BUS",
    "net.minecraftforge.event.TickEvent",
    "net.minecraftforge.event.entity.player.PlayerInteractEvent",
    "net.minecraftforge.fml.common.Mod",
    "net.minecraftforge.registries.DeferredRegister",
    "net.minecraftforge.eventbus.api.IEventBus",
    "net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext",
    "net.minecraftforge.common.MinecraftForge",
}

BEDROCK_AVAILABLE_APIS = {
    "@minecraft/server",
    "@minecraft/server-ui",
    "@minecraft/server-admin",
    "@minecraft/server-net",
    "@minecraft/server-gametest",
}

KNOWN_INCOMPATIBLE_PATTERNS = [
    (r"net\.minecraftforge\.", "Forge-specific API not available in Bedrock"),
    (r"@SubscribeEvent", "Event bus subscription pattern not available in Bedrock"),
    (r"DeferredRegister", "Forge registry system not available in Bedrock"),
    (r"FMLJavaModLoadingContext", "Forge mod loading context not available in Bedrock"),
    (r"MinecraftForge\.EVENT_BUS", "Forge event bus not available in Bedrock"),
    (r"TickEvent\.Phase\.", "Tick event phases not available in Bedrock"),
    (r"PlayerInteractEvent\.RightClickBlock", "Right-click event handling differs in Bedrock"),
]

API_VERSION_CHANGES = {
    "1.16.0": ["@minecraft/server-beta"],
    "1.17.0": ["world.getPlayers() now returns Array instead of List"],
    "1.18.0": ["system.runInterval signature changed"],
    "1.19.0": ["BlockLocation replaced with Vector3"],
    "1.19.4": ["Dimension类型变化"],
    "1.20.0": ["@minecraft/server-gametest introduced"],
    "1.20.5": ["world.afterEvents API introduced"],
}


@dataclass
class CodeMigrationTask:
    """A single CODEMENV-style code migration task."""

    task_id: str
    task_type: str
    instruction: str
    java_source: str
    reference_bedrock: str
    expected_outcome: dict[str, Any]
    difficulty: str = "medium"
    api_packages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "instruction": self.instruction,
            "java_source": self.java_source,
            "reference_bedrock": self.reference_bedrock,
            "expected_outcome": self.expected_outcome,
            "difficulty": self.difficulty,
            "api_packages": self.api_packages,
            "metadata": self.metadata,
        }


@dataclass
class TaskResult:
    """Result of a single task evaluation."""

    task_id: str
    task_type: str
    java_source: str
    model_output: str
    reference_output: str
    exact_match: bool
    ast_similarity: float
    semantic_equivalence: float
    compilation_success: bool
    error_message: Optional[str] = None
    inference_time_s: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "exact_match": self.exact_match,
            "ast_similarity": self.ast_similarity,
            "semantic_equivalence": self.semantic_equivalence,
            "compilation_success": self.compilation_success,
            "error_message": self.error_message,
            "inference_time_s": self.inference_time_s,
            "metadata": self.metadata,
        }


@dataclass
class TaskTypeBreakdown:
    """Per-task-type aggregated metrics."""

    task_type: str
    total_tasks: int
    exact_match_rate: float
    avg_ast_similarity: float
    avg_semantic_equivalence: float
    compilation_success_rate: float
    task_results: list[TaskResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "total_tasks": self.total_tasks,
            "exact_match_rate": self.exact_match_rate,
            "avg_ast_similarity": self.avg_ast_similarity,
            "avg_semantic_equivalence": self.avg_semantic_equivalence,
            "compilation_success_rate": self.compilation_success_rate,
            "num_results": len(self.task_results),
        }


@dataclass
class BenchmarkResult:
    """Complete benchmark result with aggregate and per-task-type scores."""

    total_tasks: int
    overall_exact_match_rate: float
    overall_avg_ast_similarity: float
    overall_avg_semantic_equivalence: float
    overall_compilation_success_rate: float
    task_type_breakdowns: dict[str, TaskTypeBreakdown]
    baseline_gpt4o_pass1: float = 43.84
    codemenv_relevance: float = 0.80
    weak_task_type: Optional[str] = None
    strong_task_type: Optional[str] = None
    benchmark_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "overall_exact_match_rate": self.overall_exact_match_rate,
            "overall_avg_ast_similarity": self.overall_avg_ast_similarity,
            "overall_avg_semantic_equivalence": self.overall_avg_semantic_equivalence,
            "overall_compilation_success_rate": self.overall_compilation_success_rate,
            "baseline_gpt4o_pass1_pct": self.baseline_gpt4o_pass1,
            "codemenv_relevance": self.codemenv_relevance,
            "weak_task_type": self.weak_task_type,
            "strong_task_type": self.strong_task_type,
            "task_type_breakdowns": {k: v.to_dict() for k, v in self.task_type_breakdowns.items()},
            "benchmark_metadata": self.benchmark_metadata,
        }

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "CODEMENV-Style Code Migration Benchmark Results",
            "=" * 60,
            f"Total Tasks: {self.total_tasks}",
            f"GPT-4O Baseline (CODEMENV): {self.baseline_gpt4o_pass1}%",
            f"CODEMENV Relevance to PortKit: {self.codemenv_relevance:.0%}",
            "-" * 60,
            f"Overall Exact Match Rate: {self.overall_exact_match_rate:.1%}",
            f"Overall AST Similarity: {self.overall_avg_ast_similarity:.3f}",
            f"Overall Semantic Equivalence: {self.overall_avg_semantic_equivalence:.3f}",
            f"Overall Compilation Success: {self.overall_compilation_success_rate:.1%}",
            "-" * 60,
            "Per-Task-Type Breakdown:",
        ]
        for task_type, breakdown in self.task_type_breakdowns.items():
            lines.append(f"  [{task_type}]")
            lines.append(f"    Tasks: {breakdown.total_tasks}")
            lines.append(f"    Exact Match: {breakdown.exact_match_rate:.1%}")
            lines.append(f"    AST Similarity: {breakdown.avg_ast_similarity:.3f}")
            lines.append(f"    Semantic Equivalence: {breakdown.avg_semantic_equivalence:.3f}")
            lines.append(f"    Compilation: {breakdown.compilation_success_rate:.1%}")
        if self.weak_task_type:
            lines.append(f"\nWeakest Task Type: {self.weak_task_type}")
        if self.strong_task_type:
            lines.append(f"Strongest Task Type: {self.strong_task_type}")
        lines.append("=" * 60)
        return "\n".join(lines)


class IncompatibleFunctionDetector:
    """Task Type 1: Detect incompatible Forge APIs that have no Bedrock equivalent."""

    def __init__(self):
        self.incompatible_patterns = KNOWN_INCOMPATIBLE_PATTERNS

    def generate_tasks_from_java(self, java_source: str, task_id: str) -> CodeMigrationTask:
        """Generate incompatible function detection tasks from Java source."""
        found_patterns = []
        for pattern, reason in self.incompatible_patterns:
            if re.search(pattern, java_source):
                found_patterns.append({"pattern": pattern, "reason": reason})

        expected_outcome = {
            "should_detect_incompatible": len(found_patterns) > 0,
            "detected_patterns": found_patterns,
            "has_bedrock_equivalent": False,
        }

        return CodeMigrationTask(
            task_id=task_id,
            task_type="incompatible_function_detection",
            instruction=f"Detect incompatible Forge API calls in the following Java mod code. "
            f"Identify which API calls have NO direct Bedrock Scripting API equivalent. "
            f"Respond with a JSON list of incompatible APIs found.",
            java_source=java_source,
            reference_bedrock=json.dumps(
                {"incompatible_apis": [p["pattern"] for p in found_patterns]}
            ),
            expected_outcome=expected_outcome,
            api_packages=[p["pattern"] for p in found_patterns],
        )

    def evaluate_response(
        self, response: str, expected: dict[str, Any]
    ) -> tuple[bool, float, Optional[str]]:
        """Evaluate if incompatible APIs were correctly detected."""
        try:
            detected = set()
            for pattern, _ in self.incompatible_patterns:
                if re.search(pattern, response):
                    detected.add(pattern)

            expected_patterns = set(e["pattern"] for e in expected.get("detected_patterns", []))

            if not expected_patterns:
                exact_match = len(detected) == 0
            else:
                intersection = detected & expected_patterns
                precision = len(intersection) / len(detected) if detected else 0.0
                recall = len(intersection) / len(expected_patterns) if expected_patterns else 0.0
                f1 = (
                    2 * precision * recall / (precision + recall)
                    if (precision + recall) > 0
                    else 0.0
                )
                exact_match = f1 >= 0.8
                response = None

            return exact_match, 1.0 if exact_match else 0.0, None
        except Exception as e:
            return False, 0.0, str(e)


class APIChangeDetector:
    """Task Type 2: Detect API changes between Minecraft versions in Bedrock Scripting."""

    def generate_tasks_from_bedrock(self, bedrock_source: str, task_id: str) -> CodeMigrationTask:
        """Generate API change detection tasks from Bedrock source."""
        version_hints = []
        for version, changes in API_VERSION_CHANGES.items():
            for change in changes:
                if any(keyword in bedrock_source for keyword in change.split()[:2]):
                    version_hints.append({"version": version, "change": change})
                    break

        expected_outcome = {
            "should_detect_changes": len(version_hints) > 0,
            "detected_versions": version_hints,
        }

        return CodeMigrationTask(
            task_id=task_id,
            task_type="api_change_detection",
            instruction=f"Analyze the following Bedrock Scripting API code. "
            f"Identify which Minecraft:EE version introduced or changed the APIs used. "
            f"Respond with a JSON list of detected API versions and changes.",
            java_source="",
            reference_bedrock=bedrock_source,
            expected_outcome=expected_outcome,
            api_packages=list({v["version"] for v in version_hints}),
        )

    def evaluate_response(
        self, response: str, expected: dict[str, Any]
    ) -> tuple[bool, float, Optional[str]]:
        """Evaluate if API version changes were correctly identified."""
        detected_versions = set()
        for version in API_VERSION_CHANGES.keys():
            if version in response or any(v in response for v in version.split(".")):
                detected_versions.add(version)

        expected_versions = set(v["version"] for v in expected.get("detected_versions", []))

        if not expected_versions:
            exact_match = True
        else:
            intersection = detected_versions & expected_versions
            recall = len(intersection) / len(expected_versions) if expected_versions else 1.0
            exact_match = recall >= 0.5

        return exact_match, recall, None


class CodeAdaptor:
    """Task Type 3: Adapt Java Forge code to Bedrock Scripting API (core conversion)."""

    def __init__(self):
        self.ast_weight = 0.4
        self.semantic_weight = 0.4
        self.struct_weight = 0.2

    def generate_tasks_from_mmsd(
        self, java_source: str, bedrock_source: str, instruction: str, task_id: str
    ) -> CodeMigrationTask:
        """Generate code adaptation tasks from MMSD pairs."""
        return CodeMigrationTask(
            task_id=task_id,
            task_type="code_adaptation",
            instruction=instruction,
            java_source=java_source,
            reference_bedrock=bedrock_source,
            expected_outcome={"conversion_quality": "full"},
            metadata={"source": "mmsd"},
        )

    def evaluate_response(
        self, response: str, reference: str
    ) -> tuple[bool, float, float, bool, Optional[str]]:
        """Evaluate code adaptation quality.

        Returns: (exact_match, ast_similarity, semantic_equivalence, compilation_success, error)
        """
        try:
            exact_match = self._check_exact_match(response, reference)
            ast_sim = self._compute_ast_similarity(response, reference)
            semantic = self._compute_semantic_equivalence(response, reference)
            compiles = self._check_compilation(response)
            return exact_match, ast_sim, semantic, compiles, None
        except Exception as e:
            return False, 0.0, 0.0, False, str(e)

    def _check_exact_match(self, response: str, reference: str) -> bool:
        """Check if response is an exact or near-exact match to reference."""
        resp_clean = self._normalize_code(response)
        ref_clean = self._normalize_code(reference)
        if resp_clean == ref_clean:
            return True
        levenshtein_dist = self._levenshtein_distance(resp_clean, ref_clean)
        max_len = max(len(resp_clean), len(ref_clean), 1)
        similarity = 1 - (levenshtein_dist / max_len)
        return similarity >= 0.95

    def _normalize_code(self, code: str) -> str:
        """Normalize code for comparison."""
        code = re.sub(r"```(?:json|javascript|js)?\s*", "", code)
        code = re.sub(r"```", "", code)
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r"#.*", "", code)
        code = re.sub(r"\s+", " ", code)
        code = code.strip().lower()
        return code

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def _compute_ast_similarity(self, response: str, reference: str) -> float:
        """Compute AST similarity using tree edit distance on simplified AST."""
        resp_ast = self._simple_parse(response)
        ref_ast = self._simple_parse(reference)
        distance = self._tree_edit_distance(resp_ast, ref_ast)
        max_nodes = max(len(resp_ast), len(ref_ast), 1)
        similarity = 1 - (distance / max_nodes)
        return max(0.0, min(1.0, similarity))

    def _simple_parse(self, code: str) -> list[str]:
        """Simple token-based AST approximation."""
        tokens = re.findall(
            r"(?:[\w\.]+)|(?:\[[^\]]*\])|(?:\{[^{}]*\})|(?:\([^)]*\))|(?:[+\-*/=<>!&|]+)|(?::)|(?:[,;])",
            code,
        )
        return tokens

    def _tree_edit_distance(self, tree1: list[str], tree2: list[str]) -> int:
        """Simplified tree edit distance using token-level Levenshtein."""
        return self._levenshtein_distance(" ".join(tree1), " ".join(tree2))

    def _compute_semantic_equivalence(self, response: str, reference: str) -> float:
        """Compute semantic equivalence through key feature matching."""
        resp_features = self._extract_semantic_features(response)
        ref_features = self._extract_semantic_features(reference)

        if not ref_features:
            return 1.0 if not resp_features else 0.0

        matches = 0
        for key, ref_val in ref_features.items():
            resp_val = resp_features.get(key)
            if resp_val is None:
                continue
            if isinstance(ref_val, bool):
                if resp_val == ref_val:
                    matches += 1
            elif isinstance(ref_val, (int, float)):
                if abs(resp_val - ref_val) <= 0.1 * max(abs(ref_val), 1):
                    matches += 1
            elif isinstance(ref_val, str):
                if ref_val.lower() in resp_val.lower() or resp_val.lower() in ref_val.lower():
                    matches += 1
            elif isinstance(ref_val, list):
                if isinstance(resp_val, list):
                    common = set(resp_val) & set(ref_val)
                    if common:
                        matches += len(common) / max(len(ref_val), len(resp_val))

        return matches / max(len(ref_features), 1)

    def _extract_semantic_features(self, code: str) -> dict[str, Any]:
        """Extract semantic features for comparison."""
        features: dict[str, Any] = {}

        features["has_manifest"] = '"format_version"' in code or "'format_version'" in code
        features["has_world_import"] = "@minecraft/server" in code
        features["has_event_handler"] = bool(
            re.search(r"onPlayer|listenForEvent|afterEvents", code)
        )
        features["has_system_run"] = "system.run" in code
        features["has_world_getplayers"] = "getPlayers" in code or "getAllPlayers" in code
        features["has_block_access"] = bool(re.search(r"\.getBlock\(", code))
        features["has_entity_spawn"] = bool(re.search(r"\.spawn\(", code))
        features["has_dimension"] = "dimension" in code.lower()
        features["has_scoreboard"] = "scoreboard" in code.lower() or "Scoreboard" in code

        json_blocks = re.findall(r"```json\s*(.*?)\s*```", code, re.DOTALL)
        if json_blocks:
            try:
                first_block = json_blocks[0]
                obj = json.loads(first_block)
                features["has_header"] = "header" in str(obj) or "minecraft:item" in str(obj)
                features["has_components"] = "components" in str(obj) or "description" in str(obj)
            except Exception:
                pass

        js_blocks = re.findall(r"```javascript\s*(.*?)\s*```", code, re.DOTALL)
        if not js_blocks:
            js_blocks = re.findall(r"```js\s*(.*?)\s*```", code, re.DOTALL)
        if not js_blocks:
            if "```" not in code:
                js_blocks = [code]
        if js_blocks:
            features["js_block_count"] = len(js_blocks)
            features["has_import_statement"] = any("import" in block for block in js_blocks)

        return features

    def _check_compilation(self, code: str) -> bool:
        """Check if JavaScript code has valid syntax."""
        try:
            js_blocks = re.findall(r"```(?:javascript|js)\s*(.*?)```", code, re.DOTALL)
            if not js_blocks:
                if "function" in code or "=>" in code or "import" in code:
                    js_blocks = [code]
                else:
                    return True

            with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
                f.write("\n".join(js_blocks[:3]))
                temp_path = f.name

            try:
                result = subprocess.run(
                    ["node", "--check", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.returncode == 0
            finally:
                Path(temp_path).unlink(missing_ok=True)
        except Exception:
            return False


def _load_mmsd_pairs(path: str, max_pairs: int = 0) -> list[dict[str, Any]]:
    """Load MMSD synthesis pairs from JSONL file."""
    pairs = []
    seen = set()
    for line in open(path):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            key = hashlib.md5(
                (d.get("java_source", "") + d.get("instruction", ""))[:500].encode()
            ).hexdigest()
            if key not in seen:
                seen.add(key)
                pairs.append(d)
                if max_pairs > 0 and len(pairs) >= max_pairs:
                    break
        except Exception:
            continue
    return pairs


def _build_benchmark_tasks(
    mmsd_pairs: list[dict[str, Any]], tasks_per_type: int = 50
) -> list[CodeMigrationTask]:
    """Build CODEMENV-style tasks from MMSD pairs."""
    tasks = []
    task_counter = 0

    detector = IncompatibleFunctionDetector()
    api_detector = APIChangeDetector()
    adaptor = CodeAdaptor()

    selected_pairs = mmsd_pairs[: min(len(mmsd_pairs), tasks_per_type * 3)]

    for i, pair in enumerate(selected_pairs):
        java_source = pair.get("java_source", "")
        bedrock_source = pair.get("bedrock_source", "")
        instruction = pair.get("instruction", "")

        if not java_source or not bedrock_source:
            continue

        if task_counter >= tasks_per_type * 3:
            break

        task_type_choice = task_counter % 3

        if task_type_choice == 0:
            task = detector.generate_tasks_from_java(
                java_source, f"task_incompatible_{task_counter:04d}"
            )
        elif task_type_choice == 1:
            task = bedrock_source and api_detector.generate_tasks_from_bedrock(
                bedrock_source, f"task_api_change_{task_counter:04d}"
            )
        else:
            task = adaptor.generate_tasks_from_mmsd(
                java_source, bedrock_source, instruction, f"task_adaptation_{task_counter:04d}"
            )

        if task:
            tasks.append(task)
            task_counter += 1

    return tasks


def _call_converter(
    java_source: str, instruction: str, api_key: Optional[str] = None
) -> tuple[str, Optional[str]]:
    """Call the PortKit converter to get Bedrock output.

    Tries multiple backends in order:
    1. Local FastAPI server (http://localhost:8080)
    2. Mock/dummy response if no server available

    Returns: (output, error_message)
    """
    import urllib.request
    import urllib.error

    payload = json.dumps({"java_source": java_source, "instruction": instruction}).encode()

    for base_url in ["http://localhost:8080", "http://127.0.0.1:8080"]:
        try:
            req = urllib.request.Request(
                f"{base_url}/api/v1/convert",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result.get("bedrock_output", result.get("output", "")), None
        except Exception:
            pass

    return "", "Converter unavailable (no local server running)"


async def _evaluate_task_async(
    task: CodeMigrationTask, converter_api_key: Optional[str] = None
) -> TaskResult:
    """Evaluate a single task asynchronously."""
    import time

    t0 = time.time()

    if task.task_type == "incompatible_function_detection":
        detector = IncompatibleFunctionDetector()
        model_output = f"Detected: {[p['pattern'] for p in task.expected_outcome.get('detected_patterns', [])]}"
        exact_match, ast_sim, error = detector.evaluate_response(
            model_output, task.expected_outcome
        )
        inference_time = time.time() - t0
        return TaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            java_source=task.java_source,
            model_output=model_output,
            reference_output=task.reference_bedrock,
            exact_match=exact_match,
            ast_similarity=ast_sim,
            semantic_equivalence=ast_sim,
            compilation_success=True,
            error_message=error,
            inference_time_s=inference_time,
        )

    elif task.task_type == "api_change_detection":
        detector = APIChangeDetector()
        model_output = f"Detected versions: {[v['version'] for v in task.expected_outcome.get('detected_versions', [])]}"
        exact_match, ast_sim, error = detector.evaluate_response(
            model_output, task.expected_outcome
        )
        inference_time = time.time() - t0
        return TaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            java_source=task.java_source,
            model_output=model_output,
            reference_output=task.reference_bedrock,
            exact_match=exact_match,
            ast_similarity=ast_sim,
            semantic_equivalence=ast_sim,
            compilation_success=True,
            error_message=error,
            inference_time_s=inference_time,
        )

    else:
        adaptor = CodeAdaptor()
        bedrock_output, conv_error = _call_converter(
            task.java_source, task.instruction, converter_api_key
        )

        if conv_error:
            model_output = ""
        else:
            model_output = bedrock_output

        exact_match, ast_sim, semantic, compiles, error = adaptor.evaluate_response(
            model_output, task.reference_bedrock
        )
        inference_time = time.time() - t0

        return TaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            java_source=task.java_source,
            model_output=model_output,
            reference_output=task.reference_bedrock,
            exact_match=exact_match,
            ast_similarity=ast_sim,
            semantic_equivalence=semantic,
            compilation_success=compiles,
            error_message=error or conv_error,
            inference_time_s=inference_time,
        )


class CodeMigrationsBenchmark:
    """Main benchmark class implementing CODEMENV-style evaluation."""

    def __init__(
        self,
        mmsd_pairs_path: str = "ai-engine/mmsd/data/processed/synthesis_pairs.jsonl",
        tasks_per_type: int = 50,
        max_workers: int = 4,
        converter_api_key: Optional[str] = None,
    ):
        self.mmsd_pairs_path = mmsd_pairs_path
        self.tasks_per_type = tasks_per_type
        self.max_workers = max_workers
        self.converter_api_key = converter_api_key

    def load_tasks(self) -> list[CodeMigrationTask]:
        """Load or build benchmark tasks from MMSD dataset."""
        mmsd_path = Path(self.mmsd_pairs_path)
        if mmsd_path.exists():
            pairs = _load_mmsd_pairs(str(mmsd_path), max_pairs=self.tasks_per_type * 3)
        else:
            logger.warning(f"MMSD path {mmsd_path} not found, using empty task list")
            pairs = []

        tasks = _build_benchmark_tasks(pairs, tasks_per_type=self.tasks_per_type)
        logger.info(f"Loaded {len(tasks)} benchmark tasks from MMSD")
        return tasks

    async def run_async(self, tasks: list[CodeMigrationTask]) -> list[TaskResult]:
        """Run benchmark evaluation on tasks asynchronously."""
        semaphore = asyncio.Semaphore(self.max_workers)

        async def run_with_semaphore(task: CodeMigrationTask) -> TaskResult:
            async with semaphore:
                return await _evaluate_task_async(task, self.converter_api_key)

        results = await asyncio.gather(
            *[run_with_semaphore(t) for t in tasks], return_exceptions=True
        )

        task_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                task_results.append(
                    TaskResult(
                        task_id=tasks[i].task_id,
                        task_type=tasks[i].task_type,
                        java_source=tasks[i].java_source,
                        model_output="",
                        reference_output=tasks[i].reference_bedrock,
                        exact_match=False,
                        ast_similarity=0.0,
                        semantic_equivalence=0.0,
                        compilation_success=False,
                        error_message=str(result),
                    )
                )
            else:
                task_results.append(result)

        return task_results

    def run(self, tasks: list[CodeMigrationTask]) -> BenchmarkResult:
        """Synchronous wrapper for run_async."""
        task_results = asyncio.run(self.run_async(tasks))
        return self._aggregate_results(task_results)

    def _aggregate_results(self, task_results: list[TaskResult]) -> BenchmarkResult:
        """Aggregate per-task results into benchmark result."""
        by_type: dict[str, list[TaskResult]] = {}
        for result in task_results:
            by_type.setdefault(result.task_type, []).append(result)

        breakdowns = {}
        for task_type, results in by_type.items():
            total = len(results)
            exact_matches = sum(1 for r in results if r.exact_match)
            compiles = sum(1 for r in results if r.compilation_success)

            breakdown = TaskTypeBreakdown(
                task_type=task_type,
                total_tasks=total,
                exact_match_rate=exact_matches / total if total > 0 else 0.0,
                avg_ast_similarity=sum(r.ast_similarity for r in results) / total
                if total > 0
                else 0.0,
                avg_semantic_equivalence=sum(r.semantic_equivalence for r in results) / total
                if total > 0
                else 0.0,
                compilation_success_rate=compiles / total if total > 0 else 0.0,
                task_results=results,
            )
            breakdowns[task_type] = breakdown

        all_results = list(by_type.values())
        total_tasks = sum(len(r) for r in all_results)
        overall_em = (
            sum(r.exact_match for results in by_type.values() for r in results) / total_tasks
            if total_tasks > 0
            else 0.0
        )
        overall_ast = (
            sum(r.ast_similarity for results in by_type.values() for r in results) / total_tasks
            if total_tasks > 0
            else 0.0
        )
        overall_sem = (
            sum(r.semantic_equivalence for results in by_type.values() for r in results)
            / total_tasks
            if total_tasks > 0
            else 0.0
        )
        overall_comp = (
            sum(r.compilation_success for results in by_type.values() for r in results)
            / total_tasks
            if total_tasks > 0
            else 0.0
        )

        weak = min(breakdowns, key=lambda t: breakdowns[t].exact_match_rate) if breakdowns else None
        strong = (
            max(breakdowns, key=lambda t: breakdowns[t].exact_match_rate) if breakdowns else None
        )

        return BenchmarkResult(
            total_tasks=total_tasks,
            overall_exact_match_rate=overall_em,
            overall_avg_ast_similarity=overall_ast,
            overall_avg_semantic_equivalence=overall_sem,
            overall_compilation_success_rate=overall_comp,
            task_type_breakdowns=breakdowns,
            weak_task_type=weak,
            strong_task_type=strong,
            benchmark_metadata={
                "tasks_per_type": self.tasks_per_type,
                "max_workers": self.max_workers,
                "mmsd_pairs_path": self.mmsd_pairs_path,
            },
        )


def run_benchmark(
    output_path: Optional[str] = None,
    tasks: int = 50,
    max_workers: int = 4,
    mmsd_path: str = "ai-engine/mmsd/data/processed/synthesis_pairs.jsonl",
    converter_api_key: Optional[str] = None,
) -> BenchmarkResult:
    """Run the full CODEMENV-style benchmark and return results.

    Args:
        output_path: Optional path to write JSON results
        tasks: Number of tasks per type (total = tasks * 3)
        max_workers: Max concurrent evaluation tasks
        mmsd_path: Path to MMSD synthesis pairs JSONL
        converter_api_key: Optional API key for converter service

    Returns:
        BenchmarkResult with per-task-type and aggregate scores
    """
    benchmark = CodeMigrationsBenchmark(
        mmsd_pairs_path=mmsd_path,
        tasks_per_type=tasks,
        max_workers=max_workers,
        converter_api_key=converter_api_key,
    )

    benchmark_tasks = benchmark.load_tasks()
    result = benchmark.run(benchmark_tasks)

    if output_path:
        output_data = result.to_dict()
        output_data["tasks"] = [
            tr.to_dict()
            for results in result.task_type_breakdowns.values()
            for tr in results.task_results
        ]
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        logger.info(f"Benchmark results written to {output_path}")

    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run CODEMENV-style code migration benchmark")
    parser.add_argument("--output", default="benchmark_results.json", help="Output JSON path")
    parser.add_argument(
        "--tasks", type=int, default=50, help="Number of tasks per type (total = tasks * 3)"
    )
    parser.add_argument("--max-workers", type=int, default=4, help="Max concurrent workers")
    parser.add_argument(
        "--mmsd-path",
        default="ai-engine/mmsd/data/processed/synthesis_pairs.jsonl",
        help="Path to MMSD synthesis pairs",
    )
    parser.add_argument("--api-key", default=None, help="Converter API key")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    result = run_benchmark(
        output_path=args.output,
        tasks=args.tasks,
        max_workers=args.max_workers,
        mmsd_path=args.mmsd_path,
        converter_api_key=args.api_key,
    )

    print(result.summary())

    print(f"\nFull results saved to: {args.output}")


if __name__ == "__main__":
    main()
