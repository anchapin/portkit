"""Tree-sitter Java AST analysis.

Split out from ``translator.py`` per Issue #1746. Provides Java source analysis
via tree-sitter, producing structured AST dictionaries and natural-language
summaries that feed downstream translation.

The :class:`ASTAnalyzerMixin` is composed into :class:`LogicTranslatorAgent`.
"""

from typing import Any, Dict

try:
    import tree_sitter_java as ts_java
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    ts_java = None
    Parser = None

from utils.logging_config import get_agent_logger

logger = get_agent_logger("logic_translator")


class ASTAnalyzerMixin:
    """Tree-sitter Java AST analysis methods for the LogicTranslatorAgent."""

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

    def analyze_java_code_ast(self, java_code: str):
        """Analyze Java code and return AST using tree-sitter."""
        if not TREE_SITTER_AVAILABLE:
            logger.warning(
                "Tree-sitter not available, javalang fallback not supported in migrated code"
            )
            return {
                "success": False,
                "error": "tree-sitter not available",
                "ast_tree": None,
            }

        parser = self._get_tree_sitter_parser()
        if parser is None:
            return {
                "success": False,
                "error": "tree-sitter parser not available",
                "ast_tree": None,
            }

        try:
            tree = parser.parse(bytes(java_code, "utf8"))
            ast_dict = self._tree_sitter_to_dict(tree.root_node)
            return {
                "success": True,
                "ast_tree": ast_dict,
                "root_type": tree.root_node.type,
            }
        except Exception as e:
            logger.error(f"Error analyzing Java code AST: {e}")
            return {
                "success": False,
                "error": str(e),
                "ast_tree": None,
            }

    def _serialize_ast_for_llm(self, ast_dict: Dict[str, Any], max_depth: int = 10) -> str:
        """Serialize AST dictionary for LLM consumption."""
        if ast_dict is None:
            return "No AST available"

        lines = []
        indent = "  "

        def serialize_node(node: Dict[str, Any], depth: int = 0):
            if depth >= max_depth:
                lines.append(f"{indent * depth}...")
                return

            node_type = node.get("type", "unknown")
            has_errors = node.get("has_errors", False)

            prefix = "[ERROR] " if has_errors else ""
            lines.append(f"{indent * depth}{prefix}{node_type}")

            if "text" in node:
                text = node["text"]
                if text.strip():
                    lines.append(f"{indent * (depth + 1)}text: {repr(text)}")

            if "children" in node:
                for child in node["children"]:
                    serialize_node(child, depth + 1)

        serialize_node(ast_dict, 0)
        return "\n".join(lines)

    def generate_nl_summary_from_ast(self, java_code: str) -> str:
        """Generate natural language summary from Java AST using tree-sitter."""
        try:
            result = self.analyze_java_code_ast(java_code)

            if not result.get("success"):
                return f"Could not analyze code: {result.get('error', 'Unknown error')}"

            ast_dict = result.get("ast_tree")
            if not ast_dict:
                return "No AST found in analysis result"

            self._serialize_ast_for_llm(ast_dict)

            class_decl = None
            method_sigs = []

            def find_decls(node: Dict[str, Any]):
                nonlocal class_decl
                if node.get("type") == "class_declaration":
                    nonlocal class_decl
                    class_decl = node
                elif node.get("type") == "method_declaration":
                    method_sigs.append(node)

            def walk(node: Dict[str, Any]):
                find_decls(node)
                for child in node.get("children", []):
                    walk(child)

            walk(ast_dict)

            summary_parts = []
            if class_decl:
                class_name = "UnknownClass"
                for child in class_decl.get("children", []):
                    if child.get("type") == "identifier":
                        class_name = child.get("text", "UnknownClass")
                        break
                summary_parts.append(f"Class: {class_name}")

            if method_sigs:
                summary_parts.append(f"Contains {len(method_sigs)} method(s)")

            return "; ".join(summary_parts) if summary_parts else "Empty class"

        except Exception as e:
            logger.error(f"Error generating NL summary from AST: {e}")
            return f"Error: {str(e)}"
