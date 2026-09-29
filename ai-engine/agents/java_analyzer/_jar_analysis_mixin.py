"""JAR / source / registry analysis (mixin for ``JavaAnalyzerAgent``)."""

from __future__ import annotations

import os
import time
import zipfile
from typing import Dict, List, Optional

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer")
from agents.java_semantic_chunker import ChunkManifest, JavaSemanticChunker
from agents.java_analyzer.archive_reader import (
    FEATURE_ANALYSIS_FILE_LIMIT,
    DEPENDENCY_ANALYSIS_FILE_LIMIT,
    METADATA_AST_FILE_LIMIT,
)


class JarAnalysisMixin:
    """JAR / source / registry / metadata extraction analysis."""

    def _get_file_size(self, file_path: str) -> int:
        """Get file size in bytes, return 0 if file doesn't exist or is directory"""
        try:
            if os.path.isfile(file_path):
                return os.path.getsize(file_path)
            elif os.path.isdir(file_path):
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(file_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                        except (OSError, IOError):
                            continue
                return total_size
            return 0
        except (OSError, IOError):
            return 0

    def generate_chunk_manifest(
        self,
        jar_path: str,
        mod_id: str = "",
        mod_name: str = "",
        loader: str = "",
        loader_version: str = "",
    ) -> ChunkManifest:
        """
        Produce a ChunkManifest for all Java sources in the given JAR.

        Args:
            jar_path: Path to the mod JAR file
            mod_id: Mod identifier
            mod_name: Human-readable mod name
            loader: Loader name
            loader_version: Loader + game version string

        Returns:
            ChunkManifest with ordered chunks and context headers
        """
        sources = self._archive_reader.read_java_sources_from_jar(jar_path)

        chunker = JavaSemanticChunker()
        manifest = chunker.build_manifest(
            sources,
            mod_id=mod_id,
            mod_name=mod_name,
            loader=loader,
            loader_version=loader_version,
        )
        logger.info(
            f"ChunkManifest generated: {manifest.total_chunks} chunks from {len(sources)} Java sources"
        )
        return manifest

    def _analyze_sources_batch(self, jar: zipfile.ZipFile, java_sources: List[str]) -> Dict:
        """
        Analyze Java sources in a single pass to extract features, dependencies, and metadata.
        """
        batch_result = {
            "features": {
                "blocks": [],
                "items": [],
                "entities": [],
                "recipes": [],
                "dimensions": [],
                "gui": [],
                "machinery": [],
                "commands": [],
                "events": [],
            },
            "dependencies": [],
            "metadata": {},
        }

        max_files = max(
            FEATURE_ANALYSIS_FILE_LIMIT, DEPENDENCY_ANALYSIS_FILE_LIMIT, METADATA_AST_FILE_LIMIT
        )

        feature_keywords = set()
        for patterns in self.feature_patterns.values():
            feature_keywords.update(patterns)

        metadata_keywords = {"Mod", "ModInstance", "Instance", "@Mod"}
        dependency_keywords = {"import", "package"}

        for i, source_path in enumerate(java_sources[:max_files]):
            need_features = i < FEATURE_ANALYSIS_FILE_LIMIT
            need_deps = i < DEPENDENCY_ANALYSIS_FILE_LIMIT
            need_metadata = i < METADATA_AST_FILE_LIMIT

            try:
                source_code = jar.read(source_path).decode("utf-8")

                should_parse = False

                if need_deps:
                    if any(k in source_code for k in dependency_keywords):
                        should_parse = True

                if not should_parse and need_metadata:
                    if any(k in source_code for k in metadata_keywords):
                        should_parse = True

                if not should_parse and need_features:
                    if any(k in source_code for k in feature_keywords):
                        should_parse = True

                if not should_parse:
                    continue

                tree = self._feature_extractor.parse_java_source(source_code)
                if not tree:
                    continue

                if need_features:
                    source_features = self._feature_extractor.extract_features_from_ast(tree)
                    for feature_type, feature_list in source_features.items():
                        if feature_type in batch_result["features"]:
                            batch_result["features"][feature_type].extend(feature_list)

                if need_deps:
                    dependencies = self._feature_extractor.analyze_dependencies_from_ast(tree)
                    batch_result["dependencies"].extend(dependencies)

                if need_metadata:
                    source_metadata = self._feature_extractor.extract_mod_metadata_from_ast(tree)
                    batch_result["metadata"].update(source_metadata)

            except Exception as e:
                logger.warning(f"Error analyzing source file {source_path}: {e}")
                if need_features:
                    class_name = source_path.split("/")[-1].replace(".java", "")
                    fallback_features = self._feature_extractor.extract_features_from_class_name(
                        class_name
                    )
                    for feature_type, feature_list in fallback_features.items():
                        if feature_type in batch_result["features"]:
                            batch_result["features"][feature_type].extend(feature_list)
                continue

        for feature_type in batch_result["features"]:
            seen = set()
            unique_features = []
            for feature in batch_result["features"][feature_type]:
                feature_key = f"{feature.get('name', '')}_{feature.get('registry_name', '')}"
                if feature_key not in seen:
                    seen.add(feature_key)
                    unique_features.append(feature)
            batch_result["features"][feature_type] = unique_features

        seen_imports = set()
        unique_dependencies = []
        for dep in batch_result["dependencies"]:
            import_path = dep.get("import", "")
            if import_path not in seen_imports:
                seen_imports.add(import_path)
                unique_dependencies.append(dep)
        batch_result["dependencies"] = unique_dependencies

        return batch_result

    def analyze_jar_with_ast(self, jar_path: str) -> dict:
        """
        AST-focused analysis: Extract comprehensive mod information using Java AST parsing.

        Args:
            jar_path: Path to the JAR file

        Returns:
            Dict with analysis results including features, dependencies, and metadata
        """
        try:
            logger.info(f"AST analysis of JAR: {jar_path}")
            result = {
                "success": False,
                "mod_info": {},
                "assets": {},
                "features": {},
                "dependencies": [],
                "framework": "unknown",
                "errors": [],
                "processing_time": 0,
            }

            start_time = time.time()

            with zipfile.ZipFile(jar_path, "r") as jar:
                file_list = jar.namelist()

                if not file_list:
                    logger.warning(f"Empty JAR file: {jar_path}")
                    result["success"] = True
                    result["mod_info"] = {
                        "name": "unknown",
                        "framework": "unknown",
                        "version": "1.0.0",
                    }
                    result["errors"].append("JAR file is empty but analysis completed")
                    result["processing_time"] = time.time() - start_time
                    result["file_count"] = 0
                    return result

                framework = self._detect_framework_from_jar_files(file_list, jar)
                result["framework"] = framework
                result["mod_info"]["framework"] = framework

                mod_info = self._archive_reader.extract_mod_info_from_jar(jar, file_list)
                result["mod_info"].update(mod_info)

                result["assets"] = self._archive_reader.analyze_assets_from_jar(file_list)

                java_sources = [f for f in file_list if f.endswith(".java")]
                if java_sources:
                    logger.info(f"Found {len(java_sources)} Java source files, analyzing with AST")
                    batch_results = self._analyze_sources_batch(jar, java_sources)

                    result["features"] = batch_results["features"]
                    result["dependencies"] = batch_results["dependencies"]
                    result["mod_info"].update(batch_results["metadata"])
                else:
                    logger.info("No Java source files found in JAR, attempting bytecode analysis")

                    from agents.java_analyzer.feature_extractor import JAVASSIST_AVAILABLE

                    if JAVASSIST_AVAILABLE:
                        bytecode_features = self._feature_extractor.analyze_classes_with_bytecode(
                            jar, file_list
                        )
                        if bytecode_features and (
                            bytecode_features.get("blocks")
                            or bytecode_features.get("items")
                            or bytecode_features.get("entities")
                        ):
                            logger.info(
                                f"Bytecode analysis found {len(bytecode_features['blocks'])} blocks, {len(bytecode_features['items'])} items"
                            )
                            result["features"] = bytecode_features
                        else:
                            logger.info(
                                "Bytecode analysis yielded no results, falling back to class name analysis"
                            )
                            result["features"] = (
                                self._feature_extractor.extract_features_from_classes(file_list)
                            )
                    else:
                        logger.info("Javassist not available, using class name-based analysis")
                        result["features"] = self._feature_extractor.extract_features_from_classes(
                            file_list
                        )

                    result["dependencies"] = []

                result["success"] = True
                result["file_count"] = len(file_list)

            result["processing_time"] = time.time() - start_time
            logger.info(
                f"AST analysis completed successfully for {jar_path} in {result['processing_time']:.2f}s"
            )
            return result

        except Exception as e:
            logger.error(f"AST analysis error: {e}")
            return {
                "success": False,
                "mod_info": {},
                "assets": {},
                "features": {},
                "dependencies": [],
                "framework": "unknown",
                "errors": [f"JAR analysis failed: {str(e)}"],
                "processing_time": 0,
            }

    def analyze_jar_for_mvp(self, jar_path: str) -> dict:
        """
        MVP-focused analysis: Extract registry name and texture path from simple block JAR.

        Args:
            jar_path: Path to the JAR file

        Returns:
            Dict with registry_name, texture_path, and success status
        """
        try:
            logger.info(f"MVP analysis of JAR: {jar_path}")
            result = {
                "success": False,
                "registry_name": "unknown:block",
                "texture_path": None,
                "errors": [],
            }

            with zipfile.ZipFile(jar_path, "r") as jar:
                file_list = jar.namelist()

                if not file_list:
                    logger.warning(f"Empty JAR file: {jar_path}")
                    result["success"] = True
                    result["registry_name"] = "unknown:copper_block"
                    result["errors"].append("JAR file is empty but analysis completed")
                    return result

                texture_path = self._archive_reader.find_block_texture(file_list)
                if texture_path:
                    result["texture_path"] = texture_path
                    logger.info(f"Found texture: {texture_path}")

                registry_name = self._extract_registry_name_from_jar(jar, file_list)
                if registry_name:
                    result["registry_name"] = registry_name
                    logger.info(f"Found registry name: {registry_name}")

                if registry_name and registry_name != "unknown:block":
                    result["success"] = True
                    logger.info(f"MVP analysis completed successfully for {jar_path}")
                    if not texture_path:
                        logger.warning("No texture found, will use default texture")
                        if "warnings" not in result:
                            result["warnings"] = []
                        result["warnings"].append(
                            "Could not find block texture in JAR, using default"
                        )
                else:
                    result["errors"].append("Could not determine block registry name")
                    if "success" not in result or not result["success"]:
                        result["success"] = False

                return result

        except Exception as e:
            logger.error(f"MVP analysis error: {e}")
            return {
                "success": False,
                "registry_name": "unknown:block",
                "texture_path": None,
                "errors": [f"JAR analysis failed: {str(e)}"],
            }

    def _detect_framework_from_jar_files(self, file_list: list, jar: zipfile.ZipFile) -> str:
        """Detect modding framework from JAR file contents"""
        return self._framework_detector._detect_framework_from_files(file_list, jar)

    def _analyze_jar_file(self, jar_path: str, result: dict) -> dict:
        """Analyze a JAR file for mod information"""
        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                file_list = jar.namelist()

                framework = self._detect_framework_from_jar_files(file_list, jar)
                result["mod_info"]["framework"] = framework

                mod_info = self._archive_reader.extract_mod_info_from_jar(jar, file_list)
                result["mod_info"].update(mod_info)

                result["assets"] = self._archive_reader.analyze_assets_from_jar(file_list)

                result["structure"] = {"files": len(file_list), "type": "jar"}

                java_sources = [f for f in file_list if f.endswith(".java")]
                if java_sources:
                    logger.info(f"Found {len(java_sources)} Java source files, analyzing with AST")
                    batch_results = self._analyze_sources_batch(jar, java_sources)
                    result["features"] = batch_results["features"]
                    result["dependencies"] = batch_results["dependencies"]
                else:
                    logger.info("No Java source files found in JAR, attempting bytecode analysis")

                    from agents.java_analyzer.feature_extractor import JAVASSIST_AVAILABLE

                    if JAVASSIST_AVAILABLE:
                        bytecode_features = self._feature_extractor.analyze_classes_with_bytecode(
                            jar, file_list
                        )
                        if bytecode_features and (
                            bytecode_features.get("blocks")
                            or bytecode_features.get("items")
                            or bytecode_features.get("entities")
                        ):
                            logger.info(
                                f"Bytecode analysis found {len(bytecode_features['blocks'])} blocks, {len(bytecode_features['items'])} items"
                            )
                            result["features"] = bytecode_features
                        else:
                            logger.info(
                                "Bytecode analysis yielded no results, falling back to class name analysis"
                            )
                            result["features"] = (
                                self._feature_extractor.extract_features_from_classes(file_list)
                            )
                    else:
                        logger.info("Javassist not available, using class name-based analysis")
                        result["features"] = self._feature_extractor.extract_features_from_classes(
                            file_list
                        )

        except Exception as e:
            result["errors"].append(f"Error analyzing JAR file: {str(e)}")

        return result

    def _analyze_source_directory(self, source_path: str, result: dict) -> dict:
        """Analyze a source directory for mod information"""
        try:
            result["mod_info"]["framework"] = "source"
            result["structure"] = {"type": "source", "path": source_path}
        except Exception as e:
            result["errors"].append(f"Error analyzing source directory: {str(e)}")

        return result

    def _extract_registry_name_from_jar_simple(self, jar, file_list: list) -> str:
        """Extract block registry name from JAR metadata (simple version)."""
        return self._archive_reader.extract_registry_name_from_jar_simple(jar, file_list)

    def _extract_registry_name_from_jar(self, jar: zipfile.ZipFile, file_list: list) -> str:
        """Extract registry name from JAR."""
        return self._archive_reader.extract_registry_name_from_jar(jar, file_list)

    def _find_block_texture(self, file_list: list) -> str:
        """Find a block texture in the JAR file list."""
        return self._archive_reader.find_block_texture(file_list)

    def _analyze_assets_from_jar(self, file_list: list) -> dict:
        """Analyze assets in the JAR file."""
        return self._archive_reader.analyze_assets_from_jar(file_list)

    def _extract_mod_id_from_metadata(self, jar: zipfile.ZipFile, file_list: list) -> Optional[str]:
        """Extract mod ID from metadata files."""
        return self._archive_reader._extract_mod_id_from_metadata(jar, file_list)

    def _extract_mod_info_from_jar(self, jar: zipfile.ZipFile, file_list: list) -> dict:
        """Extract mod info from JAR metadata."""
        return self._archive_reader.extract_mod_info_from_jar(jar, file_list)

    def _find_block_class_name(self, file_list: list) -> Optional[str]:
        """Find the main block class name from file paths."""
        return self._archive_reader._find_block_class_name(file_list)
