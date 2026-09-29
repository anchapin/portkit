"""Mod metadata / dependency / reflection analysis (mixin)."""

from __future__ import annotations

from typing import Dict, List
from ._constants import logger


class MetadataAnalysisMixin:
    """Metadata, dependency & reflection analysis."""

    def extract_mod_metadata_from_ast(self, tree: Dict) -> Dict:
        """Extract mod metadata from parsed Java AST."""
        metadata = {}
        annotations_found = []

        try:
            if hasattr(tree, "annotations"):
                for ann in tree.annotations:
                    annotation_data = {
                        "name": ann.get("name", ""),
                        "type": ann.get("type", "marker_annotation"),
                        "value": ann.get("value"),
                    }
                    annotations_found.append(annotation_data)

                    ann_name = annotation_data.get("name", "")

                    if ann_name in ["Mod", "ModInstance", "ModEventBusSubscriber"]:
                        value = annotation_data.get("value")
                        if value:
                            metadata["value"] = value
                        if ann_name in ["SubscribeEvent", "Mod.EventBusSubscriber"]:
                            metadata["event_subscriber"] = True
                    elif ann_name == "ObjectHolder":
                        if annotation_data.get("value"):
                            metadata["object_holder"] = annotation_data["value"]
            else:
                all_annotations = self._find_nodes_by_type(tree, "annotation")
                marker_annotations = self._find_nodes_by_type(tree, "marker_annotation")
                all_annotations.extend(marker_annotations)

                for ann_node in all_annotations:
                    annotation_data = self._extract_annotation_data_ts(ann_node)
                    annotations_found.append(annotation_data)

                    ann_name = annotation_data.get("name", "")

                    if ann_name in ["Mod", "ModInstance", "ModEventBusSubscriber"]:
                        value = annotation_data.get("value")
                        if value:
                            metadata["value"] = value
                        if ann_name in ["SubscribeEvent", "Mod.EventBusSubscriber"]:
                            metadata["event_subscriber"] = True
                    elif ann_name == "ObjectHolder":
                        if annotation_data.get("value"):
                            metadata["object_holder"] = annotation_data["value"]

            if annotations_found:
                metadata["all_annotations"] = annotations_found

            return metadata
        except Exception as e:
            logger.warning(f"Error extracting metadata from AST: {e}")
            return metadata

    def analyze_dependencies_from_ast(self, tree: Dict) -> List[Dict]:
        """Analyze dependencies from parsed Java AST."""
        dependencies = []
        reflection_uses = []

        try:
            if hasattr(tree, "imports"):
                for imp in tree.imports:
                    if hasattr(imp, "path"):
                        dependencies.append({"import": imp.path, "type": "explicit"})
            else:
                imports = self._find_nodes_by_type(tree, "import_declaration")
                for imp in imports:
                    import_path = self._get_import_path(imp)
                    if import_path:
                        dependencies.append({"import": import_path, "type": "explicit"})

                method_invocations = self._find_nodes_by_type(tree, "method_invocation")
                for inv in method_invocations:
                    method_name = self._get_ts_method_name(inv)
                    qualifier = self._get_ts_qualifier(inv)

                    if qualifier:
                        dependencies.append(
                            {
                                "import": qualifier,
                                "type": "implicit",
                                "method": method_name,
                            }
                        )

                    method_lower = method_name.lower()
                    if method_lower in [
                        "class_forname",
                        "class",
                        "getmethod",
                        "getfield",
                        "getdeclaredmethod",
                        "getdeclaredfield",
                        "newinstance",
                        "invoke",
                        "setaccessible",
                        "getclass",
                    ]:
                        reflection_uses.append(
                            {
                                "type": "reflection",
                                "method": method_lower,
                                "qualifier": qualifier,
                            }
                        )

                if reflection_uses:
                    dependencies.extend(reflection_uses)

            return dependencies
        except Exception as e:
            logger.warning(f"Error analyzing dependencies from AST: {e}")
            return dependencies

    def detect_reflection_in_mods(self, tree: Dict) -> Dict:
        """Detect reflection usage in mods through static analysis."""
        reflection_info = {
            "detected": False,
            "class_forname": [],
            "method_reflection": [],
            "field_reflection": [],
            "warnings": [],
        }

        try:
            method_invocations = self._find_nodes_by_type(tree, "method_invocation")
            for inv in method_invocations:
                method_name = self._get_ts_method_name(inv).lower()
                qualifier = self._get_ts_qualifier(inv)

                if method_name == "forname" and qualifier.lower() == "class":
                    reflection_info["detected"] = True
                    args = self._get_method_arguments(inv)
                    if args:
                        class_name = self._extract_string_from_node(args[0])
                        if class_name:
                            reflection_info["class_forname"].append(class_name)

                elif method_name in ["getmethod", "getdeclaredmethod"]:
                    reflection_info["detected"] = True
                    reflection_info["method_reflection"].append(
                        {
                            "method": method_name,
                            "qualifier": qualifier,
                        }
                    )

                elif method_name in ["getfield", "getdeclaredfield"]:
                    reflection_info["detected"] = True
                    reflection_info["field_reflection"].append(
                        {
                            "method": method_name,
                            "qualifier": qualifier,
                        }
                    )

                elif method_name == "setaccessible":
                    reflection_info["detected"] = True

            if reflection_info["detected"]:
                logger.debug(
                    f"Reflection detected in mod: {len(reflection_info['class_forname'])} Class.forName, "
                    f"{len(reflection_info['method_reflection'])} method reflections"
                )

            return reflection_info
        except Exception as e:
            logger.warning(f"Error detecting reflection: {e}")
            return reflection_info

    def _get_import_path(self, imp_node: Dict) -> str:
        """Get import path from import_declaration node."""
        parts = []
        for child in imp_node.get("children", []):
            if child.get("type") == "scoped_identifier":
                parts = self._get_scoped_identifier_parts(child)
        return ".".join(parts)
