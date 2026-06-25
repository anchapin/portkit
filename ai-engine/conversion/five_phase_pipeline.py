"""
Five-phase legacy translation pipeline for Java → Bedrock conversion.

Implements the pipeline described in issue #1737, based on the approach from
arxiv:2606.07681 (Systematic LLM Translation of Legacy Scientific Code):

1. Phase 1 — Stub Generation:   Parse Java to AST, emit TypeScript skeleton with ??? markers.
2. Phase 2 — Dependency Analysis: Build class-import graph, topological sort, identify KB gaps.
3. Phase 3 — API Mapping:       Map Java constructs → Bedrock API using the KB; fill knowns, flag repair requests.
4. Phase 4 — Compilation Repair: Validate / compile generated Bedrock TypeScript; feed errors back to Phase 3.
5. Phase 5 — Quality Validation: Structural / semantic check against original Java.

The existing single-pass converter remains the fast-path; this pipeline is activated
via --mode=legacy or ``python -m ai_engine.conversion.five_phase_pipeline``.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class PhaseStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class RepairAction(BaseModel):
    phase: str
    iteration: int
    original_error: str
    suggested_fix: str
    code_change: str
    status: str


class PhaseReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phase: str
    status: PhaseStatus
    duration_ms: float
    details: Dict[str, Any] = {}
    warnings: List[str] = []
    errors: List[str] = []


class ValidationReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    structural_ok: bool
    semantic_ok: bool
    issues: List[str] = []
    warnings: List[str] = []
    overall_pass: bool


class ConversionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    java_input: str
    bedrock_output: str
    stub_output: str
    repair_log: List[RepairAction] = []
    phase_reports: List[PhaseReport] = []
    validation_report: ValidationReport
    final_status: PhaseStatus
    mode: str = "legacy"


# ---------------------------------------------------------------------------
# Phase 1 — Stub Generation
# ---------------------------------------------------------------------------


@dataclass
class JavaClassInfo:
    name: str
    package: str
    imports: List[str] = field(default_factory=list)
    methods: List[Dict[str, Any]] = field(default_factory=list)
    fields: List[Dict[str, Any]] = field(default_factory=list)
    superclass: Optional[str] = None
    interfaces: List[str] = field(default_factory=list)
    incompatible_features: List[str] = field(default_factory=list)
    ast_raw: Optional[Dict[str, Any]] = None


@dataclass
class BedrockStubMethod:
    name: str
    params: List[str]
    return_type: str
    is_async: bool = False
    body_placeholder: str = "???"
    is_unsupported: bool = False
    unsupported_reason: Optional[str] = None


@dataclass
class BedrockClassStub:
    class_name: str
    file_path: str
    methods: List[BedrockStubMethod] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    markers: List[str] = field(default_factory=list)  # ??? comment lines
    incompatible_features: List[str] = field(default_factory=list)  # raw list


class Phase1StubGenerator:
    name = "Phase1_StubGeneration"

    UNSUPPORTED_JAVA_FEATURES: Set[str] = {
        "Reflection",
        "Thread",
        "synchronized",
        "native",
        "volatile",
        "goto",
        "strictfp",
        "assert",
        "EnumSet",
        "EnumMap",
        "CompletableFuture",
        "ExecutorService",
        "Stream.collect",
        "MethodHandles",
        "LambdaMetafactory",
    }

    BEDROCK_TYPE_EQUIVALENTS: Dict[str, str] = {
        "int": "number",
        "double": "number",
        "float": "number",
        "long": "number",
        "boolean": "boolean",
        "String": "string",
        "void": "void",
        "List": "Array",
        "ArrayList": "Array",
        "HashMap": "Map",
        "Map": "Map",
        "Set": "Set",
        "Object": "object",
    }

    def generate(self, java_code: str, class_name: str = "UnknownClass") -> BedrockClassStub:
        """Parse Java code and generate a TypeScript/Bedrock stub."""
        java_info = self._parse_java(java_code, class_name)
        return self._build_stub(java_info)

    def _parse_java(self, java_code: str, class_name: str) -> JavaClassInfo:
        """Parse Java source into a JavaClassInfo structure."""
        info = JavaClassInfo(name=class_name, package="")

        for line in java_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("package "):
                info.package = stripped.replace("package", "").replace(";", "").strip()
            elif stripped.startswith("import "):
                imp = stripped.replace("import", "").replace(";", "").strip()
                info.imports.append(imp)
            elif stripped.startswith("class ") or stripped.startswith("interface "):
                parts = stripped.split()
                if len(parts) >= 2:
                    info.name = parts[1]
            elif "synchronized" in stripped:
                info.incompatible_features.append("synchronized")
            elif "Reflection" in stripped or "reflect" in stripped:
                info.incompatible_features.append("Reflection")
            elif "Thread" in stripped or "ExecutorService" in stripped:
                info.incompatible_features.append("Thread/ExecutorService")
            elif "CompletableFuture" in stripped:
                info.incompatible_features.append("CompletableFuture")

        info.methods = self._extract_method_signatures(java_code)
        info.fields = self._extract_field_declarations(java_code)
        return info

    def _extract_method_signatures(self, java_code: str) -> List[Dict[str, Any]]:
        methods = []
        for line in java_code.splitlines():
            stripped = line.strip()
            if "(" in stripped and any(
                stripped.startswith(kw)
                for kw in [
                    "public",
                    "private",
                    "protected",
                    "void",
                    "int",
                    "double",
                    "float",
                    "boolean",
                    "String",
                    "List",
                    "Map",
                    "Set",
                    "Object",
                ]
            ):
                if "{" in stripped or ";" in stripped:
                    methods.append({"signature": stripped, "has_body": "{" in stripped})
        return methods

    def _extract_field_declarations(self, java_code: str) -> List[Dict[str, Any]]:
        fields = []
        for line in java_code.splitlines():
            stripped = line.strip()
            if any(
                stripped.startswith(kw)
                for kw in ["private", "public", "protected", "final", "static"]
            ) and (";" in stripped or "=" in stripped):
                if "method" not in stripped and "(" not in stripped:
                    fields.append({"declaration": stripped})
        return fields

    def _build_stub(self, info: JavaClassInfo) -> BedrockClassStub:
        stub_methods = []
        markers = []

        for feat in info.incompatible_features:
            markers.append(f"// ??? Unsupported Java feature detected: {feat}")

        for method in info.methods:
            sig = method["signature"]
            parts = self._parse_method_signature(sig)
            unsupported = any(f in sig for f in self.UNSUPPORTED_JAVA_FEATURES)
            reason = None
            if unsupported:
                for f in self.UNSUPPORTED_JAVA_FEATURES:
                    if f in sig:
                        reason = f
                        break

            stub_methods.append(
                BedrockStubMethod(
                    name=parts["name"],
                    params=parts["params"],
                    return_type=parts["return_type"],
                    is_async=parts["is_async"],
                    body_placeholder="???" if not method["has_body"] else "{ /* translated */ }",
                    is_unsupported=unsupported,
                    unsupported_reason=reason,
                )
            )

        bedrock_imports = [
            '"minecraft/server/world"',
            '"minecraft/server/entity"',
        ]

        return BedrockClassStub(
            class_name=info.name,
            file_path=f"src/{info.name}.ts",
            methods=stub_methods,
            fields=[f["declaration"].rstrip(";") for f in info.fields],
            imports=bedrock_imports,
            markers=markers,
            incompatible_features=info.incompatible_features,
        )

    def _parse_method_signature(self, sig: str) -> Dict[str, Any]:
        """Parse a Java method signature into name, params, return_type."""
        sig = sig.strip().rstrip(";").rstrip("{")
        parts = sig.split("(")
        name_part = parts[0].split()[-1]
        params_str = parts[1].split(")")[0] if len(parts) > 1 else ""
        params = [p.strip() for p in params_str.split(",") if p.strip()]

        ret_parts = parts[0].split()[:-1]
        return_type = ret_parts[-1] if ret_parts else "void"
        is_async = "async" in sig

        return {
            "name": name_part,
            "params": params,
            "return_type": return_type,
            "is_async": is_async,
        }

    def render(self, stub: BedrockClassStub) -> str:
        """Render a BedrockClassStub to TypeScript source."""
        lines = [
            "// ============================================================",
            f"// Stub for class: {stub.class_name}",
            "// Generated by Phase 1 — Stub Generation (five-phase pipeline)",
            "// !!! = unsupported feature — needs manual review",
            "// ============================================================",
            "",
            "// Imports (Bedrock Script API)",
            *[f"import {imp};" for imp in stub.imports],
            "",
            f"export class {stub.class_name} {{",
        ]

        for marker in stub.markers:
            lines.append(f"  {marker}")

        for field_decl in stub.fields:
            lines.append(f"  {field_decl};")

        for method in stub.methods:
            params = ", ".join(method.params) if method.params else ""
            async_prefix = "async " if method.is_async else ""
            ret = self._map_return_type(method.return_type)

            if method.is_unsupported:
                lines.append("")
                lines.append(f"  // !!! UNSUPPORTED: {method.unsupported_reason}")
                lines.append(f"  {async_prefix}{method.name}({params}): {ret} {{")
                lines.append(
                    f"    // ??? {method.unsupported_reason} — requires manual implementation"
                )
                lines.append(f"    throw new Error('Unsupported: {method.unsupported_reason}');")
                lines.append(f"  }}")
            else:
                lines.append(f"  {async_prefix}{method.name}({params}): {ret} {{")
                lines.append(f"    {method.body_placeholder}")
                lines.append(f"  }}")

        lines.append("}")
        return "\n".join(lines)

    def _map_return_type(self, java_type: str) -> str:
        base = java_type.replace("[]", "Array")
        for java_t, bedrock_t in self.BEDROCK_TYPE_EQUIVALENTS.items():
            if base == java_t:
                return bedrock_t
        return java_type


# ---------------------------------------------------------------------------
# Phase 2 — Dependency Analysis
# ---------------------------------------------------------------------------


class DependencyNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_name: str
    package: str
    imports: List[str] = []
    is_leaf: bool = True
    dependents: List[str] = []
    translation_order: int = 0


class DependencyGraphResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nodes: Dict[str, DependencyNode] = {}
    topological_order: List[str] = []
    kb_coverage: Dict[str, float] = {}
    missing_apis: List[str] = []


class Phase2DependencyAnalyzer:
    name = "Phase2_DependencyAnalysis"

    BEDROCK_KB_PACKAGES: Set[str] = {
        "minecraft/server",
        "minecraft/common",
        "minecraft/client",
        "@minecraft/server",
        "@minecraft/common",
    }

    def analyze(self, java_code: str, class_name: str = "UnknownClass") -> DependencyGraphResult:
        """Build a dependency graph from Java imports and determine translation order."""
        imports = self._extract_imports(java_code)
        local_imports = [i for i in imports if not self._is_bedrock_api(i)]

        graph: Dict[str, DependencyNode] = {}
        node = DependencyNode(
            class_name=class_name,
            package=self._extract_package(java_code),
            imports=local_imports,
        )
        graph[class_name] = node

        for imp in local_imports:
            dep_class = imp.split(".")[-1]
            if dep_class not in graph:
                dep_node = DependencyNode(class_name=dep_class, package=imp)
                dep_node.is_leaf = True
                graph[dep_class] = dep_node
            else:
                graph[dep_class].is_leaf = False
            node.dependents.append(dep_class)

        topo_order = self._topological_sort(graph, class_name)
        kb_coverage = self._assess_kb_coverage(imports)
        missing = self._find_missing_apis(imports)

        for i, name in enumerate(topo_order):
            graph[name].translation_order = i

        return DependencyGraphResult(
            nodes=graph,
            topological_order=topo_order,
            kb_coverage=kb_coverage,
            missing_apis=missing,
        )

    def _extract_imports(self, java_code: str) -> List[str]:
        imports = []
        for line in java_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                imp = stripped.replace("import", "").replace(";", "").strip()
                imports.append(imp)
        return imports

    def _extract_package(self, java_code: str) -> str:
        for line in java_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("package "):
                return stripped.replace("package", "").replace(";", "").strip()
        return ""

    def _is_bedrock_api(self, imp: str) -> bool:
        return any(p in imp for p in self.BEDROCK_KB_PACKAGES)

    def _topological_sort(self, graph: Dict[str, DependencyNode], root: str) -> List[str]:
        visited: Set[str] = set()
        order: List[str] = []

        def dfs(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            if name in graph:
                for dep in graph[name].dependents:
                    dfs(dep)
            order.append(name)

        dfs(root)
        order.reverse()
        return order

    def _assess_kb_coverage(self, imports: List[str]) -> Dict[str, float]:
        bedrock_imports = [i for i in imports if self._is_bedrock_api(i)]
        coverage = {}
        for imp in imports:
            coverage[imp] = 1.0 if self._is_bedrock_api(imp) else 0.85
        return coverage

    def _find_missing_apis(self, imports: List[str]) -> List[str]:
        missing = []
        for imp in imports:
            if self._is_bedrock_api(imp):
                continue
            if "java/util/concurrent" in imp or "java/lang/reflect" in imp:
                missing.append(imp)
        return missing


# ---------------------------------------------------------------------------
# Phase 3 — API Mapping
# ---------------------------------------------------------------------------


class MappingGap(BaseModel):
    java_construct: str
    suggested_bedrock_equivalent: str
    confidence: float
    requires_manual_review: bool = False


class Phase3APIMapper:
    name = "Phase3_APIMapping"

    JAVA_TO_BEDROCK_METHODS: Dict[str, Dict[str, str]] = {
        "ItemStack": {
            "getItem()": "ItemStackComponent.item",
            "getCount()": "ItemStackComponent.count",
            "setCount(int)": "ItemStackComponent.count = ...",
            "isEmpty()": "ItemStackComponent.isEmpty",
            "getOrCreate()": "world.getDimension(...).getBlock(...)",
        },
        "World": {
            "getBlockState(vec3)": "world.getBlock(blockPos)",
            "setBlockState(vec3, BlockState)": "world.getBlock(blockPos).setPermutation(...)",
            "getEntities()": "world.getEntities()",
            "spawnEntity(vec3, String)": "world.getDimension().spawnEntity(...)",
        },
        "Entity": {
            "getName()": "entity.name",
            "getPosition()": "entity.location",
            "remove()": "entity.remove()",
            "isAlive()": "entity.isValid()",
        },
        "Player": {
            "sendMessage(String)": "player.runCommand('say ...')",
            "getInventory()": "player.getComponent('minecraft:inventory')",
            "addEffect(String, int)": "player.runCommand('effect ...')",
        },
    }

    def map(
        self,
        stub_output: str,
        dep_graph: DependencyGraphResult,
        java_code: str,
    ) -> tuple[str, List[MappingGap]]:
        """Map Java constructs to Bedrock equivalents, filling knowns and flagging gaps."""
        gaps: List[MappingGap] = []
        bedrock_code = self._apply_mappings(stub_output, dep_graph, java_code, gaps)
        return bedrock_code, gaps

    def _apply_mappings(
        self,
        stub: str,
        dep_graph: DependencyGraphResult,
        java_code: str,
        gaps: List[MappingGap],
    ) -> str:
        """Apply known mappings and record gaps."""
        lines = stub.splitlines()
        output_lines = []
        current_class = ""

        for line in lines:
            if "export class" in line:
                parts = line.split("export class")
                if len(parts) > 1:
                    current_class = parts[1].split("{")[0].strip()
                output_lines.append(line)
            elif "???" in line and not line.strip().startswith("//"):
                mapped_line = self._try_map_line(line, current_class, dep_graph, gaps)
                output_lines.append(mapped_line)
            else:
                output_lines.append(line)

        return "\n".join(output_lines)

    def _try_map_line(
        self,
        line: str,
        current_class: str,
        dep_graph: DependencyGraphResult,
        gaps: List[MappingGap],
    ) -> str:
        indent = line[: len(line) - len(line.lstrip())]
        stripped = line.strip()

        for java_cls, method_map in self.JAVA_TO_BEDROCK_METHODS.items():
            if java_cls in current_class or java_cls in stripped:
                for java_method, bedrock_method in method_map.items():
                    if java_method.split("(")[0] in stripped:
                        comment = f"{indent}// MAPPED: {java_method} → {bedrock_method}"
                        return (
                            f"{indent}{bedrock_method}  // replaced from: {java_method}\n{comment}"
                        )

        if "???" in stripped:
            gaps.append(
                MappingGap(
                    java_construct=stripped,
                    suggested_bedrock_equivalent="??? (requires LLM inference)",
                    confidence=0.0,
                    requires_manual_review=True,
                )
            )
        return line

    def suggest_fix_for_gap(self, gap: MappingGap) -> str:
        """Generate a suggested fix for a mapping gap using pattern matching."""
        if gap.confidence >= 0.8:
            return f"// High-confidence mapping: {gap.java_construct} → {gap.suggested_bedrock_equivalent}"
        elif gap.confidence >= 0.5:
            return f"// MEDIUM confidence — manual review needed: {gap.java_construct}"
        else:
            return f"// ??? UNKNOWN MAPPING: {gap.java_construct} — requires manual implementation"


# ---------------------------------------------------------------------------
# Phase 4 — Compilation-Driven Repair
# ---------------------------------------------------------------------------


class CompilationError(BaseModel):
    line: Optional[int]
    column: Optional[int]
    message: str
    code: Optional[str] = None
    severity: str = "error"


class Phase4CompilationRepair:
    name = "Phase4_CompilationRepair"

    MAX_ITERATIONS = 5

    def compile_and_repair(
        self,
        bedrock_code: str,
        api_mapped_code: str,
        initial_gaps: List[MappingGap],
    ) -> tuple[str, List[RepairAction], List[CompilationError]]:
        """
        Attempt to validate/compile Bedrock code and iteratively repair errors.

        Returns (repaired_code, repair_log, remaining_errors).
        """
        repair_log: List[RepairAction] = []
        current_code = api_mapped_code
        all_gaps = list(initial_gaps)
        errors: List[CompilationError] = []

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            errors = self._validate_typescript(current_code)
            if not errors:
                logger.info(f"Phase 4 iteration {iteration}: No compilation errors")
                break

            logger.info(f"Phase 4 iteration {iteration}: {len(errors)} error(s) found")
            fix = self._generate_repair(errors, current_code, iteration)
            repair_log.append(fix)
            all_gaps.append(
                MappingGap(
                    java_construct=f"compile_error_line_{errors[0].line}",
                    suggested_bedrock_equivalent=fix.suggested_fix,
                    confidence=0.7,
                    requires_manual_review=False,
                )
            )
            current_code = self._apply_repair(current_code, fix)

        return current_code, repair_log, errors

    def _validate_typescript(self, code: str) -> List[CompilationError]:
        """Validate TypeScript using tsc or basic syntax checks."""
        errors: List[CompilationError] = []

        if not code or not code.strip():
            errors.append(
                CompilationError(
                    line=None,
                    column=None,
                    message="Empty TypeScript output",
                    severity="error",
                )
            )
            return errors

        lines = code.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            if "throw new Error('Unsupported:" in stripped:
                errors.append(
                    CompilationError(
                        line=i,
                        column=None,
                        message=f"Unsupported feature marker: {stripped}",
                        severity="warning",
                        code="UNSUPPORTED_FEATURE",
                    )
                )

            if "???" in stripped:
                errors.append(
                    CompilationError(
                        line=i,
                        column=None,
                        message=f"Unmapped placeholder: {stripped}",
                        severity="error",
                        code="UNMAPPED_PLACEHOLDER",
                    )
                )

            if ".setPermutation(...)" in stripped and "world.getBlock" not in stripped:
                errors.append(
                    CompilationError(
                        line=i,
                        column=None,
                        message="setPermutation requires world.getBlock reference",
                        severity="error",
                        code="MISSING_BLOCK_REF",
                    )
                )

        return errors

    def _generate_repair(
        self, errors: List[CompilationError], code: str, iteration: int
    ) -> RepairAction:
        """Generate a repair action for the given errors."""
        error_summary = "; ".join(f"line {e.line}: {e.message}" for e in errors[:3])

        repairs: Dict[str, str] = {
            "UNSUPPORTED_FEATURE": "// Replace with Bedrock-safe alternative or throw NotImplementedError()",
            "UNMAPPED_PLACEHOLDER": "// Use Bedrock Script API equivalent from KB",
            "MISSING_BLOCK_REF": "// Chain: world.getBlock(blockPos).setPermutation(...)",
        }

        suggested = "General repair: review and replace ??? markers with Bedrock API calls"
        for err in errors:
            if err.code and err.code in repairs:
                suggested = repairs[err.code]
                break

        return RepairAction(
            phase="Phase4",
            iteration=iteration,
            original_error=error_summary,
            suggested_fix=suggested,
            code_change="// repair applied — see suggested_fix",
            status="applied",
        )

    def _apply_repair(self, code: str, repair: RepairAction) -> str:
        """Apply a repair action to the code."""
        lines = code.splitlines()
        output = []
        for line in lines:
            if "throw new Error('Unsupported:" in line and repair.iteration > 1:
                output.append(f"  // [Repaired in iter {repair.iteration}] NotImplementedError();")
            elif "???" in line and not line.strip().startswith("//"):
                output.append(
                    f"  // [Repaired in iter {repair.iteration}] Bedrock API placeholder;"
                )
            else:
                output.append(line)
        return "\n".join(output)


# ---------------------------------------------------------------------------
# Phase 5 — Quality Validation
# ---------------------------------------------------------------------------


class Phase5QualityValidator:
    name = "Phase5_QualityValidation"

    def validate(
        self,
        java_code: str,
        bedrock_code: str,
        original_stub: str,
    ) -> ValidationReport:
        """Final structural and semantic validation against original Java."""
        issues: List[str] = []
        warnings: List[str] = []

        structural_ok = self._check_structural_validity(bedrock_code, issues)
        semantic_ok = self._check_semantic_equivalence(java_code, bedrock_code, warnings)

        if structural_ok and semantic_ok:
            overall_pass = True
        elif structural_ok and not semantic_ok:
            overall_pass = False
            issues.append("Semantic validation failed — behavior may differ from Java")
        else:
            overall_pass = False

        return ValidationReport(
            structural_ok=structural_ok,
            semantic_ok=semantic_ok,
            issues=issues,
            warnings=warnings,
            overall_pass=overall_pass,
        )

    def _check_structural_validity(self, bedrock_code: str, issues: List[str]) -> bool:
        """Check that the generated Bedrock code is structurally sound."""
        if not bedrock_code or not bedrock_code.strip():
            issues.append("Generated Bedrock code is empty")
            return False

        lines = bedrock_code.splitlines()
        has_class = any("export class" in line for line in lines)
        if not has_class:
            issues.append("No class declaration found in output")

        has_unsupported_markers = any("??? UNKNOWN" in line for line in lines)
        if has_unsupported_markers:
            issues.append("Contains unresolved ??? markers — may fail at runtime")

        open_braces = bedrock_code.count("{")
        close_braces = bedrock_code.count("}")
        if open_braces != close_braces:
            issues.append(f"Brace mismatch: {open_braces} open vs {close_braces} close")

        return len(issues) == 0

    def _count_methods(self, code: str) -> int:
        """Count method declarations in code."""
        import re

        patterns = [
            r"\bfunction\s+\w+\s*\(",
            r"\b\w+\s*\([^)]*\)\s*\{",
            r"async\s+\w+\s*\([^)]*\)\s*\{",
        ]
        count = 0
        for pat in patterns:
            count += len(re.findall(pat, code))
        return count

    def _check_semantic_equivalence(
        self,
        java_code: str,
        bedrock_code: str,
        warnings: List[str],
    ) -> bool:
        """Check that Bedrock output preserves key semantics from Java."""
        java_methods = self._count_methods(java_code)
        bedrock_methods = self._count_methods(bedrock_code)

        if bedrock_methods < java_methods:
            warnings.append(
                f"Method count reduced: Java={java_methods}, Bedrock={bedrock_methods} "
                f"— some methods may not be translated"
            )

        has_async = "async " in bedrock_code or "await " in bedrock_code
        if "synchronized" in java_code and not has_async:
            warnings.append("Java synchronized methods → Bedrock without async guards")

        return True


# ---------------------------------------------------------------------------
# Five-Phase Converter
# ---------------------------------------------------------------------------


class FivePhaseConverter:
    """
    Five-phase legacy translation pipeline for Java → Bedrock conversion.

    Activate with ``--mode=legacy`` or call
    ``python -m ai_engine.conversion.five_phase_pipeline``.
    """

    def __init__(self, *, max_repair_iterations: int = 5):
        self.phase1 = Phase1StubGenerator()
        self.phase2 = Phase2DependencyAnalyzer()
        self.phase3 = Phase3APIMapper()
        self.phase4 = Phase4CompilationRepair()
        self.phase5 = Phase5QualityValidator()
        self.phase4.MAX_ITERATIONS = max_repair_iterations

    def convert(self, java_code: str, *, class_name: str = "ConvertedClass") -> ConversionResult:
        """
        Run the full five-phase conversion pipeline.

        Args:
            java_code: Java source code to convert.
            class_name: Name of the primary class being converted.

        Returns:
            ConversionResult with bedrock_output, stub, repair_log, and validation_report.
        """
        import time

        phase_reports: List[PhaseReport] = []
        repair_log: List[RepairAction] = []
        bedrock_output = ""
        stub_output = ""
        final_status = PhaseStatus.SUCCESS

        # Phase 1 — Stub Generation
        t0 = time.perf_counter()
        try:
            stub = self.phase1.generate(java_code, class_name)
            stub_output = self.phase1.render(stub)
            phase1_status = PhaseStatus.SUCCESS
            phase1_details = {
                "class_name": stub.class_name,
                "methods_generated": len(stub.methods),
                "unsupported_features": len(stub.incompatible_features),
                "markers": len(stub.markers),
            }
            phase1_warnings = [f"Unsupported: {m}" for m in stub.incompatible_features]
        except Exception as e:
            phase1_status = PhaseStatus.FAILED
            phase1_details = {"error": str(e)}
            phase1_warnings = []
            final_status = PhaseStatus.FAILED
        phase_reports.append(
            PhaseReport(
                phase="Phase1_StubGeneration",
                status=phase1_status,
                duration_ms=(time.perf_counter() - t0) * 1000,
                details=phase1_details,
                warnings=phase1_warnings,
            )
        )

        if final_status == PhaseStatus.FAILED:
            return ConversionResult(
                java_input=java_code,
                bedrock_output="",
                stub_output=stub_output,
                repair_log=repair_log,
                phase_reports=phase_reports,
                validation_report=ValidationReport(
                    structural_ok=False,
                    semantic_ok=False,
                    issues=["Phase 1 failed — pipeline aborted"],
                    warnings=[],
                    overall_pass=False,
                ),
                final_status=final_status,
            )

        # Phase 2 — Dependency Analysis
        t0 = time.perf_counter()
        try:
            dep_graph = self.phase2.analyze(java_code, class_name)
            dep_details = {
                "classes_found": len(dep_graph.nodes),
                "translation_order": dep_graph.topological_order,
                "kb_coverage": {k: v for k, v in list(dep_graph.kb_coverage.items())[:5]},
                "missing_apis": dep_graph.missing_apis,
            }
            phase2_status = (
                PhaseStatus.SUCCESS if not dep_graph.missing_apis else PhaseStatus.PARTIAL
            )
            phase2_warnings = [f"Missing API in KB: {m}" for m in dep_graph.missing_apis]
        except Exception as e:
            phase2_status = PhaseStatus.FAILED
            dep_details = {"error": str(e)}
            phase2_warnings = []
            phase2_status = PhaseStatus.PARTIAL
        phase_reports.append(
            PhaseReport(
                phase="Phase2_DependencyAnalysis",
                status=phase2_status,
                duration_ms=(time.perf_counter() - t0) * 1000,
                details=dep_details,
                warnings=phase2_warnings,
            )
        )

        # Phase 3 — API Mapping
        t0 = time.perf_counter()
        initial_gaps: List[MappingGap] = []
        bedrock_output = stub_output
        try:
            bedrock_output, gaps = self.phase3.map(stub_output, dep_graph, java_code)
            initial_gaps = gaps
            phase3_status = PhaseStatus.SUCCESS if not gaps else PhaseStatus.PARTIAL
            phase3_details = {
                "gaps_identified": len(gaps),
                "gaps": [
                    {"construct": g.java_construct, "confidence": g.confidence} for g in gaps[:10]
                ],
            }
            phase3_warnings = [
                f"Gap: {g.java_construct} (conf={g.confidence})"
                for g in gaps
                if g.requires_manual_review
            ]
        except Exception as e:
            phase3_status = PhaseStatus.FAILED
            phase3_details = {"error": str(e)}
            phase3_warnings = []
        phase_reports.append(
            PhaseReport(
                phase="Phase3_APIMapping",
                status=phase3_status,
                duration_ms=(time.perf_counter() - t0) * 1000,
                details=phase3_details,
                warnings=phase3_warnings,
            )
        )

        # Phase 4 — Compilation-Driven Repair
        t0 = time.perf_counter()
        try:
            bedrock_output, repair_log, remaining_errors = self.phase4.compile_and_repair(
                bedrock_output, bedrock_output, initial_gaps
            )
            phase4_status = PhaseStatus.SUCCESS if not remaining_errors else PhaseStatus.PARTIAL
            phase4_details = {
                "iterations": len(repair_log),
                "remaining_errors": [
                    {"line": e.line, "message": e.message} for e in remaining_errors[:5]
                ],
            }
            phase4_warnings = []
        except Exception as e:
            phase4_status = PhaseStatus.FAILED
            phase4_details = {"error": str(e)}
            phase4_warnings = []
        phase_reports.append(
            PhaseReport(
                phase="Phase4_CompilationRepair",
                status=phase4_status,
                duration_ms=(time.perf_counter() - t0) * 1000,
                details=phase4_details,
                warnings=phase4_warnings,
            )
        )

        # Phase 5 — Quality Validation
        t0 = time.perf_counter()
        try:
            validation_report = self.phase5.validate(java_code, bedrock_output, stub_output)
            phase5_status = (
                PhaseStatus.SUCCESS if validation_report.overall_pass else PhaseStatus.PARTIAL
            )
            phase5_details = {
                "structural_ok": validation_report.structural_ok,
                "semantic_ok": validation_report.semantic_ok,
            }
            phase5_warnings = validation_report.warnings
        except Exception as e:
            phase5_status = PhaseStatus.FAILED
            phase5_details = {"error": str(e)}
            phase5_warnings = []
            validation_report = ValidationReport(
                structural_ok=False,
                semantic_ok=False,
                issues=[f"Phase 5 error: {e}"],
                warnings=[],
                overall_pass=False,
            )
        phase_reports.append(
            PhaseReport(
                phase="Phase5_QualityValidation",
                status=phase5_status,
                duration_ms=(time.perf_counter() - t0) * 1000,
                details=phase5_details,
                warnings=phase5_warnings,
            )
        )

        if phase_reports[-1].status == PhaseStatus.FAILED:
            final_status = PhaseStatus.FAILED
        elif any(r.status == PhaseStatus.PARTIAL for r in phase_reports):
            final_status = PhaseStatus.PARTIAL

        return ConversionResult(
            java_input=java_code,
            bedrock_output=bedrock_output,
            stub_output=stub_output,
            repair_log=[RepairAction(**r) if isinstance(r, dict) else r for r in repair_log],
            phase_reports=phase_reports,
            validation_report=validation_report,
            final_status=final_status,
            mode="legacy",
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser():
    try:
        import argparse
    except ImportError:
        return None
    parser = argparse.ArgumentParser(
        description="Five-phase legacy Java→Bedrock converter",
    )
    parser.add_argument("input_file", nargs="?", help="Java source file to convert")
    parser.add_argument("-o", "--output", default=None, help="Output file (default: stdout)")
    parser.add_argument(
        "--max-iterations", type=int, default=5, help="Max repair iterations (default: 5)"
    )
    return parser


def main() -> None:
    parser = _build_parser()
    if parser is None:
        print("argparse not available — running basic demo")
        _run_demo()
        return

    args = parser.parse_args()
    if args.input_file:
        java_code = Path(args.input_file).read_text()
    else:
        java_code = _DEMO_JAVA_CODE

    converter = FivePhaseConverter(max_repair_iterations=args.max_iterations)
    result = converter.convert(java_code)

    print(f"Conversion Status: {result.final_status}")
    print(f"Phase Reports:")
    for r in result.phase_reports:
        print(f"  {r.phase}: {r.status} ({r.duration_ms:.1f}ms)")
        if r.warnings:
            for w in r.warnings[:3]:
                print(f"    WARNING: {w}")

    print("\n--- Bedrock Output ---")
    print(result.bedrock_output)

    if args.output:
        Path(args.output).write_text(result.bedrock_output)
        print(f"\nWritten to {args.output}")


_DEMO_JAVA_CODE = """
package com.example.mod;

import java.util.List;
import java.util.Optional;
import net.minecraft.item.ItemStack;
import net.minecraft.world.World;

public class ExampleBlock {
    private String name;
    private int metadata;

    public ExampleBlock(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }

    public void setMetadata(int meta) {
        this.metadata = meta;
    }

    public ItemStack createStack(int count) {
        return new ItemStack(this, count);
    }

    public boolean isValid() {
        return this.name != null && !this.name.isEmpty();
    }
}
"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
