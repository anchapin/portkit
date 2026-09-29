"""
Asset Converter Agent - Audio module.

Contains audio-related methods that delegate to audio_converter subpackage.
"""

from typing import Dict, List

from agents.audio_converter import (
    _convert_single_audio as _ac_convert_single_audio,
    _analyze_audio,
    _generate_sound_structure,
)

# Optional audio support
try:
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError

    HAS_AUDIO_SUPPORT = True
except ImportError:
    HAS_AUDIO_SUPPORT = False
    AudioSegment = None
    CouldntDecodeError = Exception


def _convert_single_audio(agent, audio_path: str, metadata: Dict, audio_type: str) -> Dict:
    """Convert a single audio file to Bedrock format."""
    return _ac_convert_single_audio(agent, audio_path, metadata, audio_type)


def _analyze_audio(agent, audio_path: str, metadata: Dict) -> Dict:
    """Analyze an audio file for conversion needs."""
    return _analyze_audio(agent, audio_path, metadata)


def _generate_sound_structure(agent, sounds: List[Dict]) -> Dict:
    """Generate sound structure files."""
    return _generate_sound_structure(agent, sounds)


def convert_audio(audio_list: str, output_path: str) -> str:
    """Convert audio to Bedrock format (standalone function)."""
    from agents.asset_converter.base import AssetConverterAgent

    agent = AssetConverterAgent.get_instance()
    return (
        agent.convert_audio_tool(audio_list)
        if hasattr(agent, "convert_audio_tool")
        else str({"success": False, "error": "Audio conversion not available"})
    )
