"""
AST-based and bytecode-based feature extraction for Java mods
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer.feature_extractor")

try:
    import tree_sitter_java as ts_java
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    ts_java = None
    Parser = None

try:
    import javassist

    JAVASSIST_AVAILABLE = True
except ImportError:
    javassist = None
    JAVASSIST_AVAILABLE = False


FEATURE_ANALYSIS_FILE_LIMIT = 10
METADATA_AST_FILE_LIMIT = 5
DEPENDENCY_ANALYSIS_FILE_LIMIT = 10
GOAL_SELECTOR_PATTERNS = (
    "goalSelector.addGoal",
    "goalSelector.add",
    "targetSelector.addGoal",
    "targetSelector.add",
)


class FeatureExtractor:
    """Extracts mod features from Java AST and bytecode"""

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

    def _get_method_arguments(self, inv_node: Dict) -> List:
        """Extract arguments from method_invocation node."""
        args = []
        for child in inv_node.get("children", []):
            if child.get("type") == "argument_list":
                for arg in child.get("children", []):
                    if arg.get("type") not in ["(", ")", ","]:
                        args.append(arg)
        return args

    def _extract_sound_type(self, arg_node: Dict) -> str:
        """Extract sound type from method argument."""
        if arg_node.get("type") == "field_access":
            parts = []
            self._collect_identifiers(arg_node, parts)
            if len(parts) >= 2:
                return parts[-1].lower()
        return "stone"

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

    def _extract_string_content(self, string_node: Dict) -> str:
        """Extract string content from string_literal node."""
        if string_node.get("text"):
            return string_node.get("text", "").strip('"')
        for child in string_node.get("children", []):
            if child.get("type") == "string_fragment":
                return child.get("text", "").strip('"')
        return ""

    def _get_import_path(self, imp_node: Dict) -> str:
        """Get import path from import_declaration node."""
        parts = []
        for child in imp_node.get("children", []):
            if child.get("type") == "scoped_identifier":
                parts = self._get_scoped_identifier_parts(child)
        return ".".join(parts)

    def _get_scoped_identifier_parts(self, node: Dict) -> List[str]:
        """Get parts from scoped_identifier."""
        parts = []
        for child in node.get("children", []):
            if child.get("type") == "identifier":
                parts.append(child.get("text", ""))
            elif child.get("type") == "scoped_identifier":
                parts.extend(self._get_scoped_identifier_parts(child))
        return parts


def _class_name_to_registry_name(class_name: str) -> str:
    """Convert Java class name to registry name format."""
    name = class_name
    if name.endswith("Block") and len(name) > 5:
        name = name[:-5]
    elif name.startswith("Block") and len(name) > 5 and name[5].isupper():
        name = name[5:]

    name = _snake_case(name)

    if not name:
        return "unknown"
    return name


def _snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re

    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    return name
