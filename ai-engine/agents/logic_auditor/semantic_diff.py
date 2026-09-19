"""semantic_diff - Java vs Bedrock semantic diff engine.

Seam: lines 85-482 of the original logic_auditor_agent.py (the 5 checker classes
that pair-extract Java and Bedrock patterns and emit AuditFindings for each
divergence: FormulaDriftChecker, ProbabilityInversionChecker,
EventHookMismatchChecker, ConditionalNegationChecker, ResourceIDMatchChecker).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .audit_reporter import AuditFinding
from .pattern_detector import SemanticType, Severity


class FormulaDriftChecker:
    """Checks for coefficient drift and operator substitution in numeric formulas."""

    def __init__(self):
        self.check_type = "formula_drift"
        self.operator_patterns = [
            (r"\*\s*(\d+\.?\d*)", "*", "multiplication"),
            (r"\+\s*(\d+\.?\d*)", "+", "addition"),
            (r"-\s*(\d+\.?\d*)", "-", "subtraction"),
            (r"/\s*(\d+\.?\d*)", "/", "division"),
        ]

    def check(self, java_code: str, bedrock_code: str) -> List[AuditFinding]:
        findings = []
        java_formulas = self._extract_formulas(java_code, is_java=True)
        bedrock_formulas = self._extract_formulas(bedrock_code, is_java=False)

        for java_formula in java_formulas:
            for bedrock_formula in bedrock_formulas:
                finding = self._compare_formulas(java_formula, bedrock_formula)
                if finding:
                    findings.append(finding)
        return findings

    def _extract_formulas(self, code: str, is_java: bool) -> List[Dict[str, Any]]:
        formulas = []
        lines = code.split("\n")
        for i, line in enumerate(lines, start=1):
            if is_java:
                matches = re.findall(r"(\w+)\s*=\s*([^;]+);", line)
                for var, expr in matches:
                    if any(op in expr for op in ["*", "+", "-", "/"]):
                        formulas.append({"var": var, "expr": expr.strip(), "line": i})
            else:
                matches = re.findall(r"(\w+)\s*=\s*([^;]+);", line)
                for var, expr in matches:
                    if any(op in expr for op in ["*", "+", "-", "/"]):
                        formulas.append({"var": var, "expr": expr.strip(), "line": i})
        return formulas

    def _compare_formulas(self, java: Dict, bedrock: Dict) -> Optional[AuditFinding]:
        java_expr = java["expr"]
        bedrock_expr = bedrock["expr"]

        if java["var"] != bedrock["var"]:
            return None

        java_has_coef = re.search(r"\*\s*(\d+\.?\d*)", java_expr)
        bedrock_has_addcoef = re.search(r"\+\s*(\d+\.?\d*)", bedrock_expr)

        if java_has_coef and bedrock_has_addcoef:
            java_coef = java_has_coef.group(1)
            bedrock_add = bedrock_has_addcoef.group(1)
            bedrock_ends_with_addcoef = (
                bedrock_expr.strip().rstrip(";").endswith(f"+ {bedrock_add}")
            )
            if java_coef == bedrock_add and bedrock_ends_with_addcoef:
                return AuditFinding(
                    check_type=self.check_type,
                    severity=Severity.HIGH,
                    description=f"Operator substitution detected: multiplication converted to addition for variable '{java['var']}'",
                    java_snippet=f"{java['var']} = {java_expr}",
                    bedrock_snippet=f"{bedrock['var']} = {bedrock_expr}",
                    expected_behavior=f"Java: {java['var']} should scale by {java_coef}x",
                    actual_behavior=f"Bedrock: {bedrock['var']} adds {bedrock_add} instead",
                )

        java_mult_matches = re.findall(r"(\w+)\s*\*\s*(\d+\.?\d*)", java_expr)
        bedrock_add_matches = re.findall(r"(\w+)\s*\+\s*(\d+\.?\d*)", bedrock_expr)
        if java_mult_matches and bedrock_add_matches:
            java_vars = {m[0] for m in java_mult_matches}
            bedrock_vars = {m[0] for m in bedrock_add_matches}
            if java_vars & bedrock_vars:
                return AuditFinding(
                    check_type=self.check_type,
                    severity=Severity.HIGH,
                    description="Coefficient drift: multiplication pattern in Java became addition in Bedrock",
                    java_snippet=f"{java['var']} = {java_expr}",
                    bedrock_snippet=f"{bedrock['var']} = {bedrock_expr}",
                    expected_behavior=f"Value should be multiplied: {java_mult_matches}",
                    actual_behavior=f"Value is being added: {bedrock_add_matches}",
                )

        return None


class ProbabilityInversionChecker:
    """Checks for comparison direction and threshold value errors in probability/RNG code."""

    JAVA_RANDOM_PATTERNS = [
        r"random\.nextDouble\(\)\s*([<>]=?)\s*([\d.]+)",
        r"Math\.random\(\)\s*([<>]=?)\s*([\d.]+)",
        r"Random\(\)\.nextFloat\(\)\s*([<>]=?)\s*([\d.]+)",
        r"random\s*([<>]=?)\s*([\d.]+)",  # bare random variable like "random >= 0.5"
    ]

    BEDROCK_RANDOM_PATTERNS = [
        r"Math\.random\(\)\s*([<>]=?)\s*([\d.]+)",
        r"this\.world\.getRandom\(\)\.nextFloat\(\)\s*([<>]=?)\s*([\d.]+)",
    ]

    def __init__(self):
        self.check_type = "probability_inversion"

    def check(self, java_code: str, bedrock_code: str) -> List[AuditFinding]:
        findings = []
        java_probs = self._extract_probabilities(java_code, is_java=True)
        bedrock_probs = self._extract_probabilities(bedrock_code, is_java=False)

        for java_prob in java_probs:
            for bedrock_prob in bedrock_probs:
                finding = self._compare_probability(java_prob, bedrock_prob)
                if finding:
                    findings.append(finding)
        return findings

    def _extract_probabilities(self, code: str, is_java: bool) -> List[Dict[str, Any]]:
        probabilities = []
        patterns = self.JAVA_RANDOM_PATTERNS if is_java else self.BEDROCK_RANDOM_PATTERNS
        lines = code.split("\n")
        for i, line in enumerate(lines, start=1):
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    operator = match.group(1)
                    threshold = float(match.group(2))
                    context = line.strip()
                    probabilities.append(
                        {
                            "operator": operator,
                            "threshold": threshold,
                            "line": i,
                            "context": context,
                            "inverted": False,
                        }
                    )
        return probabilities

    def _compare_probability(self, java_prob: Dict, bedrock_prob: Dict) -> Optional[AuditFinding]:
        java_op = java_prob["operator"]
        bedrock_op = bedrock_prob["operator"]

        opposites = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}

        if opposites.get(java_op) == bedrock_op:
            return AuditFinding(
                check_type=self.check_type,
                severity=Severity.HIGH,
                description=f"Probability comparison inverted: '{java_op}' in Java became '{bedrock_op}' in Bedrock",
                java_snippet=java_prob["context"],
                bedrock_snippet=bedrock_prob["context"],
                expected_behavior=f"Java triggers when random {java_op} {java_prob['threshold']}",
                actual_behavior=f"Bedrock triggers when random {bedrock_op} {bedrock_prob['threshold']} (inverted!)",
            )

        if abs(java_prob["threshold"] - bedrock_prob["threshold"]) > 0.001:
            return AuditFinding(
                check_type=self.check_type,
                severity=Severity.HIGH,
                description=f"Probability threshold modified: Java uses {java_prob['threshold']}, Bedrock uses {bedrock_prob['threshold']}",
                java_snippet=java_prob["context"],
                bedrock_snippet=bedrock_prob["context"],
                expected_behavior=f"Should trigger at probability {java_prob['threshold']}",
                actual_behavior=f"Triggers at probability {bedrock_prob['threshold']}",
            )

        return None


class EventHookMismatchChecker:
    """Checks for lifecycle stage and trigger condition mismatches between Java and Bedrock."""

    JAVA_EVENT_HOOKS = {
        "BREAK_BLOCK": ["onBlockDestroyed", "onDestroy", "onBreak", "destroyBlock"],
        "INTERACT": ["onInteract", "onUse", "onPlayerInteract", "useItem"],
        "ATTACK": ["onAttack", "onEntityHit", "onHit", "attackEntity"],
        "SPAWN": ["onSpawn", "onCreated", "onInitialize", "onLoad"],
        "TICK": ["onTick", "update", "onUpdate", "tick"],
        "DAMAGE": ["onDamage", "onEntityDamage", "onHurt", "onTakeDamage"],
    }

    BEDROCK_EVENT_HOOKS = {
        "step_on": ["onStepOn", "onPlayerInteractWithBlock"],
        "interact": ["onInteract", "onUseItem", "onItemUse"],
        "attack": ["onAttack", "onHurtEntity", "onEntityAttack"],
        "spawn": ["onSpawn", "initialize", "onInitialize"],
        "tick": ["onTick", "tick", "onTick"],
        "break_block": ["onBlockDestroyed", "onDestroyBlock", "onBreakBlock"],
    }

    JAVA_TO_BEDROCK_HOOK_MAP = {
        "BREAK_BLOCK": "break_block",
        "INTERACT": "interact",
        "ATTACK": "attack",
        "SPAWN": "spawn",
        "TICK": "tick",
        "DAMAGE": "interact",
    }

    def __init__(self):
        self.check_type = "event_hook_mismatch"

    def check(self, java_code: str, bedrock_code: str) -> List[AuditFinding]:
        findings = []
        java_hooks = self._extract_java_hooks(java_code)
        bedrock_hooks = self._extract_bedrock_hooks(bedrock_code)
        bedrock_hook_names = {h for h, _ in bedrock_hooks}

        for java_hook, context in java_hooks:
            java_event_type = self._classify_java_hook(java_hook)
            if java_event_type:
                correct_bedrock_hooks = self.BEDROCK_EVENT_HOOKS.get(
                    self.JAVA_TO_BEDROCK_HOOK_MAP.get(java_event_type, ""), []
                )
                if correct_bedrock_hooks:
                    has_correct_hook = any(
                        correct_hook in bedrock_hook_names for correct_hook in correct_bedrock_hooks
                    )
                    if not has_correct_hook and bedrock_hook_names:
                        wrong_hook = list(bedrock_hook_names)[0]
                        finding = AuditFinding(
                            check_type=self.check_type,
                            severity=Severity.HIGH,
                            description=f"Event hook mismatch: Java uses '{java_hook}' which should map to one of {correct_bedrock_hooks} but Bedrock uses '{wrong_hook}'",
                            java_snippet=context,
                            bedrock_snippet=self._get_bedrock_context(bedrock_code, wrong_hook),
                            expected_behavior=f"Event should trigger on one of {correct_bedrock_hooks}",
                            actual_behavior=f"Event is hooked to {wrong_hook}, which is wrong lifecycle",
                        )
                        findings.append(finding)
        return findings

    def _extract_java_hooks(self, code: str) -> List[Tuple[str, str]]:
        hooks = []
        for event_family, hook_names in self.JAVA_EVENT_HOOKS.items():
            for hook_name in hook_names:
                pattern = rf"public\s+void\s+{hook_name}\s*\("
                for i, line in enumerate(code.split("\n"), start=1):
                    if re.search(pattern, line):
                        hooks.append((hook_name, line.strip()))
        return hooks

    def _extract_bedrock_hooks(self, code: str) -> List[Tuple[str, str]]:
        hooks = []
        for hook_family, hook_names in self.BEDROCK_EVENT_HOOKS.items():
            for hook_name in hook_names:
                hook_name_lower = hook_name.lower()
                for i, line in enumerate(code.split("\n"), start=1):
                    line_lower = line.lower()
                    if (
                        hook_name_lower in line_lower
                        or f"'{hook_name}'" in line
                        or f"this.{hook_name}" in line
                    ):
                        hooks.append((hook_name, line.strip()))
        return hooks

    def _classify_java_hook(self, hook_name: str) -> Optional[str]:
        for event_type, hook_names in self.JAVA_EVENT_HOOKS.items():
            if hook_name in hook_names:
                return event_type
        return None

    def _get_bedrock_context(self, code: str, hook_name: str) -> str:
        for line in code.split("\n"):
            if hook_name in line:
                return line.strip()
        return f"<hook {hook_name} not found in code>"


class ConditionalNegationChecker:
    """Checks for negation drift and operator substitution in conditionals."""

    def __init__(self):
        self.check_type = "conditional_negation"

    def check(self, java_code: str, bedrock_code: str) -> List[AuditFinding]:
        findings = []
        java_conditionals = self._extract_conditionals(java_code, is_java=True)
        bedrock_conditionals = self._extract_conditionals(bedrock_code, is_java=False)

        for java_cond in java_conditionals:
            for bedrock_cond in bedrock_conditionals:
                finding = self._compare_conditionals(java_cond, bedrock_cond)
                if finding:
                    findings.append(finding)
        return findings

    def _extract_conditionals(self, code: str, is_java: bool) -> List[Dict[str, Any]]:
        conditionals = []
        patterns = [
            r"if\s*\(([^)]+)\)",
            r"else\s+if\s*\(([^)]+)\)",
            r"while\s*\(([^)]+)\)",
            r"for\s*\([^)]*;\s*([^;]+);",
        ]

        lines = code.split("\n")
        for i, line in enumerate(lines, start=1):
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    condition = match.group(1).strip()
                    conditionals.append(
                        {
                            "condition": condition,
                            "line": i,
                            "context": line.strip(),
                        }
                    )
        return conditionals

    def _compare_conditionals(self, java_cond: Dict, bedrock_cond: Dict) -> Optional[AuditFinding]:
        java_cond_str = java_cond["condition"]
        bedrock_cond_str = bedrock_cond["condition"]

        java_has_and = "&&" in java_cond_str
        bedrock_has_or = "||" in bedrock_cond_str

        if java_has_and and bedrock_has_or:
            return AuditFinding(
                check_type=self.check_type,
                severity=Severity.HIGH,
                description="Conditional operator drift: '&&' in Java became '||' in Bedrock",
                java_snippet=java_cond["context"],
                bedrock_snippet=bedrock_cond["context"],
                expected_behavior=f"Java: both conditions must be true: {java_cond_str}",
                actual_behavior=f"Bedrock: either condition triggers (changed logic): {bedrock_cond_str}",
            )

        java_operators = re.findall(r"([<>=!]+)", java_cond_str)
        bedrock_operators = re.findall(r"([<>=!]+)", bedrock_cond_str)

        opposites = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
        for java_op in java_operators:
            if java_op in opposites:
                if opposites[java_op] in bedrock_operators:
                    return AuditFinding(
                        check_type=self.check_type,
                        severity=Severity.HIGH,
                        description=f"Comparison operator inverted: '{java_op}' became '{opposites[java_op]}'",
                        java_snippet=java_cond["context"],
                        bedrock_snippet=bedrock_cond["context"],
                        expected_behavior=f"Java condition: {java_cond_str}",
                        actual_behavior=f"Bedrock condition: {bedrock_cond_str} (inverted!)",
                    )

        return None


class ResourceIDMatchChecker:
    """Checks for namespace match and ID case sensitivity issues."""

    def __init__(self):
        self.check_type = "resource_id_match"

    def check(self, java_code: str, bedrock_code: str) -> List[AuditFinding]:
        findings = []
        java_ids = self._extract_resource_ids(java_code)
        bedrock_ids = self._extract_resource_ids(bedrock_code)

        for java_ns, java_id in java_ids:
            for bedrock_ns, bedrock_id in bedrock_ids:
                if java_id.lower() == bedrock_id.lower() and java_id != bedrock_id:
                    findings.append(
                        AuditFinding(
                            check_type=self.check_type,
                            severity=Severity.MEDIUM,
                            description=f"Resource ID case mismatch: '{java_id}' vs '{bedrock_id}'",
                            java_snippet=f"{java_ns}:{java_id}",
                            bedrock_snippet=f"{bedrock_ns}:{bedrock_id}",
                            expected_behavior=f"ID should be '{java_id}'",
                            actual_behavior=f"ID is '{bedrock_id}' (case difference)",
                        )
                    )
        return findings

    def _extract_resource_ids(self, code: str) -> List[Tuple[str, str]]:
        ids = []
        patterns = [
            r"\"([a-zA-Z_]+):([a-zA-Z_]+)\"",
            r"'([a-zA-Z_]+):([a-zA-Z_]+)'",
            r"identifier\s*:\s*\"([a-zA-Z_]+):([a-zA-Z_]+)\"",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, code)
            for namespace, resource_id in matches:
                ids.append((namespace, resource_id))
        return ids


ADVERSARIAL_CHECKS = {
    SemanticType.NUMERIC_FORMULA: FormulaDriftChecker(),
    SemanticType.PROBABILITY_RNG: ProbabilityInversionChecker(),
    SemanticType.EVENT_HOOK: EventHookMismatchChecker(),
    SemanticType.CONDITIONAL: ConditionalNegationChecker(),
    SemanticType.RESOURCE_ID: ResourceIDMatchChecker(),
}
