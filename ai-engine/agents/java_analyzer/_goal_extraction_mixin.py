"""Entity / goal-selector extraction (mixin)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from ._constants import logger


class GoalExtractionMixin:
    """Entity goal/selector extraction from Java AST."""

    def extract_entity_goals_from_ast(self, tree: Dict) -> List[Dict[str, Any]]:
        """
        Extract entity AI goals from registerGoals() method AST.

        Parses GoalSelector.addGoal(...) and targetSelector.addGoal(...) call sites
        to extract goal type, priority, and constructor arguments.

        Args:
            tree: Parsed Java AST (tree-sitter format)

        Returns:
            List of goal dicts with keys: type, priority, config
        """
        goals: List[Dict[str, Any]] = []

        try:
            method_declarations = self._find_nodes_by_type(tree, "method_declaration")
            for method_node in method_declarations:
                method_name = self._get_method_name(method_node)
                if method_name not in ("registerGoals", "createGoals"):
                    continue

                block_nodes = self._find_nodes_by_type(method_node, "block")
                if not block_nodes:
                    continue

                goal_calls = self._find_goal_selector_calls(block_nodes[0])
                for call in goal_calls:
                    goal_info = self._parse_goal_call(call)
                    if goal_info:
                        goals.append(goal_info)

        except Exception as e:
            logger.warning(f"Error extracting entity goals from AST: {e}")

        return goals

    def _find_goal_selector_calls(self, block_node: Dict) -> List[Dict]:
        """Find all GoalSelector.addGoal/add calls within a block."""
        calls: List[Dict] = []
        method_invocations = self._find_nodes_by_type(block_node, "method_invocation")
        for inv in method_invocations:
            method_name = self._get_ts_method_name(inv)
            if method_name not in ("addGoal", "add"):
                continue
            for child in inv.get("children", []):
                if child.get("type") == "field_access":
                    qualifier = self._extract_field_access_name(child)
                    if qualifier and qualifier.lower() == "goalselector":
                        calls.append(inv)
                        break
        return calls

    def _extract_field_access_name(self, field_access_node: Dict) -> Optional[str]:
        """Extract the field name from a field_access node."""
        identifiers = []
        for child in field_access_node.get("children", []):
            if child.get("type") == "identifier":
                identifiers.append(child.get("text", ""))
        if identifiers:
            return identifiers[-1]
        return None

    def _parse_goal_call(self, inv_node: Dict) -> Optional[Dict[str, Any]]:
        """Parse a goal selector call into {type, priority, config}."""
        try:
            args = self._get_method_arguments(inv_node)
            if len(args) < 2:
                return None

            priority = self._extract_priority_from_arg(args[0])
            goal_class = self._extract_goal_class_name(args[1])

            if goal_class is None or priority is None:
                return None

            goal_constructor_args = self._extract_goal_constructor_args(args[1])
            goal_type = self._goal_class_to_type(goal_class)
            config = self._extract_goal_config(goal_class, args[2:], goal_constructor_args)

            return {"type": goal_type, "priority": priority, "config": config}
        except Exception:
            return None

    def _extract_goal_constructor_args(self, arg_node: Dict) -> Optional[List]:
        """Extract arguments from a goal constructor 'new GoalClass(...)' node."""
        try:
            if arg_node.get("type") != "object_creation_expression":
                return None
            for child in arg_node.get("children", []):
                if child.get("type") == "argument_list":
                    goal_args = []
                    for arg in child.get("children", []):
                        arg_type = arg.get("type")
                        if arg_type in (
                            "decimal_integer_literal",
                            "decimal_floating_point_literal",
                            "true",
                            "false",
                            "string_literal",
                        ):
                            goal_args.append(arg)
                    return goal_args
            return None
        except Exception:
            return None

    def _extract_priority_from_arg(self, arg_node: Dict) -> Optional[int]:
        """Extract integer priority from the first argument."""
        try:
            text = arg_node.get("text", "").strip()
            if text.isdigit():
                return int(text)
            if text.startswith("int(") or text.startswith("Integer."):
                return None
            return None
        except Exception:
            return None

    def _extract_goal_class_name(self, arg_node: Dict) -> Optional[str]:
        """Extract the Goal class name from 'new ClassName(...)' argument."""
        try:
            if arg_node.get("type") == "object_creation_expression":
                for child in arg_node.get("children", []):
                    child_type = child.get("type")
                    if child_type in ("identifier", "type_identifier"):
                        return child.get("text", "")
            if arg_node.get("type") == "class_literal":
                text = arg_node.get("text", "")
                return text.replace(".class", "") if text else None
            text = arg_node.get("text", "")
            if "Goal" in text:
                text = text.strip()
                if "(" in text:
                    text = text[: text.index("(")]
                return text
            return None
        except Exception:
            return None

    def _goal_class_to_type(self, class_name: str) -> str:
        """Convert a Java Goal class name to goal type string."""
        name = class_name
        name = re.sub(r"Goal$", "", name)
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
        return name

    def _extract_goal_config(
        self, goal_class: str, add_goal_args: List, goal_constructor_args: Optional[List] = None
    ) -> Dict[str, Any]:
        """Extract configuration from goal constructor arguments."""
        config: Dict[str, Any] = {}

        try:
            args = goal_constructor_args if goal_constructor_args else add_goal_args
            if not args:
                return config

            if "Attack" in goal_class and len(args) >= 2:
                speed = self._extract_numeric_arg(args[0])
                if speed:
                    config["speed_multiplier"] = speed
            elif "Stroll" in goal_class or "Wander" in goal_class or "Move" in goal_class:
                speed = self._extract_numeric_arg(args[0])
                if speed:
                    config["speed_multiplier"] = speed
            elif "LookAt" in goal_class:
                dist = self._extract_numeric_arg(args[0])
                if dist:
                    config["look_distance"] = dist
            elif "Follow" in goal_class:
                dist = self._extract_numeric_arg(args[0])
                if dist:
                    config["distance"] = dist
        except Exception:
            pass

        return config

    def _get_method_arguments(self, inv_node: Dict) -> List:
        """Extract arguments from method_invocation node."""
        args = []
        for child in inv_node.get("children", []):
            if child.get("type") == "argument_list":
                for arg in child.get("children", []):
                    if arg.get("type") not in ["(", ")", ","]:
                        args.append(arg)
        return args
