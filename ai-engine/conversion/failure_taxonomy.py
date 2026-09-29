"""
Operational Failure Taxonomy for PortKit's Converter and Validator Agents.

Implements a research-validated taxonomy of operational safety failures in autonomous
coding agents (arxiv:2605.30777) mapped to PortKit's Java->Bedrock conversion pipeline.

Failure Categories:
    FABRICATED_SUCCESS    - Converter claims success but output is wrong (runtime errors,
                            wrong behavior despite syntactic validity)
    SCOPE_CREEP           - Converter handles out-of-scope features incorrectly (modifies
                            Java constructs beyond conversion task scope)
    HALLUCINATED_API      - Converter uses Bedrock APIs that don't exist
    INCOMPLETE_CONVERSION - Partial conversion leaving TODO/??? markers
    TYPE_MISMATCH         - Java types not correctly mapped to Bedrock types
    DEPENDENCY_MISMATCH   - Missing/wrong @minecraft/server module imports
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class FailureType(str, Enum):
    FABRICATED_SUCCESS = "fabricated_success"
    SCOPE_CREEP = "scope_creep"
    HALLUCINATED_API = "hallucinated_api"
    INCOMPLETE_CONVERSION = "incomplete_conversion"
    TYPE_MISMATCH = "type_mismatch"
    DEPENDENCY_MISMATCH = "dependency_mismatch"
    NONE = "none"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FailureEvidence:
    location: str
    description: str
    snippet: Optional[str] = None


@dataclass
class FailureClassification:
    failure_type: FailureType
    confidence: float
    evidence: List[FailureEvidence] = field(default_factory=list)
    message: str = ""
    severity: Severity = Severity.MEDIUM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_type": self.failure_type.value,
            "confidence": self.confidence,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": [
                {
                    "location": e.location,
                    "description": e.description,
                    "snippet": e.snippet,
                }
                for e in self.evidence
            ],
        }


INCOMPLETE_MARKERS = frozenset(
    {
        "???",
        "TODO",
        "FIXME",
        "UNCONVERTED",
        "NOT_YET_IMPLEMENTED",
        "PLACEHOLDER",
        "MISSING_IMPLEMENTATION",
    }
)

BEDROCK_API_KEYWORDS = frozenset(
    {
        "minecraft.server",
        "world.afterEvents",
        "world.beforeEvents",
        "player.afterEvents",
        "player.beforeEvents",
        "entity.afterEvents",
        "entity.beforeEvents",
        "system.run",
        "system.runInterval",
        "system.runTimeout",
        "world.getAllPlayers",
        "world.getDimension",
        "block.setPermutation",
        "world.getBlock",
        "player.dimension",
    }
)


VALID_BEDROCK_API_PATTERNS = re.compile(
    r"""
    (minecraft__server|@minecraft/server)  |
    (world|player|entity|block|item|dimension|container|inventory)
    \.
    (afterEvents|beforeEvents|get|set|run|sendMessage|execute|getComponent|setComponent|hasComponent|
     addEffect|removeEffect|getEntities|getBlock|setBlock|getPlayers|getAll|clear|transfer|
     isValid|exists|name|typeId|location|velocity|rotation|dimension)
    """,
    re.VERBOSE | re.IGNORECASE,
)


UNCONVERTABLE_MARKERS = frozenset(
    {
        "unconvertable",
        "no bedrock equivalent",
        "not supported in bedrock",
        "no direct equivalent",
        "unsupported feature",
        "cannot convert",
        "no minecraft server api for",
    }
)


JAVA_REFLECTION_PATTERNS = re.compile(
    r"""
    \.getClass\(\)|
    \.getDeclaredMethods|
    \.getDeclaredFields|
    \.invoke\(|
    \.forName\(|
    Class\.forName|
    Reflection|
    Modifier\.isPrivate|
    Modifier\.isPublic|
    Modifier\.isStatic
    """,
    re.VERBOSE,
)

JAVA_THREAD_PATTERNS = re.compile(
    r"""
    new\s+Thread\(|
    Thread\.sleep\(|
    ExecutorService|
    Future<|
    CompletableFuture|
    synchronized\s*\(|
    ConcurrentHashMap|
    AtomicInteger|
    ReentrantLock
    """,
    re.VERBOSE,
)


@dataclass
class ConversionContext:
    java_input: str = ""
    bedrock_output: str = ""
    conversion_scope: Optional[List[str]] = None
    known_bedrock_apis: Optional[frozenset] = None


class FailureClassifier:
    def __init__(self, hardening_mode: bool = False):
        self.hardening_mode = hardening_mode
        self._bedrock_api_cache: Optional[frozenset] = None

    def classify(
        self,
        bedrock_output: str,
        java_input: str = "",
        conversion_scope: Optional[List[str]] = None,
    ) -> FailureClassification:
        ctx = ConversionContext(
            java_input=java_input,
            bedrock_output=bedrock_output,
            conversion_scope=conversion_scope,
        )
        candidates: List[Tuple[FailureType, float, List[FailureEvidence]]] = []

        candidates.append(self._check_incomplete_conversion(bedrock_output, ctx))
        candidates.append(self._check_hallucinated_api(bedrock_output, ctx))
        candidates.append(self._check_type_mismatch(bedrock_output, ctx))
        candidates.append(self._check_dependency_mismatch(bedrock_output, ctx))
        candidates.append(self._check_scope_creep(bedrock_output, java_input, ctx))
        candidates.append(self._check_fabricated_success(bedrock_output, ctx))

        priority = {
            FailureType.INCOMPLETE_CONVERSION: 1,
            FailureType.HALLUCINATED_API: 2,
            FailureType.TYPE_MISMATCH: 3,
            FailureType.FABRICATED_SUCCESS: 4,
            FailureType.SCOPE_CREEP: 5,
            FailureType.DEPENDENCY_MISMATCH: 6,
        }
        valid = [(ft, c, ev) for ft, c, ev in candidates if ft != FailureType.NONE and c >= 0.3]
        if not valid:
            return FailureClassification(
                failure_type=FailureType.NONE,
                confidence=1.0,
                message="No failure detected.",
            )

        best_with_priority = sorted(valid, key=lambda x: (-x[1], priority.get(x[0], 99)))
        failure_type, confidence, evidence = best_with_priority[0]

        severity = self._severity_for(confidence)
        message = self._message_for(failure_type, evidence)

        return FailureClassification(
            failure_type=failure_type,
            confidence=round(confidence, 2),
            evidence=evidence,
            message=message,
            severity=severity,
        )

    def classify_all(
        self,
        bedrock_output: str,
        java_input: str = "",
        conversion_scope: Optional[List[str]] = None,
    ) -> List[FailureClassification]:
        ctx = ConversionContext(
            java_input=java_input,
            bedrock_output=bedrock_output,
            conversion_scope=conversion_scope,
        )
        results: List[FailureClassification] = []

        checks = [
            (FailureType.INCOMPLETE_CONVERSION, self._check_incomplete_conversion),
            (FailureType.HALLUCINATED_API, self._check_hallucinated_api),
            (FailureType.TYPE_MISMATCH, self._check_type_mismatch),
            (FailureType.DEPENDENCY_MISMATCH, self._check_dependency_mismatch),
            (FailureType.SCOPE_CREEP, lambda out, c: self._check_scope_creep(out, java_input, c)),
            (FailureType.FABRICATED_SUCCESS, self._check_fabricated_success),
        ]

        for failure_type, check_fn in checks:
            ft, confidence, evidence = check_fn(bedrock_output, ctx)
            if ft != FailureType.NONE and confidence >= 0.3:
                results.append(
                    FailureClassification(
                        failure_type=ft,
                        confidence=round(confidence, 2),
                        evidence=evidence,
                        message=self._message_for(ft, evidence),
                        severity=self._severity_for(confidence),
                    )
                )

        return results

    def _check_incomplete_conversion(
        self, bedrock_output: str, ctx: ConversionContext
    ) -> Tuple[FailureType, float, List[FailureEvidence]]:
        evidence: List[FailureEvidence] = []
        for line_no, line in enumerate(bedrock_output.splitlines(), 1):
            for marker in INCOMPLETE_MARKERS:
                if marker in line:
                    evidence.append(
                        FailureEvidence(
                            location=f"line {line_no}",
                            description=f"Incomplete conversion marker '{marker}' found",
                            snippet=line.strip()[:120],
                        )
                    )
        if not evidence:
            return FailureType.NONE, 0.0, []
        confidence = min(0.95, 0.5 + 0.15 * len(evidence))
        return FailureType.INCOMPLETE_CONVERSION, confidence, evidence

    KNOWN_BEDROCK_METHODS = frozenset(
        {
            "afterEvents",
            "beforeEvents",
            "getAllPlayers",
            "getDimension",
            "getBlock",
            "setPermutation",
            "getComponent",
            "setComponent",
            "hasComponent",
            "addEffect",
            "removeEffect",
            "getEntities",
            "setBlock",
            "getPlayers",
            "getAll",
            "clear",
            "transfer",
            "isValid",
            "exists",
            "name",
            "typeId",
            "location",
            "velocity",
            "rotation",
            "dimension",
            "sendMessage",
            "execute",
            "run",
            "runInterval",
            "runTimeout",
            "subscribe",
            "unsubscribe",
            "getContainer",
            "getInventory",
            "setRotation",
            "setVelocity",
            "addTag",
            "removeTag",
            "hasTag",
            "kill",
            "teleport",
            "getEntitiesOfType",
            "getItemStack",
            "setItem",
        }
    )

    def _check_hallucinated_api(
        self, bedrock_output: str, ctx: ConversionContext
    ) -> Tuple[FailureType, float, List[FailureEvidence]]:
        evidence: List[FailureEvidence] = []

        for line_no, line in enumerate(bedrock_output.splitlines(), 1):
            if "minecraft" in line.lower() and "__" in line:
                evidence.append(
                    FailureEvidence(
                        location=f"line {line_no}",
                        description="Suspicious double-underscore minecraft API (possibly hallucinated)",
                        snippet=line.strip()[:120],
                    )
                )

            for match in re.finditer(
                r"(world|player|entity|block|item|dimension|container)\.(\w+)\(",
                line,
                re.IGNORECASE,
            ):
                method_name = match.group(2).lower()
                if method_name not in self.KNOWN_BEDROCK_METHODS:
                    evidence.append(
                        FailureEvidence(
                            location=f"line {line_no}",
                            description=f"Potentially non-existent Bedrock API: {match.group(1)}.{method_name}()",
                            snippet=line.strip()[:120],
                        )
                    )
        if not evidence:
            return FailureType.NONE, 0.0, []
        confidence = min(0.9, 0.4 + 0.1 * len(evidence))
        return FailureType.HALLUCINATED_API, confidence, evidence

    def _check_type_mismatch(
        self, bedrock_output: str, ctx: ConversionContext
    ) -> Tuple[FailureType, float, List[FailureEvidence]]:
        evidence: List[FailureEvidence] = []
        problematic_mappings = [
            (r"\blong\b", "long should map to number in Bedrock"),
            (r"\bfloat\b(?!\s*[A-Za-z])", "float type may need explicit handling in Bedrock JS"),
            (r"\bArrayList\b", "ArrayList should be converted to Array"),
            (r"\bHashMap\b", "HashMap should be converted to Map"),
            (r"List<\s*\w+\s*>", "Java generic List should become Array in Bedrock"),
        ]
        for pattern, description in problematic_mappings:
            for match in re.finditer(pattern, bedrock_output):
                start = max(0, match.start() - 20)
                end = min(len(bedrock_output), match.end() + 20)
                snippet = bedrock_output[start:end]
                evidence.append(
                    FailureEvidence(
                        location=f"pos {match.start()}",
                        description=description,
                        snippet=snippet,
                    )
                )
        if not evidence:
            return FailureType.NONE, 0.0, []
        confidence = min(0.85, 0.5 + 0.1 * len(evidence))
        return FailureType.TYPE_MISMATCH, confidence, evidence

    def _check_dependency_mismatch(
        self, bedrock_output: str, ctx: ConversionContext
    ) -> Tuple[FailureType, float, List[FailureEvidence]]:
        evidence: List[FailureEvidence] = []
        has_import = bool(re.search(r"import.*minecraft", bedrock_output, re.IGNORECASE))
        uses_minecraft_api = bool(
            re.search(r"(world|player|entity|block|item)\.", bedrock_output, re.IGNORECASE)
        )
        if uses_minecraft_api and not has_import:
            evidence.append(
                FailureEvidence(
                    location="import section",
                    description="Uses Bedrock Script API without import statement",
                    snippet=None,
                )
            )
        wrong_imports = re.findall(
            r"import\s+.*(?:java\.|javax\.|org\.|com\.)", bedrock_output, re.IGNORECASE
        )
        for imp in wrong_imports:
            evidence.append(
                FailureEvidence(
                    location="import",
                    description="Java import found in Bedrock output",
                    snippet=imp.strip()[:80],
                )
            )
        if not evidence:
            return FailureType.NONE, 0.0, []
        confidence = min(0.9, 0.6 + 0.1 * len(evidence))
        return FailureType.DEPENDENCY_MISMATCH, confidence, evidence

    def _check_scope_creep(
        self, bedrock_output: str, java_input: str, ctx: ConversionContext
    ) -> Tuple[FailureType, float, List[FailureEvidence]]:
        evidence: List[FailureEvidence] = []
        if not java_input:
            return FailureType.NONE, 0.0, []

        for marker in UNCONVERTABLE_MARKERS:
            if marker.lower() in bedrock_output.lower():
                evidence.append(
                    FailureEvidence(
                        location="general",
                        description=f"Unconvertable feature marker '{marker}' suggests scope creep or unsupported feature",
                        snippet=None,
                    )
                )

        if JAVA_REFLECTION_PATTERNS.search(java_input) and not JAVA_REFLECTION_PATTERNS.search(
            bedrock_output
        ):
            evidence.append(
                FailureEvidence(
                    location="general",
                    description="Java reflection used but not reflected in Bedrock output (scope creep or silent drop)",
                    snippet=None,
                )
            )

        if JAVA_THREAD_PATTERNS.search(java_input) and not re.search(
            r"(system\.run|async|await|Promise)", bedrock_output, re.IGNORECASE
        ):
            evidence.append(
                FailureEvidence(
                    location="general",
                    description="Java threading/concurrency code without Bedrock async equivalent",
                    snippet=None,
                )
            )
        if not evidence:
            return FailureType.NONE, 0.0, []
        confidence = min(0.88, 0.5 + 0.12 * len(evidence))
        return FailureType.SCOPE_CREEP, confidence, evidence

    def _check_fabricated_success(  # noqa: C901 - minimal state machine for bracket tracking
        self, bedrock_output: str, ctx: ConversionContext
    ) -> Tuple[FailureType, float, List[FailureEvidence]]:
        evidence: List[FailureEvidence] = []
        lines = bedrock_output.splitlines()
        if not bedrock_output.strip() or all(
            not line.strip() or line.strip().startswith("//") for line in lines
        ):
            evidence.append(
                FailureEvidence(
                    location="output",
                    description="Bedrock output is empty or contains only comments",
                    snippet=None,
                )
            )
            return FailureType.FABRICATED_SUCCESS, 0.97, evidence

        brace_count, paren_count = 0, 0
        in_string = in_block_comment = False
        string_char = ""

        for line_no, line in enumerate(lines, 1):
            chars = list(line)
            for idx, c in enumerate(chars):
                n = chars[idx + 1] if idx + 1 < len(chars) else ""

                if in_block_comment:
                    if c == "*" and n == "/":
                        in_block_comment = False
                    continue
                if c == "/" and n == "/":
                    break
                if c == "/" and n == "*":
                    in_block_comment = True
                    continue

                if in_string:
                    if c == "\\" and idx + 1 < len(chars):
                        continue
                    if c == string_char:
                        in_string = False
                    continue

                if c in ('"', "'", "`"):
                    in_string = True
                    string_char = c
                    continue

                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count < 0:
                        evidence.append(
                            FailureEvidence(
                                location=f"line {line_no}",
                                description="Unexpected closing brace '}' - possible syntax error",
                                snippet=line.strip()[:80],
                            )
                        )
                        brace_count = 0
                elif c == "(":
                    paren_count += 1
                elif c == ")":
                    paren_count -= 1
                    if paren_count < 0:
                        evidence.append(
                            FailureEvidence(
                                location=f"line {line_no}",
                                description="Unexpected closing parenthesis - possible syntax error",
                                snippet=line.strip()[:80],
                            )
                        )
                        paren_count = 0

        if brace_count > 0:
            evidence.append(
                FailureEvidence(
                    location="general",
                    description=f"Unclosed {{}} block(s) - {brace_count} unclosed brace(s)",
                    snippet=None,
                )
            )
        if paren_count > 0:
            evidence.append(
                FailureEvidence(
                    location="general",
                    description=f"Unclosed parenthesis - {paren_count} unclosed paren(s)",
                    snippet=None,
                )
            )
        if not evidence:
            return FailureType.NONE, 0.0, []
        confidence = min(0.92, 0.6 + 0.1 * len(evidence))
        return FailureType.FABRICATED_SUCCESS, confidence, evidence

    def _severity_for(self, confidence: float) -> Severity:
        if confidence >= 0.85:
            return Severity.CRITICAL
        elif confidence >= 0.7:
            return Severity.HIGH
        elif confidence >= 0.5:
            return Severity.MEDIUM
        return Severity.LOW

    def _message_for(self, failure_type: FailureType, evidence: List[FailureEvidence]) -> str:
        messages = {
            FailureType.FABRICATED_SUCCESS: (
                "Converter claims success but Bedrock output contains structural/syntax errors "
                "that will cause runtime failures."
            ),
            FailureType.SCOPE_CREEP: (
                "Converter attempted features beyond conversion scope or without Bedrock equivalent, "
                "producing incorrect stubs or silently dropping features."
            ),
            FailureType.HALLUCINATED_API: (
                "Converter used Bedrock Script APIs that do not exist in the official API surface."
            ),
            FailureType.INCOMPLETE_CONVERSION: (
                "Converter left incomplete markers (TODO/???/UNCONVERTED) in the output."
            ),
            FailureType.TYPE_MISMATCH: (
                "Java types were not correctly mapped to Bedrock-compatible types."
            ),
            FailureType.DEPENDENCY_MISMATCH: (
                "Converter output contains Java module imports that have no Bedrock equivalent."
            ),
        }
        base = messages.get(failure_type, "Unknown failure type.")
        if evidence:
            base += f" ({len(evidence)} evidence(s) found)"
        return base


def classify_conversion_failure(
    bedrock_output: str,
    java_input: str = "",
    conversion_scope: Optional[List[str]] = None,
    hardening_mode: bool = False,
) -> FailureClassification:
    classifier = FailureClassifier(hardening_mode=hardening_mode)
    return classifier.classify(bedrock_output, java_input, conversion_scope)


def classify_all_failures(
    bedrock_output: str,
    java_input: str = "",
    conversion_scope: Optional[List[str]] = None,
    hardening_mode: bool = False,
) -> List[FailureClassification]:
    classifier = FailureClassifier(hardening_mode=hardening_mode)
    return classifier.classify_all(bedrock_output, java_input, conversion_scope)
