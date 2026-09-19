"""
Asset Converter Agent - Models module.

Contains model-related methods that delegate to model_converter subpackage.
"""

from typing import Dict, List, Tuple

from agents.model_converter import (
    _convert_single_model as _mc_convert_single_model,
    _analyze_model,
    _generate_model_structure,
    extract_models_from_jar,
    parse_blockstate,
    resolve_parent_model,
    get_model_elements_with_inheritance,
    convert_blockstate,
)


def _convert_single_model(agent, model_path: str, metadata: Dict, entity_type: str) -> Dict:
    """Convert a single model to Bedrock format."""
    return _mc_convert_single_model(agent, model_path, metadata, entity_type)


def _analyze_model(agent, model_path: str, metadata: Dict) -> Dict:
    """Analyze a model for conversion needs."""
    return _analyze_model(agent, model_path, metadata)


def _generate_model_structure(agent, models: List[Dict]) -> Dict:
    """Generate model structure files."""
    return _generate_model_structure(agent, models)


def extract_models_from_jar(jar_path: str, output_dir: str, namespace: str = None) -> Dict:
    """Extract models from a Java mod JAR file."""
    return extract_models_from_jar(jar_path, output_dir, namespace)


def _parse_blockstate(agent, blockstate_data: Dict) -> Dict:
    """Parse a blockstate JSON file."""
    return parse_blockstate(blockstate_data)


def _resolve_parent_model(
    agent, model_data: Dict, model_cache: Dict, namespace: str = None
) -> Tuple[List[Dict], List[str]]:
    """Resolve parent model inheritance."""
    return resolve_parent_model(model_data, model_cache, namespace)


def _get_model_elements_with_inheritance(
    agent, model_json: Dict, all_models: Dict, namespace: str = None
) -> Tuple[List[Dict], List[str]]:
    """Get model elements with inheritance resolved."""
    return get_model_elements_with_inheritance(model_json, all_models, namespace)


def _convert_blockstate(
    agent, blockstate_path: str, model_output_dir: str, all_models: Dict, namespace: str = None
) -> Dict:
    """Convert a blockstate file to Bedrock format."""
    return convert_blockstate(agent, blockstate_path, model_output_dir, all_models, namespace)


def convert_blockstate(
    agent, blockstate_path: str, model_output_dir: str, all_models: Dict, namespace: str = None
) -> Dict:
    """Convert a blockstate file (standalone function)."""
    return convert_blockstate(agent, blockstate_path, model_output_dir, all_models, namespace)


def parse_blockstate(blockstate_data: Dict) -> Dict:
    """Parse blockstate data (standalone function)."""
    return parse_blockstate(blockstate_data)


def convert_models(model_list: str, output_path: str) -> str:
    """Convert models to Bedrock format (standalone function)."""
    from agents.asset_converter.base import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()
    return (
        agent.convert_models_tool(model_list)
        if hasattr(agent, "convert_models_tool")
        else str({"success": False, "error": "Model conversion not available"})
    )
