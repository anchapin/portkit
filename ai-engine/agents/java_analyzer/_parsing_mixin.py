"""Tree-sitter parsing & AST node-text helpers (mixin)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from ._constants import logger, TREE_SITTER_AVAILABLE, Language, Parser, ts_java


class SourceParsingMixin:
    """Tree-sitter parsing + AST text-extraction helpers."""

    def parse_java_source(self, source_code: str) -> Optional[Dict]:
        """Parse Java source code into an AST using tree-sitter."""
        parser = self._get_tree_sitter_parser()
        if parser is None:
            return self._parse_java_source_fallback(source_code)

        try:
            tree = parser.parse(bytes(source_code, "utf8"))
            return self._tree_sitter_to_dict(tree.root_node)
        except Exception as e:
            logger.warning(f"Tree-sitter parsing failed: {e}")
            return self._parse_java_source_fallback(source_code)

    def _get_tree_sitter_parser(self):
        """Get or create tree-sitter parser instance."""
        if not TREE_SITTER_AVAILABLE:
            return None
        if not hasattr(self, "_ts_parser") or self._ts_parser is None:
            try:
                lang = Language(ts_java.language())
                self._ts_parser = Parser(lang)
            except Exception as e:
                logger.warning(f"Failed to initialize tree-sitter parser: {e}")
                self._ts_parser = None
        return self._ts_parser

    def _tree_sitter_to_dict(self, node, error_count: int = 0) -> Dict[str, Any]:
        """Convert tree-sitter node to dictionary."""
        result = {
            "type": node.type,
            "start_point": node.start_point,
            "end_point": node.end_point,
            "start_byte": node.start_byte,
            "end_byte": node.end_byte,
            "has_errors": error_count > 0 or node.type == "ERROR",
        }

        if node.child_count == 0:
            result["text"] = node.text.decode("utf8") if node.text else ""

        if node.child_count > 0:
            result["children"] = [
                self._tree_sitter_to_dict(child, error_count) for child in node.children
            ]

        return result

    def _parse_java_source_fallback(self, source_code: str) -> Optional[Dict]:
        """Fallback parsing for incomplete Java source code."""
        try:
            import_statements = re.findall(r"^import\s+([^;]+);", source_code, re.MULTILINE)

            class_pattern = (
                r"(?:public\s+|private\s+|protected\s+)?(?:static\s+)?(?:abstract\s+)?class\s+(\w+)"
            )
            class_matches = re.findall(class_pattern, source_code)

            annotation_pattern = r"@(\w+)(?:\(([^)]*)\))?"
            annotation_matches = re.findall(annotation_pattern, source_code)
            annotations = []
            for ann_name, ann_value in annotation_matches:
                if ann_value:
                    ann_value = ann_value.strip('"')
                annotations.append(
                    {"Name": ann_name, "value": ann_value, "type": "marker_annotation"}
                )

            class FakeAST:
                def __init__(self):
                    self.imports = []
                    for imp in import_statements:

                        class FakeImport:
                            def __init__(self, path):
                                self.path = path

                        self.imports.append(FakeImport(imp))
                    self.classes = class_matches
                    self.annotations = annotations

                def __iter__(self):
                    for class_name in self.classes:

                        class FakeClassNode:
                            def __init__(self, name):
                                self.name = name
                                self.methods = []
                                self.qualifier = ""
                                self.annotations = []

                        yield [], FakeClassNode(class_name)

            return FakeAST()
        except Exception as e:
            logger.warning(f"Fallback parsing also failed: {e}")
            return None

    def _extract_string_from_node(self, node: Dict) -> Optional[str]:
        """Extract string value from an AST node."""
        if node.get("type") == "string_literal":
            text = node.get("text", "").strip('"')
            if text:
                return text
            for child in node.get("children", []):
                if child.get("type") == "string_fragment":
                    return child.get("text", "").strip('"')
        return None

    def _find_nodes_by_type(self, node: Dict, target_type: str) -> List[Dict]:
        """Find all nodes of a specific type in tree-sitter AST."""
        results = []
        if not isinstance(node, dict):
            return results

        if node.get("type") == target_type:
            results.append(node)

        for child in node.get("children", []):
            results.extend(self._find_nodes_by_type(child, target_type))

        return results

    def _collect_identifiers(self, node: Dict, parts: List):
        """Recursively collect identifiers from field_access nodes."""
        for child in node.get("children", []):
            if child.get("type") == "identifier":
                parts.append(child.get("text", ""))
            elif child.get("type") == "field_access":
                self._collect_identifiers(child, parts)

    def _get_ts_method_name(self, inv_node: Dict) -> str:
        """Get method name from method_invocation node."""
        identifiers = []
        for child in inv_node.get("children", []):
            if child.get("type") == "identifier":
                identifiers.append(child.get("text", ""))
        if identifiers:
            return identifiers[-1]
        return ""

    def _get_ts_qualifier(self, node: Dict) -> str:
        """Get qualifier from field_access or method_invocation."""
        identifiers = []
        for child in node.get("children", []):
            if child.get("type") == "identifier":
                identifiers.append(child.get("text", ""))
        if len(identifiers) >= 2:
            return identifiers[0]
        return ""

    def _get_ts_member(self, node: Dict) -> str:
        """Get member name from field_access node."""
        for child in node.get("children", []):
            if child.get("type") == "identifier":
                return child.get("text", "")
        return ""

    def _extract_numeric_arg(self, arg_node: Dict) -> float:
        """Extract numeric value from an argument node."""
        if arg_node.get("type") == "decimal_integer_literal":
            try:
                return float(arg_node.get("text", "0").rstrip("LlFf"))
            except ValueError:
                pass
        elif arg_node.get("type") == "decimal_floating_point_literal":
            try:
                text = arg_node.get("text", "0")
                return float(text.rstrip("Ff"))
            except ValueError:
                pass
        return 1.0

    def _extract_string_content(self, string_node: Dict) -> str:
        """Extract string content from string_literal node."""
        if string_node.get("text"):
            return string_node.get("text", "").strip('"')
        for child in string_node.get("children", []):
            if child.get("type") == "string_fragment":
                return child.get("text", "").strip('"')
        return ""

    def _get_scoped_identifier_parts(self, node: Dict) -> List[str]:
        """Get parts from scoped_identifier."""
        parts = []
        for child in node.get("children", []):
            if child.get("type") == "identifier":
                parts.append(child.get("text", ""))
            elif child.get("type") == "scoped_identifier":
                parts.extend(self._get_scoped_identifier_parts(child))
        return parts
