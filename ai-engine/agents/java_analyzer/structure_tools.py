"""Typed tools for Java mod *structure* & *metadata* analysis."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any, ClassVar, Dict, Union

from pydantic import BaseModel, ConfigDict, Field

from ._base_tool import _BaseJavaAnalyzerTool

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer.tools")


def _analyze_mod_structure_impl(mod_data: Union[str, Dict]) -> str:
    """
    Analyze the overall structure of a Java mod.

    Args:
        mod_data: JSON string containing mod file path and analysis options

    Returns:
        JSON string with structural analysis results
    """
    from agents.java_analyzer import JavaAnalyzerAgent

    agent = JavaAnalyzerAgent.get_instance()

    def _determine_mod_type_and_framework(mod_path: str) -> Dict[str, str]:
        """Determine mod type and framework"""
        if mod_path.endswith((".jar", ".zip")):
            mod_type = "jar"
            with zipfile.ZipFile(mod_path, "r") as jar:
                file_list = jar.namelist()
                framework = agent._detect_framework_from_jar_files(file_list, jar)
        elif os.path.isdir(mod_path):
            mod_type = "source"
            framework = agent.framework_indicators.get("unknown", "unknown")
        else:
            mod_type = "unknown"
            framework = "unknown"

        return {"type": mod_type, "framework": framework}

    def _analyze_jar_structure(jar_path: str, analysis_depth: str) -> Dict:
        """Analyze JAR file structure"""
        structure = {
            "total_files": 0,
            "package_structure": {},
            "main_classes": [],
            "resource_files": [],
            "metadata_files": [],
        }

        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                file_list = jar.namelist()
                structure["total_files"] = len(file_list)

                for file_name in file_list:
                    if file_name.endswith(".class"):
                        package_path = "/".join(file_name.split("/")[:-1])
                        if package_path not in structure["package_structure"]:
                            structure["package_structure"][package_path] = []
                        structure["package_structure"][package_path].append(file_name)

                        if _is_main_class(file_name):
                            structure["main_classes"].append(file_name)

                    elif any(
                        file_name.endswith(ext) for ext in agent.file_patterns["resource_files"]
                    ):
                        structure["resource_files"].append(file_name)

                    elif any(
                        metadata in file_name for metadata in agent.file_patterns["metadata_files"]
                    ):
                        structure["metadata_files"].append(file_name)

        except Exception as e:
            logger.warning(f"Error analyzing JAR structure: {e}")

        return structure

    def _analyze_source_structure(source_path: str, analysis_depth: str) -> Dict:
        """Analyze source directory structure"""
        structure = {
            "total_files": 0,
            "source_files": [],
            "resource_files": [],
            "config_files": [],
            "build_files": [],
        }

        try:
            for root, dirs, files in os.walk(source_path):
                structure["total_files"] += len(files)

                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(file_path, source_path)

                    if file_name.endswith(".java"):
                        structure["source_files"].append(rel_path)
                    elif any(
                        file_name.endswith(ext) for ext in agent.file_patterns["resource_files"]
                    ):
                        structure["resource_files"].append(rel_path)
                    elif any(
                        file_name.endswith(ext) for ext in agent.file_patterns["config_files"]
                    ):
                        structure["config_files"].append(rel_path)
                    elif file_name in ["build.gradle", "pom.xml", "build.xml"]:
                        structure["build_files"].append(rel_path)

        except Exception as e:
            logger.warning(f"Error analyzing source structure: {e}")

        return structure

    def _is_main_class(class_path: str) -> bool:
        """Check if a class is a main mod class"""
        class_name = class_path.split("/")[-1].replace(".class", "")
        package_path = "/".join(class_path.split("/")[:-1])

        mod_indicators = [
            "mod",
            "Mod",
            "main",
            "Main",
            "init",
            "Init",
            "loader",
            "Loader",
            "Core",
            "core",
            "Entry",
            "entry",
            "Plugin",
            "plugin",
        ]

        package_parts = package_path.split("/")
        has_mod_package = any(
            "mod" in part.lower() or "plugin" in part.lower() for part in package_parts if part
        )

        has_mod_name = any(indicator in class_name for indicator in mod_indicators)
        is_shallow = class_path.count("/") <= 3

        return (has_mod_package and has_mod_name) or is_shallow

    def _create_file_inventory(mod_path: str, mod_type: str) -> Dict:
        """Create comprehensive file inventory"""
        inventory = {"by_type": {}, "by_size": {}, "total_count": 0, "total_size": 0}

        if mod_type == "jar":
            try:
                with zipfile.ZipFile(mod_path, "r") as jar:
                    for info in jar.infolist():
                        if not info.is_dir():
                            file_ext = Path(info.filename).suffix.lower()
                            file_size = info.file_size

                            inventory["by_type"][file_ext] = (
                                inventory["by_type"].get(file_ext, 0) + 1
                            )
                            inventory["total_count"] += 1
                            inventory["total_size"] += file_size

                            size_category = (
                                "small"
                                if file_size < 1024
                                else "medium"
                                if file_size < 1024 * 1024
                                else "large"
                            )
                            inventory["by_size"][size_category] = (
                                inventory["by_size"].get(size_category, 0) + 1
                            )
            except Exception as e:
                logger.warning(f"Error creating JAR inventory: {e}")
        elif mod_type == "source":
            try:
                for root, dirs, files in os.walk(mod_path):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        file_ext = Path(file_name).suffix.lower()
                        file_size = os.path.getsize(file_path)

                        inventory["by_type"][file_ext] = inventory["by_type"].get(file_ext, 0) + 1
                        inventory["total_count"] += 1
                        inventory["total_size"] += file_size

                        size_category = (
                            "small"
                            if file_size < 1024
                            else "medium"
                            if file_size < 1024 * 1024
                            else "large"
                        )
                        inventory["by_size"][size_category] = (
                            inventory["by_size"].get(size_category, 0) + 1
                        )
            except Exception as e:
                logger.warning(f"Error creating source inventory: {e}")

        return inventory

    def _assess_mod_complexity(structure: Dict, file_inventory: Dict) -> Dict:
        """Assess the complexity of the mod for conversion planning"""
        complexity = {
            "overall_complexity": "medium",
            "complexity_factors": [],
            "complexity_score": 0,
            "conversion_difficulty": "moderate",
        }

        score = 0
        factors = []

        total_files = file_inventory.get("total_count", 0)
        if total_files > 100:
            score += 2
            factors.append("Large number of files")
        elif total_files > 50:
            score += 1
            factors.append("Moderate number of files")

        if "package_structure" in structure:
            packages = len(structure["package_structure"])
            if packages > 10:
                score += 2
                factors.append("Complex package structure")
            elif packages > 5:
                score += 1
                factors.append("Moderate package structure")

        resource_count = len(structure.get("resource_files", []))
        if resource_count > 50:
            score += 2
            factors.append("Many resource files")
        elif resource_count > 20:
            score += 1
            factors.append("Moderate resource files")

        if score >= 5:
            complexity["overall_complexity"] = "high"
            complexity["conversion_difficulty"] = "challenging"
        elif score >= 3:
            complexity["overall_complexity"] = "medium"
            complexity["conversion_difficulty"] = "moderate"
        else:
            complexity["overall_complexity"] = "low"
            complexity["conversion_difficulty"] = "straightforward"

        complexity["complexity_score"] = score
        complexity["complexity_factors"] = factors

        return complexity

    try:
        if isinstance(mod_data, str):
            try:
                data = json.loads(mod_data)
                if "mod_data" in data:
                    mod_path = data["mod_data"]
                    analysis_depth = data.get("analysis_depth", "standard")
                else:
                    mod_path = data.get("mod_path", "")
                    analysis_depth = data.get("analysis_depth", "standard")
            except json.JSONDecodeError:
                mod_path = mod_data
                analysis_depth = "standard"
        else:
            data = mod_data if isinstance(mod_data, dict) else {"mod_path": str(mod_data)}
            if "mod_data" in data:
                mod_path = data["mod_data"]
                analysis_depth = data.get("analysis_depth", "standard")
            else:
                mod_path = data.get("mod_path", str(mod_data))
                analysis_depth = data.get("analysis_depth", "standard")

        if not os.path.exists(mod_path):
            return json.dumps({"success": False, "error": f"Mod file not found: {mod_path}"})

        analysis_results = {
            "mod_path": mod_path,
            "mod_type": "",
            "framework": "",
            "structure_analysis": {},
            "file_inventory": {},
            "complexity_assessment": {},
        }

        mod_info = _determine_mod_type_and_framework(mod_path)
        analysis_results["mod_type"] = mod_info["type"]
        analysis_results["framework"] = mod_info["framework"]

        if mod_info["type"] == "jar":
            structure = _analyze_jar_structure(mod_path, analysis_depth)
        elif mod_info["type"] == "source":
            structure = _analyze_source_structure(mod_path, analysis_depth)
        else:
            structure = {"type": "unknown", "path": mod_path, "size": 0}

        analysis_results["structure_analysis"] = structure

        file_inventory = _create_file_inventory(mod_path, mod_info["type"])
        analysis_results["file_inventory"] = file_inventory

        complexity = _assess_mod_complexity(structure, file_inventory)
        analysis_results["complexity_assessment"] = complexity

        response = {
            "success": True,
            "analysis_results": analysis_results,
            "recommendations": ["Complete feature extraction for detailed conversion planning"],
        }

        logger.info(
            f"Analyzed mod structure: {mod_path} ({mod_info['framework']} {mod_info['type']})"
        )
        return json.dumps(response)

    except Exception as e:
        error_response = {
            "success": False,
            "error": f"Failed to analyze mod structure: {str(e)}",
        }
        logger.error(f"Mod structure analysis error: {e}")
        return json.dumps(error_response)


def _extract_mod_metadata_impl(mod_data: Union[str, Dict]) -> str:
    """
    Extract metadata from mod files.

    Args:
        mod_data: JSON string containing mod file path

    Returns:
        JSON string with metadata
    """
    from agents.java_analyzer import JavaAnalyzerAgent

    agent = JavaAnalyzerAgent.get_instance()

    def _extract_jar_metadata(jar_path: str) -> Dict:
        """Extract metadata from JAR file"""
        metadata = {}

        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                for metadata_file in agent.file_patterns["metadata_files"]:
                    if metadata_file in jar.namelist():
                        try:
                            content = jar.read(metadata_file).decode("utf-8")
                            if metadata_file.endswith(".json"):
                                metadata.update(json.loads(content))
                            else:
                                metadata[metadata_file] = content
                        except Exception as e:
                            logger.warning(f"Error reading {metadata_file}: {e}")
        except Exception as e:
            logger.warning(f"Error extracting JAR metadata: {e}")

        return metadata

    def _extract_source_metadata(source_path: str) -> Dict:
        """Extract metadata from source directory"""
        metadata = {}

        try:
            for root, dirs, files in os.walk(source_path):
                for file_name in files:
                    if file_name in agent.file_patterns["metadata_files"]:
                        file_path = os.path.join(root, file_name)
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                                if file_name.endswith(".json"):
                                    metadata.update(json.loads(content))
                                else:
                                    metadata[file_name] = content
                        except Exception as e:
                            logger.warning(f"Error reading {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Error extracting source metadata: {e}")

        return metadata

    try:
        if isinstance(mod_data, str):
            try:
                data = json.loads(mod_data)
                if "mod_data" in data:
                    mod_path = data["mod_data"]
                else:
                    mod_path = data.get("mod_path", "")
            except json.JSONDecodeError:
                mod_path = mod_data
        else:
            data = mod_data if isinstance(mod_data, dict) else {"mod_path": str(mod_data)}
            if "mod_data" in data:
                mod_path = data["mod_data"]
            else:
                mod_path = data.get("mod_path", str(mod_data))

        metadata_results = {
            "mod_info": {},
            "dependencies": [],
            "version_info": {},
            "author_info": {},
            "feature_flags": {},
            "compatibility_info": {},
        }

        if mod_path.endswith((".jar", ".zip")):
            metadata = _extract_jar_metadata(mod_path)
        else:
            metadata = _extract_source_metadata(mod_path)

        metadata_results.update(metadata)

        response = {
            "success": True,
            "metadata": metadata_results,
            "extraction_summary": {"summary": "Metadata extraction completed"},
        }

        logger.info(f"Extracted metadata from: {mod_path}")
        return json.dumps(response)

    except Exception as e:
        error_response = {"success": False, "error": f"Failed to extract metadata: {str(e)}"}
        logger.error(f"Metadata extraction error: {e}")
        return json.dumps(error_response)


class _AnalyzeModStructureInput(BaseModel):
    """Args for :class:`_AnalyzeModStructureTool`."""

    model_config = ConfigDict(extra="forbid")
    mod_data: Any = Field(
        description=(
            "JSON string or dict containing ``mod_path`` and analysis options. "
            "``Any`` preserves the legacy ``Union[str, Dict]`` calling shape."
        ),
    )


class _ExtractModMetadataInput(BaseModel):
    """Args for :class:`_ExtractModMetadataTool`."""

    model_config = ConfigDict(extra="forbid")
    mod_data: Any = Field(
        description="JSON string or dict containing ``mod_path``.",
    )


class _AnalyzeModStructureTool(_BaseJavaAnalyzerTool):
    name: str = "analyze_mod_structure_tool"
    description: str = (
        "Analyze the overall structure of a Java mod (mod type, framework, "
        "file inventory, complexity assessment). "
        "Args: mod_data (str or dict, required) — mod_path and options."
    )
    args_schema: ClassVar[type[BaseModel]] = _AnalyzeModStructureInput

    def _run(self, mod_data: Any) -> str:  # type: ignore[override]
        return _analyze_mod_structure_impl(mod_data)


class _ExtractModMetadataTool(_BaseJavaAnalyzerTool):
    name: str = "extract_mod_metadata_tool"
    description: str = (
        "Extract metadata from a Java mod's manifest "
        "(fabric.mod.json, mods.toml, mcmod.info). "
        "Args: mod_data (str or dict, required) — mod_path."
    )
    args_schema: ClassVar[type[BaseModel]] = _ExtractModMetadataInput

    def _run(self, mod_data: Any) -> str:  # type: ignore[override]
        return _extract_mod_metadata_impl(mod_data)
