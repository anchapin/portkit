"""
AST-based and bytecode-based feature extraction for Java mods.

Public ``FeatureExtractor`` composes focused mixins so the original
monolithic class is split across:
  * ``_parsing_mixin``         — tree-sitter parse + AST text helpers
  * ``_goal_extraction_mixin`` — entity/goal selector extraction
  * ``_analysis_mixin``        — metadata/dependency/reflection analysis
while the core feature-extraction methods remain here. All public names
(``FeatureExtractor``, the availability flags and the registry helpers)
are re-exported for backwards compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from ._helpers import _class_name_to_registry_name, _snake_case  # noqa: F401
from ._parsing_mixin import SourceParsingMixin
from ._goal_extraction_mixin import GoalExtractionMixin
from ._analysis_mixin import MetadataAnalysisMixin

# Backwards-compatibility re-exports. The tree-sitter / javassist handles and
# availability flags historically lived in this module's namespace (some tests
# and callers reach for them via ``agents.java_analyzer.feature_extractor.X``),
# so they are re-exported here from their new home in ``._constants``.
from ._constants import (  # noqa: F401
    DEPENDENCY_ANALYSIS_FILE_LIMIT,
    FEATURE_ANALYSIS_FILE_LIMIT,
    JAVASSIST_AVAILABLE,
    Language,
    METADATA_AST_FILE_LIMIT,
    Parser,
    TREE_SITTER_AVAILABLE,
    javassist,
    logger,
    ts_java,
)


class FeatureExtractor(
    SourceParsingMixin,
    GoalExtractionMixin,
    MetadataAnalysisMixin,
):
    """Extracts mod features from Java AST and bytecode.

    Composes :class:`SourceParsingMixin`, :class:`GoalExtractionMixin`
    and :class:`MetadataAnalysisMixin`; the core feature-extraction
    methods live directly on this facade.
    """

    def __init__(self, feature_patterns: Dict[str, List[str]]):
        self.feature_patterns = feature_patterns
        self._ts_parser = None

    def extract_features_from_ast(self, tree: Dict) -> Dict:
        """Extract features from parsed Java AST (tree-sitter format)."""
        features = {
            "blocks": [],
            "items": [],
            "entities": [],
            "recipes": [],
            "dimensions": [],
            "gui": [],
            "machinery": [],
            "commands": [],
            "events": [],
            "tile_entities": [],
        }

        try:
            classes = self._find_nodes_by_type(tree, "class_declaration")

            for class_node in classes:
                class_info = self._extract_class_info_from_ts(class_node)
                class_name = class_info.get("name", "")
                superclass = class_info.get("superclass", "")

                is_block_entity = "BlockEntity" in superclass

                if is_block_entity:
                    tile_info = {
                        "name": class_name,
                        "registry_name": _class_name_to_registry_name(class_name),
                        "methods": class_info.get("methods", []),
                    }
                    features["tile_entities"].append(tile_info)
                    logger.debug(f"Extracted tile_entity: {class_name}")
                elif "Block" in class_name and not class_name.startswith("Abstract"):
                    block_info = {
                        "name": class_name,
                        "registry_name": _class_name_to_registry_name(class_name),
                        "methods": class_info.get("methods", []),
                        "properties": self._extract_block_properties_from_ts(class_node),
                    }
                    features["blocks"].append(block_info)
                elif "Item" in class_name and not class_name.startswith("Abstract"):
                    features["items"].append(
                        {
                            "name": class_name,
                            "registry_name": _class_name_to_registry_name(class_name),
                            "methods": class_info.get("methods", []),
                        }
                    )
                elif "Entity" in class_name and not class_name.startswith("Abstract"):
                    entity_info = {
                        "name": class_name,
                        "registry_name": _class_name_to_registry_name(class_name),
                        "methods": class_info.get("methods", []),
                    }
                    goals = self.extract_entity_goals_from_ast(class_node)
                    if goals:
                        entity_info["goals"] = goals
                    features["entities"].append(entity_info)

            method_declarations = self._find_nodes_by_type(tree, "method_declaration")
            for method_node in method_declarations:
                method_name = self._get_method_name(method_node)

                if any(keyword in method_name.lower() for keyword in ["recipe", "craft", "smelt"]):
                    features["recipes"].append(
                        {
                            "name": method_name,
                            "parameters": self._get_method_parameters(method_node),
                        }
                    )

                if any(keyword in method_name.lower() for keyword in ["command", "execute"]):
                    features["commands"].append(
                        {
                            "name": method_name,
                            "parameters": self._get_method_parameters(method_node),
                        }
                    )

                if any(
                    keyword in method_name.lower() for keyword in ["event", "trigger", "handle"]
                ):
                    features["events"].append(
                        {
                            "name": method_name,
                            "parameters": self._get_method_parameters(method_node),
                        }
                    )

            return features
        except Exception as e:
            logger.warning(f"Error extracting features from AST: {e}")
            return features

    def extract_features_from_bytecode(self, class_info: Dict) -> Dict:
        """Extract mod features from bytecode-analyzed class information."""
        features = {
            "type": "unknown",
            "name": class_info.get("simple_name", class_info.get("name", "Unknown")),
            "registry_name": _class_name_to_registry_name(
                class_info.get("simple_name", class_info.get("name", "Unknown"))
            ),
            "methods": [],
            "properties": {},
        }

        try:
            name = class_info.get("simple_name", class_info.get("name", ""))
            superclass = class_info.get("superclass", "")
            interfaces = class_info.get("interfaces", [])

            if "TileEntity" in name or "BlockEntity" in superclass:
                features["type"] = "tile_entity"
            elif "Block" in name or "Block" in superclass:
                features["type"] = "block"
                features["properties"] = self._extract_block_properties_from_bytecode(class_info)
            elif "Item" in name or "Item" in superclass:
                features["type"] = "item"
            elif "Entity" in name or "Entity" in superclass or "Entity" in interfaces:
                features["type"] = "entity"

            methods = class_info.get("methods", [])
            features["methods"] = [m.get("name", "") for m in methods]

            return features

        except Exception as e:
            logger.warning(f"Error extracting features from bytecode: {e}")
            return features

    def extract_features_from_class_name(self, class_name: str) -> Dict:
        """Extract features from a single class name (fallback for parse failures)."""
        features = {
            "blocks": [],
            "items": [],
            "entities": [],
            "recipes": [],
            "dimensions": [],
            "gui": [],
            "machinery": [],
            "commands": [],
            "events": [],
        }

        try:
            for feature_type, patterns in self.feature_patterns.items():
                for pattern in patterns:
                    if pattern.lower() in class_name.lower():
                        feature_entry = {
                            "name": class_name,
                            "registry_name": _class_name_to_registry_name(class_name),
                        }
                        features[feature_type].append(feature_entry)
                        break

            return features
        except Exception as e:
            logger.warning(f"Error extracting features from class name {class_name}: {e}")
            return features

    def extract_features_from_classes(self, file_list: List[str]) -> Dict:
        """Extract features from class file names (fallback method)."""
        features = {
            "blocks": [],
            "items": [],
            "entities": [],
            "recipes": [],
            "dimensions": [],
            "gui": [],
            "machinery": [],
            "commands": [],
            "events": [],
        }

        try:
            for file_path in file_list:
                if file_path.endswith(".class"):
                    class_name = Path(file_path).stem
                    for feature_type, patterns in self.feature_patterns.items():
                        for pattern in patterns:
                            if pattern.lower() in class_name.lower():
                                feature_entry = {
                                    "name": class_name,
                                    "registry_name": _class_name_to_registry_name(class_name),
                                }
                                features[feature_type].append(feature_entry)
                                break

            return features
        except Exception as e:
            logger.warning(f"Error extracting features from classes: {e}")
            return features

    def analyze_bytecode_class(self, class_data: bytes, class_name: str) -> Dict:
        """Analyze a Java class file using Javassist."""
        if not JAVASSIST_AVAILABLE or javassist is None:
            return {"error": "javassist not available"}

        class_info = {
            "name": class_name,
            "superclass": None,
            "interfaces": [],
            "fields": [],
            "methods": [],
            "annotations": [],
            "source": "bytecode",
        }

        try:
            cp = javassist.ClassPool()
            cp.appendSystemPath()
            ct_class = cp.make_class(javassist.bytecode.ConstPool(bytearray(class_data)))

            simple_name = class_name.split(".")[-1]
            class_info["simple_name"] = simple_name

            if ct_class.getSuperclass():
                class_info["superclass"] = ct_class.getSuperclass().getName()

            for interface in ct_class.getInterfaces():
                class_info["interfaces"].append(interface.getName())

            for field in ct_class.getFields():
                field_info = {
                    "name": field.getName(),
                    "type": field.getType().getName() if field.getType() else "unknown",
                }
                class_info["fields"].append(field_info)

            for method in ct_class.getMethods():
                method_info = {"name": method.getName(), "signature": method.getSignature()}
                class_info["methods"].append(method_info)

            try:
                RuntimeVisibleAnnotations = ct_class.getAnnotation("Ljava/lang/Deprecated;")
                if RuntimeVisibleAnnotations:
                    class_info["annotations"] = [str(a) for a in RuntimeVisibleAnnotations]
            except Exception:
                pass

            return class_info

        except Exception as e:
            logger.warning(f"Failed to analyze bytecode for {class_name}: {e}")
            return {"error": str(e), "name": class_name}

    def analyze_classes_with_bytecode(self, jar, file_list: List[str]) -> Dict:
        """Analyze .class files in a JAR using bytecode analysis."""
        features = {
            "blocks": [],
            "items": [],
            "entities": [],
            "recipes": [],
            "tile_entities": [],
            "other": [],
        }

        class_files = [f for f in file_list if f.endswith(".class")]

        if not class_files:
            logger.info("No .class files found for bytecode analysis")
            return features

        max_classes = 50
        analyzed_count = 0

        for class_file in class_files[:max_classes]:
            try:
                class_data = jar.read(class_file)
                class_name = class_file.replace("/", ".").replace(".class", "")

                class_info = self.analyze_bytecode_class(class_data, class_name)

                if "error" not in class_info:
                    class_features = self.extract_features_from_bytecode(class_info)

                    if class_features["type"] == "block":
                        features["blocks"].append(class_features)
                    elif class_features["type"] == "item":
                        features["items"].append(class_features)
                    elif class_features["type"] == "entity":
                        features["entities"].append(class_features)
                    elif class_features["type"] == "tile_entity":
                        features["tile_entities"].append(class_features)
                    else:
                        features["other"].append(class_features)

                    analyzed_count += 1

            except Exception as e:
                logger.debug(f"Could not analyze class {class_file}: {e}")
                continue

        return features

    def _extract_class_info_from_ts(self, class_node: Dict) -> Dict:
        """Extract class information from tree-sitter class_declaration node."""
        class_info = {"name": "", "superclass": "", "methods": [], "modifiers": []}

        for child in class_node.get("children", []):
            child_type = child.get("type")
            if child_type == "identifier":
                class_info["name"] = child.get("text", "")
            elif child_type == "modifiers":
                class_info["modifiers"] = self._extract_modifiers(child)
            elif child_type == "superclass":
                class_info["superclass"] = self._get_superclass_text(child)

        block_body = self._find_nodes_by_type(class_node, "class_body")
        if block_body:
            method_nodes = self._find_nodes_by_type(block_body[0], "method_declaration")
            class_info["methods"] = [self._get_method_name(m) for m in method_nodes]

        return class_info

    def _get_superclass_text(self, superclass_node: Dict) -> str:
        """Get superclass name from superclass node."""
        text_parts = []
        for child in superclass_node.get("children", []):
            if child.get("type") == "type_identifier":
                text_parts.append(child.get("text", ""))
            elif child.get("type") == "identifier":
                text_parts.append(child.get("text", ""))
        return ".".join(text_parts)

    def _extract_modifiers(self, modifiers_node: Dict) -> List[str]:
        """Extract modifier keywords."""
        modifiers = []
        for child in modifiers_node.get("children", []):
            mod_text = child.get("text", "")
            if mod_text in ["public", "private", "protected", "static", "final", "abstract"]:
                modifiers.append(mod_text)
        return modifiers

    def _get_method_name(self, method_node: Dict) -> str:
        """Get method name from method_declaration node."""
        for child in method_node.get("children", []):
            if child.get("type") == "identifier":
                return child.get("text", "")
        return ""

    def _get_method_parameters(self, method_node: Dict) -> List[str]:
        """Get method parameters from method_declaration node."""
        params = []
        for child in method_node.get("children", []):
            if child.get("type") == "formal_parameters":
                param_list = self._find_nodes_by_type(child, "formal_parameter")
                for param in param_list:
                    for pchild in param.get("children", []):
                        if pchild.get("type") == "type_identifier":
                            params.append(pchild.get("text", ""))
        return params

    def _extract_block_properties_from_ts(self, class_node: Dict) -> Dict:
        """Extract block properties from tree-sitter block class node."""
        properties = {
            "material": "stone",
            "hardness": 1.0,
            "explosion_resistance": 0.0,
            "sound_type": "stone",
            "light_level": 0,
            "requires_tool": False,
        }

        try:
            method_invocations = self._find_nodes_by_type(class_node, "method_invocation")
            for inv in method_invocations:
                method_name = self._get_ts_method_name(inv).lower()
                args = self._get_method_arguments(inv)

                if method_name == "strength":
                    if len(args) >= 1:
                        properties["hardness"] = self._extract_numeric_arg(args[0])
                    if len(args) >= 2:
                        properties["explosion_resistance"] = self._extract_numeric_arg(args[1])
                elif method_name == "sound":
                    if args:
                        properties["sound_type"] = self._extract_sound_type(args[0])
                elif "requirescorrecttool" in method_name or "requires_tool" in method_name:
                    properties["requires_tool"] = True
                elif method_name in ["lightlevel", "luminance", "emitslight"]:
                    if args:
                        properties["light_level"] = self._extract_numeric_arg(args[0])

            member_accesses = self._find_nodes_by_type(class_node, "field_access")
            for access in member_accesses:
                qualifier = self._get_ts_qualifier(access)
                if qualifier == "Material":
                    member = self._get_ts_member(access)
                    if member:
                        properties["material"] = member.lower()

            return properties
        except Exception as e:
            logger.warning(f"Error extracting block properties from AST: {e}")
            return properties

    def _extract_block_properties_from_bytecode(self, class_info: Dict) -> Dict:
        """Extract block properties from bytecode-analyzed class."""
        properties = {
            "material": "stone",
            "hardness": 1.0,
            "explosion_resistance": 0.0,
            "sound_type": "stone",
            "light_level": 0,
            "requires_tool": False,
            "source": "bytecode_estimate",
        }

        try:
            name = class_info.get("simple_name", "").lower()
            methods = class_info.get("methods", [])
            fields = class_info.get("fields", [])

            if "wood" in name or "plank" in name:
                properties["material"] = "wood"
                properties["sound_type"] = "wood"
                properties["hardness"] = 2.0
            elif "stone" in name or "cobbl" in name:
                properties["material"] = "stone"
                properties["sound_type"] = "stone"
                properties["hardness"] = 1.5
            elif "metal" in name or "iron" in name or "gold" in name or "copper" in name:
                properties["material"] = "metal"
                properties["sound_type"] = "metal"
                properties["hardness"] = 5.0
                properties["explosion_resistance"] = 6.0
            elif "glass" in name:
                properties["material"] = "glass"
                properties["sound_type"] = "glass"
                properties["hardness"] = 0.3
            elif "dirt" in name or "grass" in name or "sand" in name:
                properties["material"] = "dirt"
                properties["sound_type"] = "gravel"
                properties["hardness"] = 0.5

            method_names = " ".join([m.get("name", "").lower() for m in methods])

            if "requiresCorrectTool" in method_names or "requires_tool" in method_names:
                properties["requires_tool"] = True

            if "emitsLight" in method_names or "luminance" in method_names:
                properties["light_level"] = 0

            for field in fields:
                field_name = field.get("name", "").lower()
                if "hardness" in field_name:
                    properties["hardness"] = 1.0
                if "resistance" in field_name:
                    properties["explosion_resistance"] = 3.0

            return properties

        except Exception as e:
            logger.warning(f"Error extracting block properties from bytecode: {e}")
            return properties

    def _extract_sound_type(self, arg_node: Dict) -> str:
        """Extract sound type from method argument."""
        if arg_node.get("type") == "field_access":
            parts = []
            self._collect_identifiers(arg_node, parts)
            if len(parts) >= 2:
                return parts[-1].lower()
        return "stone"

    def _extract_annotation_data_ts(self, ann_node: Dict) -> Dict:
        """Extract annotation data from tree-sitter annotation node."""
        annotation_info = {"name": "", "type": "unknown", "value": None}

        try:
            for child in ann_node.get("children", []):
                child_type = child.get("type")
                if child_type == "identifier":
                    annotation_info["name"] = child.get("text", "")
                elif child_type == "element_value_pair":
                    key = ""
                    value = ""
                    for pair_child in child.get("children", []):
                        if pair_child.get("type") == "identifier":
                            key = pair_child.get("text", "")
                        elif pair_child.get("type") == "string_literal":
                            value = self._extract_string_content(pair_child)
                    if key:
                        annotation_info[key] = value
                elif child_type == "annotation_argument_list":
                    for arg_child in child.get("children", []):
                        if arg_child.get("type") == "string_literal":
                            annotation_info["value"] = self._extract_string_content(arg_child)
                            break
                elif child_type == "string_literal":
                    annotation_info["value"] = self._extract_string_content(child)

            name_lower = annotation_info["name"].lower()
            if name_lower in ["mod", "modinstance", "modid"]:
                annotation_info["type"] = "mod_id"
            elif "eventbus" in name_lower or "subscribe" in name_lower:
                annotation_info["type"] = "event_subscriber"
            elif "objectholder" in name_lower:
                annotation_info["type"] = "object_holder"
            elif "inject" in name_lower or "mixin" in name_lower:
                annotation_info["type"] = "mixin"

            return annotation_info
        except Exception as e:
            logger.debug(f"Error extracting annotation data: {e}")
            return annotation_info
