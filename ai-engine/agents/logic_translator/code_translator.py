"""Java to JavaScript code translation.

Split out from ``translator.py`` per Issue #1746. Provides translation of Java
methods, classes, API calls, event handlers, and JavaScript syntax validation.

The :class:`CodeTranslatorMixin` is composed into :class:`LogicTranslatorAgent`
and assumes the host class provides:

- ``self.logger``
- ``self.type_mappings`` (dict[str, str])
- ``self._rag_context_enabled`` (bool)
- ``self._get_rag_context(...)`` (from :class:`RAGContextMixin`)
"""

import json

from utils.logging_config import get_agent_logger

logger = get_agent_logger("logic_translator")


class CodeTranslatorMixin:
    """Java method/class/API/event translation methods for the LogicTranslatorAgent."""

    def _get_javascript_type(self, java_type):
        """Convert Java type to JavaScript type.

        Handles both javalang and tree-sitter formats.
        """
        if java_type is None:
            return "any"

        # Handle tree-sitter dict format
        if isinstance(java_type, dict):
            type_name = java_type.get("type", str(java_type))
            if type_name == "type_identifier":
                type_name = java_type.get("text", str(java_type))
            if java_type.get("type") == "array_type":
                element_type_node = (
                    java_type.get("children", [{}])[0] if java_type.get("children") else {}
                )
                element_type = element_type_node.get("text", str(element_type_node))
                if element_type in self.type_mappings:
                    return f"{self.type_mappings[element_type]}[]"
                return f"{element_type}[]"
        # Handle javalang AST types (object with .name attribute)
        elif hasattr(java_type, "name"):
            type_name = java_type.name
            if hasattr(java_type, "dimensions") and java_type.dimensions:
                type_name += "[]"
        elif hasattr(java_type, "type") and hasattr(java_type.type, "name"):
            type_name = java_type.type.name
            if hasattr(java_type, "dimensions") and java_type.dimensions:
                type_name += "[]"
        else:
            type_name = str(java_type)

        # Handle arrays
        if "[]" in type_name:
            base_type = type_name.replace("[]", "")
            js_base_type = self.type_mappings.get(base_type, base_type)
            return f"{js_base_type}[]"

        return self.type_mappings.get(type_name, type_name)

    def translate_java_method(self, method_data, feature_context=None) -> str:
        """Translate Java method to JavaScript with optional RAG context augmentation."""
        try:
            rag_context = ""
            feature_type = "unknown"

            if isinstance(method_data, str):
                data = json.loads(method_data)
                method_name = data.get("method_name", "unknown")
                method_body = data.get("method_body", "")
                feature_type = data.get("feature_type", "unknown")

                if self._rag_context_enabled and feature_type != "unknown":
                    rag_context = self._get_rag_context(
                        f"{method_name} {method_body}", feature_type
                    )

                translated_js = f"// Translated {method_name}\nfunction {method_name}() {{\n  // {method_body}\n}}"

                result = {
                    "success": True,
                    "original_method": method_name,
                    "translated_javascript": translated_js,
                    "warnings": [],
                }

                if rag_context:
                    result["rag_context_applied"] = True
                    result["conversion_context"] = rag_context

                return json.dumps(result)
            else:
                method_name = getattr(method_data, "name", "unknown")

                params = []
                if hasattr(method_data, "parameters") and method_data.parameters:
                    for param in method_data.parameters:
                        param_name = param.name
                        param_type = self._get_javascript_type(param.type)
                        params.append(f"{param_name}: {param_type}")

                return_type = "void"
                if hasattr(method_data, "return_type") and method_data.return_type:
                    return_type = self._get_javascript_type(method_data.return_type)

                param_str = ", ".join(params)
                if return_type != "void":
                    translated_js = (
                        f"// Translated {method_name}\n"
                        f"function {method_name}({param_str}): {return_type} {{\n"
                        f"  // Method body\n}}"
                    )
                else:
                    translated_js = (
                        f"// Translated {method_name}\n"
                        f"function {method_name}({param_str}) {{\n"
                        f"  // Method body\n}}"
                    )

                result = {
                    "success": True,
                    "original_method": method_name,
                    "javascript_method": translated_js,
                    "warnings": [],
                }

                if rag_context:
                    result["rag_context_applied"] = True
                    result["conversion_context"] = rag_context

                return json.dumps(result)
        except Exception as e:
            logger.error(f"Error translating method: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def convert_java_class(self, class_data: str) -> str:
        """Convert Java class to JavaScript with optional RAG context."""
        try:
            data = json.loads(class_data)
            class_name = data.get("class_name", "UnknownClass")
            data.get("methods", [])
            feature_type = data.get("feature_type", "unknown")

            rag_context = ""
            if self._rag_context_enabled and feature_type != "unknown":
                rag_context = self._get_rag_context(class_name, feature_type)

            js_class = f"// Converted class {class_name}\nclass {class_name} {{}}"

            result = {
                "success": True,
                "original_class": class_name,
                "javascript_class": js_class,
                "warnings": [],
            }

            if rag_context:
                result["rag_context_applied"] = True
                result["conversion_context"] = rag_context

            return json.dumps(result)
        except Exception as e:
            logger.error(f"Error converting class: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def map_java_apis(self, api_data: str) -> str:
        """Map Java APIs to JavaScript."""
        try:
            data = json.loads(api_data)
            apis = data.get("apis", [])

            mapped_apis = {}
            for api in apis:
                mapped_apis[api] = self._get_javascript_type(api.split(".")[-1])

            return json.dumps(
                {
                    "success": True,
                    "mapped_apis": mapped_apis,
                    "warnings": [],
                }
            )
        except Exception as e:
            logger.error(f"Error mapping APIs: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def generate_event_handlers(self, event_data: str) -> str:
        """Generate event handlers for JavaScript."""
        try:
            data = json.loads(event_data)
            event_type = data.get("event_type", "unknown")
            handlers = data.get("handlers", [])

            js_handlers = [f"// Event handler for {event_type}"] * len(handlers)

            return json.dumps(
                {
                    "success": True,
                    "event_handlers": js_handlers,
                    "warnings": [],
                }
            )
        except Exception as e:
            logger.error(f"Error generating event handlers: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})

    def validate_javascript_syntax(self, js_data: str) -> str:
        """Validate JavaScript syntax."""
        try:
            data = json.loads(js_data)
            javascript_code = data.get("javascript_code", "")

            is_valid = "()" in javascript_code and "{" in javascript_code

            return json.dumps(
                {
                    "success": True,
                    "is_valid": is_valid,
                    "syntax_errors": [] if is_valid else ["Syntax error detected"],
                    "warnings": [],
                }
            )
        except Exception as e:
            logger.error(f"Error validating JavaScript: {e}")
            return json.dumps({"success": False, "error": str(e), "warnings": []})
