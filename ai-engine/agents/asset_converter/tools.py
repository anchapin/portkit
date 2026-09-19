"""
Asset converter tool functions and wrappers.

Extracted from __init__.py to resolve the monolith pattern (issue #1740).
"""

import json
from pathlib import Path

from .base import ToolFunction, _assess_conversion_complexity


def analyze_assets_tool_func(asset_data: str) -> str:
    """Analyze assets for conversion."""
    from agents.asset_converter import AssetConverterAgent

    AssetConverterAgent.get_instance()

    try:
        data = json.loads(asset_data) if isinstance(asset_data, str) else asset_data
        if isinstance(data, list) and all(isinstance(d, list) for d in data):
            asset_list = [{"path": d[0], "metadata": d[1] if len(d) > 1 else {}} for d in data]
        elif isinstance(data, list):
            asset_list = data
        else:
            asset_list = data.get("asset_list", [data])
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    analysis_results = {
        "textures": {"count": 0, "needs_conversion": 0, "issues": [], "conversions_needed": []},
        "models": {"count": 0, "issues": [], "conversions_needed": []},
        "audio": {"count": 0, "issues": [], "conversions_needed": []},
        "other": {"count": 0},
    }

    for asset in asset_list:
        path = (
            asset
            if isinstance(asset, str)
            else (asset.get("path", "") if isinstance(asset, dict) else "")
        )
        metadata = asset.get("metadata", {}) if isinstance(asset, dict) else {}

        file_ext = Path(path).suffix.lower()

        if file_ext in [".png", ".jpg", ".jpeg", ".tga", ".bmp"]:
            analysis_results["textures"]["count"] += 1
            width = metadata.get("width", 16)
            height = metadata.get("height", 16)
            if not (width > 0 and (width & (width - 1)) == 0) or not (
                height > 0 and (height & (height - 1)) == 0
            ):
                analysis_results["textures"]["needs_conversion"] += 1
                analysis_results["textures"]["issues"].append(
                    f"Resolution {width}x{height} is not power of 2"
                )
            if width > 1024 or height > 1024:
                analysis_results["textures"]["issues"].append(
                    f"Resolution {width}x{height} exceeds maximum 1024"
                )
        elif file_ext in [".obj", ".fbx", ".json"]:
            analysis_results["models"]["count"] += 1
            vertices = metadata.get("vertices", 0)
            if vertices > 3000:
                analysis_results["models"]["issues"].append(
                    f"Vertex count {vertices} exceeds maximum 3000"
                )
        elif file_ext in [".ogg", ".wav", ".mp3"]:
            analysis_results["audio"]["count"] += 1
            duration = metadata.get("duration_seconds", 0)
            if duration > 300:
                analysis_results["audio"]["issues"].append(
                    f"Duration {duration}s exceeds maximum 300s"
                )
        else:
            analysis_results["other"]["count"] += 1

    total_assets = sum(analysis_results[k]["count"] for k in analysis_results)

    return json.dumps(
        {
            "success": True,
            "total_assets": total_assets,
            "analysis_results": analysis_results,
            "conversion_complexity": _assess_conversion_complexity(analysis_results),
        }
    )


def convert_textures_tool_func(texture_data: str) -> str:
    """Convert textures to Bedrock format."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(texture_data) if isinstance(texture_data, str) else texture_data
        texture_list = (
            data if isinstance(data, list) else data.get("textures", data.get("texture_list", []))
        )
        output_dir = (
            data.get("output_path", "/tmp/texture_output")
            if isinstance(data, dict)
            else "/tmp/texture_output"
        )
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    if not texture_list:
        return json.dumps({"success": False, "error": "No textures provided"})

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    conversion_results = []
    errors = []
    successful_results = []

    for texture_info in texture_list:
        texture_path = (
            texture_info if isinstance(texture_info, str) else texture_info.get("path", "")
        )
        if not texture_path:
            continue

        try:
            result = agent._convert_single_texture(texture_path, {}, "texture", output_path)
            if result.get("success"):
                conversion_results.append(result)
                successful_results.append(
                    {
                        "resized": result.get("resized", False),
                        "was_fallback": result.get("was_fallback", False),
                        "converted_dimensions": list(result.get("converted_dimensions", [])),
                        "original_path": result.get("original_path", texture_path),
                        "converted_path": result.get("converted_path", ""),
                    }
                )
        except Exception as e:
            errors.append({"texture": texture_path, "error": str(e)})

    bedrock_pack_files = {}
    if conversion_results:
        pack_structure = agent._generate_texture_pack_structure(conversion_results)
        bedrock_pack_files = pack_structure

    return json.dumps(
        {
            "success": True,
            "conversion_summary": {"successfully_converted": len(conversion_results)},
            "successful_results": successful_results,
            "bedrock_pack_files": bedrock_pack_files,
            "converted_textures": [r.get("converted_path", "") for r in conversion_results],
            "total_textures": len(texture_list),
            "failed_conversions": len(errors),
            "errors": errors,
        }
    )


def convert_models_tool_func(model_data: str) -> str:
    """Convert models to Bedrock format."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(model_data) if isinstance(model_data, str) else model_data
        model_list = (
            data if isinstance(data, list) else data.get("models", data.get("model_list", []))
        )
        output_dir = (
            data.get("output_path", "/tmp/model_output")
            if isinstance(data, dict)
            else "/tmp/model_output"
        )
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    if not model_list:
        return json.dumps({"success": False, "error": "No models provided"})

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    successful_results = []
    errors = []

    for model_info in model_list:
        model_path = model_info if isinstance(model_info, str) else model_info.get("path", "")
        if not model_path:
            continue

        entity_type = "entity"
        if isinstance(model_info, dict) and "entity_type" in model_info:
            entity_type = model_info["entity_type"]
        else:
            try:
                with open(model_path, "r") as f:
                    model_data = json.load(f)
                parent = model_data.get("parent", "")
                if parent.startswith("block/"):
                    entity_type = "block"
                elif parent.startswith("item/"):
                    entity_type = "item"
            except Exception:
                pass

        try:
            result = agent._convert_single_model(model_path, {}, entity_type)
            if result.get("success"):
                successful_results.append(
                    {
                        "converted_path": result.get("converted_path", ""),
                        "bedrock_identifier": result.get("bedrock_identifier", ""),
                        "original_path": model_path,
                    }
                )
        except Exception as e:
            errors.append({"model": model_path, "error": str(e)})

    return json.dumps(
        {
            "success": True,
            "conversion_summary": {
                "total_requested": len(model_list),
                "successfully_converted": len(successful_results),
            },
            "successful_results": successful_results,
            "failed_conversions": len(errors),
            "errors": errors,
        }
    )


def convert_audio_tool_func(audio_data: str) -> str:
    """Convert audio to Bedrock format."""
    from agents.asset_converter import HAS_AUDIO_SUPPORT, AssetConverterAgent

    if not HAS_AUDIO_SUPPORT:
        return json.dumps(
            {"success": False, "error": "Audio support not available (pydub not installed)"}
        )

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(audio_data) if isinstance(audio_data, str) else audio_data
        audio_list = data if isinstance(data, list) else data.get("audio_list", [])
        output_dir = (
            data.get("output_path", "/tmp/audio_output")
            if isinstance(data, dict)
            else "/tmp/audio_output"
        )
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    if not audio_list:
        return json.dumps({"success": False, "error": "No audio files provided"})

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    converted = []
    errors = []

    for audio_info in audio_list:
        audio_path = audio_info if isinstance(audio_info, str) else audio_info.get("path", "")
        if not audio_path:
            continue

        try:
            result = agent._convert_single_audio(audio_path, {}, "ambient")
            if result.get("success"):
                converted.append(audio_path)
        except Exception as e:
            errors.append({"audio": audio_path, "error": str(e)})

    return json.dumps(
        {
            "success": True,
            "conversion_summary": {
                "total_requested": len(audio_list),
                "successfully_converted": len(converted),
            },
            "converted_audio": converted,
            "failed_conversions": len(errors),
            "errors": errors,
        }
    )


def validate_bedrock_assets_tool_func(assets_data: str) -> str:
    """Validate Bedrock assets."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(assets_data) if isinstance(assets_data, str) else assets_data
        assets = data.get("assets", []) if isinstance(data, dict) else data
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    results = []
    warning_count = 0
    optimization_count = 0

    for asset in assets:
        path = asset if isinstance(asset, str) else asset.get("path", "")
        asset_type = asset.get("type", "unknown") if isinstance(asset, dict) else "unknown"
        metadata = asset.get("metadata", {}) if isinstance(asset, dict) else {}

        validation = {"path": path, "valid": True, "issues": [], "warnings": []}

        file_ext = Path(path).suffix.lower()
        if asset_type == "texture" or file_ext in [".png", ".jpg", ".jpeg", ".tga", ".bmp"]:
            result = agent.validate_texture(path, metadata if metadata else None)
            if not result.get("valid", False):
                validation["valid"] = False
                validation["issues"].extend(result.get("errors", []))
            validation["warnings"] = result.get("warnings", [])
            if validation["warnings"]:
                warning_count += 1
            if result.get("properties", {}).get("format") != "PNG":
                optimization_count += 1

        results.append(validation)

    return json.dumps(
        {
            "success": True,
            "results": results,
            "quality_metrics": {
                "total_assets": len(assets),
                "warning_count": warning_count,
                "optimization_count": optimization_count,
            },
        }
    )


def extract_jar_textures_tool_func(jar_data: str) -> str:
    """Extract textures from JAR file."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(jar_data) if isinstance(jar_data, str) else jar_data
        jar_path = data.get("jar_path", "") if isinstance(data, dict) else ""
        output_dir = (
            data.get("output_dir", "/tmp/jar_textures")
            if isinstance(data, dict)
            else "/tmp/jar_textures"
        )
        namespace = data.get("namespace", None)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    if not jar_path:
        return json.dumps({"success": False, "error": "No JAR path provided"})

    try:
        result = agent.convert_jar_textures_to_bedrock(jar_path, output_dir, namespace)
        result["extracted_count"] = len(result.get("extracted", []))
        result["converted_count"] = len(result.get("converted", []))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def convert_java_texture_path_tool_func(path_data: str) -> str:
    """Convert Java texture path to Bedrock."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(path_data) if isinstance(path_data, str) else path_data
        java_path = data.get("path", "") if isinstance(data, dict) else ""
        bedrock_type = data.get("type", "blocks") if isinstance(data, dict) else "blocks"
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    if not java_path:
        return json.dumps({"success": False, "error": "No path provided"})

    result = agent.convert_java_texture_path(java_path, bedrock_type)
    return json.dumps({"success": True, "bedrock_path": result})


def validate_texture_tool_func(texture_path: str) -> str:
    """Validate a texture for Bedrock compatibility."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    if not texture_path:
        return json.dumps({"success": False, "error": "No texture path provided"})

    result = agent.validate_texture(texture_path)
    return json.dumps({"success": True, "result": result})


def generate_fallback_texture_tool_func(texture_data: str) -> str:
    """Generate fallback texture for missing assets."""
    from agents.asset_converter import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()

    try:
        data = json.loads(texture_data) if isinstance(texture_data, str) else texture_data
        output_path = data.get("output_path", "") if isinstance(data, dict) else ""
        block_name = data.get("block_name", "unknown") if isinstance(data, dict) else "unknown"
        texture_type = data.get("type", "blocks") if isinstance(data, dict) else "blocks"
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "Invalid input format"})

    if not output_path:
        return json.dumps({"success": False, "error": "No output path provided"})

    result = agent.generate_fallback_for_jar(output_path, block_name, texture_type)
    return json.dumps({"success": True, "result": result})


analyze_assets_tool = ToolFunction(analyze_assets_tool_func)
analyze_assets = analyze_assets_tool_func
convert_textures_tool = ToolFunction(convert_textures_tool_func)
convert_models_tool = ToolFunction(convert_models_tool_func)
convert_audio_tool = ToolFunction(convert_audio_tool_func)
validate_bedrock_assets_tool = ToolFunction(validate_bedrock_assets_tool_func)
extract_jar_textures_tool = ToolFunction(extract_jar_textures_tool_func)
convert_java_texture_path_tool = ToolFunction(convert_java_texture_path_tool_func)
validate_texture_tool = ToolFunction(validate_texture_tool_func)
generate_fallback_texture_tool = ToolFunction(generate_fallback_texture_tool_func)


def _attach_tool_instances(agent_cls: type) -> None:
    """Attach module-level tool instances as class attributes on AssetConverterAgent."""
    agent_cls.analyze_assets_tool = analyze_assets_tool
    agent_cls.convert_textures_tool = convert_textures_tool
    agent_cls.convert_models_tool = convert_models_tool
    agent_cls.convert_audio_tool = convert_audio_tool
    agent_cls.validate_bedrock_assets_tool = validate_bedrock_assets_tool
    agent_cls.extract_jar_textures_tool = extract_jar_textures_tool
    agent_cls.convert_java_texture_path_tool = convert_java_texture_path_tool
    agent_cls.validate_texture_tool = validate_texture_tool
    agent_cls.generate_fallback_texture_tool = generate_fallback_texture_tool
