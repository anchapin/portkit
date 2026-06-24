"""
Java Analyzer Agent for analyzing Java mod structure and extracting features.

This module provides the main JavaAnalyzerAgent class which combines functionality from:
- archive_reader: JAR/ZIP extraction
- framework_detector: Forge/Fabric/Quilt detection
- feature_extractor: AST-based feature extraction
- embedding_bridge: embedding generation
- llm_analyzer: LLM complexity analysis
- tools: LangChain/LangGraph @tool wrappers
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from agents.java_analyzer.archive_reader import (
    ArchiveReader,
)
from agents.java_analyzer.embedding_bridge import EmbeddingBridge
from agents.java_analyzer.feature_extractor import FeatureExtractor, _class_name_to_registry_name
from agents.java_analyzer.framework_detector import FrameworkDetector
from agents.java_analyzer.llm_analyzer import LLMAnalyzer
from agents.java_analyzer.tools import JavaAnalyzerTools
from models.smart_assumptions import SmartAssumptionEngine
from utils.embedding_generator import LocalEmbeddingGenerator
from utils.logging_config import get_agent_logger, log_performance

logger = get_agent_logger("java_analyzer")


from ._jar_analysis_mixin import JarAnalysisMixin


class JavaAnalyzerAgent(JarAnalysisMixin):
    """
    Java Analyzer Agent responsible for analyzing Java mod structure,
    dependencies, and features as specified in PRD Feature 2.
    """

    _instance = None

    analyze_mod_structure_tool = JavaAnalyzerTools.analyze_mod_structure_tool
    extract_mod_metadata_tool = JavaAnalyzerTools.extract_mod_metadata_tool
    identify_features_tool = JavaAnalyzerTools.identify_features_tool
    analyze_dependencies_tool = JavaAnalyzerTools.analyze_dependencies_tool
    extract_assets_tool = JavaAnalyzerTools.extract_assets_tool
    analyze_complexity_with_llm_tool = JavaAnalyzerTools.analyze_complexity_with_llm_tool

    def __init__(self):
        self.logger = logger
        self.smart_assumption_engine = SmartAssumptionEngine()
        self.embedding_generator = LocalEmbeddingGenerator()

        self.file_patterns = {
            "mod_files": [".jar", ".zip"],
            "source_files": [".java"],
            "config_files": [".json", ".toml", ".cfg"],
            "resource_files": [".png", ".jpg", ".ogg", ".wav", ".obj", ".mtl"],
            "metadata_files": ["mcmod.info", "fabric.mod.json", "quilt.mod.json", "mods.toml"],
        }

        self.framework_indicators = {
            "forge": ["net.minecraftforge", "cpw.mods", "@Mod", "ForgeModContainer"],
            "fabric": ["net.fabricmc", "FabricLoader", "fabric.mod.json"],
            "quilt": ["org.quiltmc", "QuiltLoader", "quilt.mod.json"],
            "bukkit": ["org.bukkit", "plugin.yml", "JavaPlugin"],
            "spigot": ["org.spigotmc", "SpigotAPI"],
            "paper": ["io.papermc", "PaperAPI"],
        }

        self.feature_patterns = {
            "blocks": ["Block", "BlockState", "registerBlock", "ModBlocks"],
            "items": ["Item", "ItemStack", "registerItem", "ModItems"],
            "entities": ["Entity", "EntityType", "registerEntity", "ModEntities"],
            "dimensions": ["Dimension", "World", "DimensionType", "createDimension"],
            "gui": ["GuiScreen", "ContainerScreen", "IGuiHandler", "MenuType"],
            "machinery": ["TileEntity", "BlockEntity", "IEnergyStorage", "IFluidHandler"],
            "recipes": ["IRecipe", "ShapedRecipe", "ShapelessRecipe", "registerRecipe"],
            "commands": ["Command", "ICommand", "CommandBase", "registerCommand"],
            "events": ["Event", "SubscribeEvent", "EventHandler", "Listener"],
        }

        self._archive_reader = ArchiveReader(self.feature_patterns)
        self._framework_detector = FrameworkDetector()
        self._feature_extractor = FeatureExtractor(self.feature_patterns)
        self._embedding_bridge = EmbeddingBridge(self.embedding_generator)
        self._llm_analyzer = LLMAnalyzer()

    @classmethod
    @classmethod
    def get_instance(cls):
        """Get singleton instance of JavaAnalyzerAgent"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self) -> List:
        """Get tools available to this agent"""
        return [
            JavaAnalyzerTools.analyze_mod_structure_tool,
            JavaAnalyzerTools.extract_mod_metadata_tool,
            JavaAnalyzerTools.identify_features_tool,
            JavaAnalyzerTools.analyze_dependencies_tool,
            JavaAnalyzerTools.extract_assets_tool,
            JavaAnalyzerTools.analyze_complexity_with_llm_tool,
        ]

    @log_performance("mod_file_analysis")
    @log_performance("mod_file_analysis")
    def analyze_mod_file(self, mod_path: str) -> str:
        """
        Analyze a mod file and return comprehensive results.

        Args:
            mod_path: Path to the mod file

        Returns:
            JSON string with analysis results
        """
        try:
            self.logger.log_operation_start(
                "mod_file_analysis", mod_path=mod_path, file_size=self._get_file_size(mod_path)
            )

            result = {
                "mod_info": {"name": "unknown", "framework": "unknown", "version": "1.0.0"},
                "assets": {},
                "features": {},
                "structure": {},
                "metadata": {},
                "errors": [],
                "embeddings_data": [],
            }

            self.logger.debug("Initialized analysis result structure")

            if mod_path.endswith((".jar", ".zip")):
                self.logger.info("Analyzing JAR/ZIP file", file_type="archive")
                ast_result = self.analyze_jar_with_ast(mod_path)
                if ast_result["success"]:
                    result["mod_info"].update(ast_result["mod_info"])
                    result["assets"] = ast_result["assets"]
                    result["features"] = ast_result["features"]
                    result["structure"] = {"files": ast_result.get("file_count", 0), "type": "jar"}
                    if ast_result.get("dependencies"):
                        result["dependencies"] = ast_result["dependencies"]
                    if ast_result.get("framework"):
                        result["mod_info"]["framework"] = ast_result["framework"]
                    result["errors"].extend(ast_result.get("errors", []))
                else:
                    self.logger.warning("AST analysis failed, falling back to original analysis")
                    result = self._analyze_jar_file(mod_path, result)
            elif os.path.isdir(mod_path):
                self.logger.info("Analyzing source directory", file_type="directory")
                result = self._analyze_source_directory(mod_path, result)
            else:
                error_msg = f"Unsupported mod file format: {mod_path}"
                self.logger.error(error_msg)
                result["errors"].append(error_msg)

            self.logger.info(
                "Analysis completed",
                mod_name=result["mod_info"]["name"],
                framework=result["mod_info"]["framework"],
                assets_count=len(result["assets"]),
                features_count=len(result["features"]),
                errors_count=len(result["errors"]),
            )

            self.logger.debug("Generating embeddings for analyzed content")
            embedding_start = time.time()
            self._embedding_bridge.generate_embeddings(result)
            embedding_duration = time.time() - embedding_start
            self.logger.log_tool_usage(
                "embedding_generator",
                result=f"Generated {len(result['embeddings_data'])} embeddings",
                duration=embedding_duration,
            )

            result_json = json.dumps(result)
            self.logger.debug("Analysis result serialized", result_size=len(result_json))
            return result_json

        except Exception as e:
            self.logger.error(
                f"Error analyzing mod file {mod_path}: {e}", error_type=type(e).__name__
            )
            error_result = {
                "mod_info": {"name": "error", "framework": "unknown", "version": "1.0.0"},
                "assets": {},
                "features": {},
                "structure": {},
                "metadata": {},
                "errors": [f"Analysis failed: {str(e)}"],
                "embeddings_data": [],
            }
            return json.dumps(error_result)

    def _find_nodes_by_type(self, node: Dict, target_type: str) -> List[Dict]:
        """Find all nodes of a specific type in tree-sitter AST."""
        return self._feature_extractor._find_nodes_by_type(node, target_type)

    def _extract_features_from_class_name(self, class_name: str) -> Dict:
        """Extract features from a single class name (fallback for parse failures)."""
        return self._feature_extractor.extract_features_from_class_name(class_name)

    def _analyze_bytecode_class(self, class_data: bytes, class_name: str) -> Dict:
        """Analyze a Java class file using Javassist."""
        return self._feature_extractor.analyze_bytecode_class(class_data, class_name)

    def _extract_features_from_ast(self, tree: Dict) -> Dict:
        """Extract features from parsed Java AST."""
        return self._feature_extractor.extract_features_from_ast(tree)

    def _extract_features_from_classes(self, file_list: List[str]) -> Dict:
        """Extract features from class file names (fallback method)."""
        return self._feature_extractor.extract_features_from_classes(file_list)

    def _analyze_dependencies_from_ast(self, tree: Dict) -> List[Dict]:
        """Analyze dependencies from parsed Java AST."""
        return self._feature_extractor.analyze_dependencies_from_ast(tree)

    def _detect_reflection_in_mods(self, tree: Dict) -> Dict:
        """Detect reflection usage in mods through static analysis."""
        return self._feature_extractor.detect_reflection_in_mods(tree)

    def _parse_java_source(self, source_code: str) -> Optional[Dict]:
        """Parse Java source code into an AST."""
        return self._feature_extractor.parse_java_source(source_code)

    def _parse_java_source_fallback(self, source_code: str) -> Optional[Dict]:
        """Fallback parsing that tries to handle partial/incomplete Java source code."""
        return self._feature_extractor._parse_java_source_fallback(source_code)

    def _extract_annotation_element(self, element) -> Optional[Any]:
        """Extract value from an annotation element (for fallback compatibility)."""
        if element is None:
            return None
        try:
            if hasattr(element, "value"):
                value = element.value
                if isinstance(value, str):
                    return value.strip('"')
                return value
            return str(element)
        except Exception:
            return None

    def _extract_block_properties_from_ast(self, class_node: Dict) -> Dict:
        """Extract block properties from tree-sitter block class node."""
        return self._feature_extractor._extract_block_properties_from_ts(class_node)

    def _extract_block_properties_from_ts(self, class_node: Dict) -> Dict:
        """Extract block properties from tree-sitter block class node."""
        return self._feature_extractor._extract_block_properties_from_ts(class_node)

    def _extract_annotation_data_ts(self, ann_node: Dict) -> Dict:
        """Extract annotation data from tree-sitter annotation node."""
        return self._feature_extractor._extract_annotation_data_ts(ann_node)

    def _extract_mod_metadata_from_ast(self, tree: Dict) -> Dict:
        """Extract mod metadata from parsed Java AST."""
        return self._feature_extractor.extract_mod_metadata_from_ast(tree)

    def _class_name_to_registry_name(self, class_name: str) -> str:
        """Convert Java class name to registry name format."""
        return _class_name_to_registry_name(class_name)


def _class_name_to_registry_name(class_name: str) -> str:
    """Convert Java class name to registry name format."""
    name = class_name
    if name.endswith("Block") and len(name) > 5:
        name = name[:-5]
    elif name.startswith("Block") and len(name) > 5 and name[5].isupper():
        name = name[5:]

    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        return "unknown"
    return name
