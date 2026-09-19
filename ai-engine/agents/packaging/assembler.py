"""
Packaging assembly and execution logic.

Extracted from packaging/agent.py per issue #1766. Each function here parses
its JSON input, delegates to the appropriate generator/validator held by the
PackagingAgent singleton, and returns a JSON-serializable result string.
These are the "execution logic" half of the agent; orchestration state lives
in orchestrator.py and typed LangChain wrappers live in tools.py.

Functions are invoked by PackagingAgent static methods (lazy import) and by
the BaseTool wrappers in tools.py.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_enhanced_manifests(mod_data: str) -> str:
    """Generate enhanced Bedrock manifests using the manifest generator."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()

        if isinstance(mod_data, str):
            data = json.loads(mod_data)
        else:
            data = mod_data

        bp_manifest, rp_manifest = agent.manifest_generator_enhanced.generate_manifests(data)

        result = {
            "success": True,
            "behavior_pack_manifest": bp_manifest,
            "resource_pack_manifest": rp_manifest,
            "message": "Enhanced manifests generated successfully",
        }

        return json.dumps(result)

    except Exception as e:
        logger.error(f"Enhanced manifest generation error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def generate_blocks_and_items(conversion_data: str) -> str:
    """Generate Bedrock blocks and items from Java conversion data."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()

        if isinstance(conversion_data, str):
            data = json.loads(conversion_data)
        else:
            data = conversion_data

        java_blocks = data.get("blocks", [])
        java_items = data.get("items", [])
        java_recipes = data.get("recipes", [])

        bedrock_blocks = agent.block_item_generator.generate_blocks(java_blocks)
        bedrock_items = agent.block_item_generator.generate_items(java_items)
        bedrock_recipes = agent.block_item_generator.generate_recipes(java_recipes)

        result = {
            "success": True,
            "blocks": bedrock_blocks,
            "items": bedrock_items,
            "recipes": bedrock_recipes,
            "stats": {
                "blocks_generated": len(bedrock_blocks),
                "items_generated": len(bedrock_items),
                "recipes_generated": len(bedrock_recipes),
            },
            "message": "Blocks, items, and recipes generated successfully",
        }

        return json.dumps(result)

    except Exception as e:
        logger.error(f"Block/item generation error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def generate_entities(entity_data: str) -> str:
    """Generate Bedrock entities from Java entity data."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()

        if isinstance(entity_data, str):
            data = json.loads(entity_data)
        else:
            data = entity_data

        java_entities = data.get("entities", [])

        bedrock_entities = agent.entity_converter.convert_entities(java_entities)

        result = {
            "success": True,
            "entities": bedrock_entities,
            "stats": {"entities_generated": len(bedrock_entities)},
            "message": "Entities generated successfully",
        }

        return json.dumps(result)

    except Exception as e:
        logger.error(f"Entity generation error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def package_enhanced_addon(package_data: str) -> str:
    """Package addon using the enhanced file packager."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()

        if isinstance(package_data, str):
            data = json.loads(package_data)
        else:
            data = package_data

        result = agent.file_packager.package_addon(data)

        if result["success"]:
            logger.info(f"Enhanced packaging successful: {result['output_path']}")

        return json.dumps(result)

    except Exception as e:
        logger.error(f"Enhanced packaging error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def validate_enhanced_addon(addon_path: str) -> str:
    """Validate addon using the enhanced validator."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()

        validation_result = agent.addon_validator.validate_addon(Path(addon_path))

        def convert_paths(obj):
            from pathlib import Path as PathType

            if isinstance(obj, PathType):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            return obj

        result = convert_paths(validation_result)
        result["addon_path"] = addon_path

        logger.info(f"Enhanced validation completed. Score: {result.get('overall_score', 0)}/100")

        return json.dumps(result)

    except Exception as e:
        logger.error(f"Enhanced validation error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def validate_mcaddon_structure(mcaddon_path: str) -> str:
    """Validate .mcaddon file structure using comprehensive validator."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()
        validator = agent.packaging_validator

        result = validator.validate_mcaddon(Path(mcaddon_path))

        result_dict = {
            "is_valid": result.is_valid,
            "overall_score": result.overall_score,
            "issues": [
                {
                    "severity": issue.severity.value,
                    "category": issue.category,
                    "message": issue.message,
                    "file_path": str(issue.file_path) if issue.file_path else None,
                    "suggestion": issue.suggestion,
                }
                for issue in result.issues
            ],
            "stats": result.stats,
            "compatibility": result.compatibility,
            "file_structure": result.file_structure,
        }

        return json.dumps(result_dict)

    except Exception as e:
        logger.error(f"Structure validation error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def validate_manifest_schema(manifest_data: str) -> str:
    """Validate a manifest.json against Bedrock JSON schema."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()
        validator = agent.packaging_validator

        manifest_path = Path(manifest_data)
        if manifest_path.exists() and manifest_path.is_file():
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
        else:
            manifest = json.loads(manifest_data)

        if "manifest" not in validator.schemas:
            return json.dumps({"success": False, "error": "Manifest schema not loaded"})

        try:
            import jsonschema

            jsonschema.validate(manifest, validator.schemas["manifest"])
            return json.dumps(
                {"success": True, "valid": True, "message": "Manifest passes schema validation"}
            )
        except jsonschema.ValidationError as e:
            return json.dumps(
                {
                    "success": True,
                    "valid": False,
                    "error": e.message,
                    "path": list(e.path) if e.path else [],
                    "schema_path": list(e.schema_path) if e.schema_path else [],
                }
            )

    except json.JSONDecodeError as e:
        return json.dumps({"success": False, "error": f"Invalid JSON: {e}"})
    except Exception as e:
        logger.error(f"Manifest schema validation error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def generate_validation_report(mcaddon_path: str) -> str:
    """Generate a human-readable validation report for .mcaddon file."""
    from .orchestrator import PackagingAgent

    try:
        agent = PackagingAgent.get_instance()
        validator = agent.packaging_validator

        from agents.packaging import generate_validation_report as format_report

        result = validator.validate_mcaddon(Path(mcaddon_path))
        report = format_report(result)

        return json.dumps(
            {
                "success": True,
                "report": report,
                "is_valid": result.is_valid,
                "score": result.overall_score,
            }
        )

    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return json.dumps({"success": False, "error": str(e)})
