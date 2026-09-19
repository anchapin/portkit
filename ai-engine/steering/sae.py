"""
Sparse Autoencoder (SAE) Wrapper for Feature Steering.

Provides a clean interface for:
1. Running text through an SAE to get sparse feature activations
2. Extracting specific feature indices for steering
3. Computing steering vectors from feature differences

Based on: "Sieve: SAEs Beat Baselines on a Real-World Task (A Code Generation Case Study)"
https://blog.tilderesearch.com/blog/sieve

The Sieve approach:
1. Run text through SAE to get feature activations
2. Identify features corresponding to unwanted patterns (Java idioms)
3. Compute steering vector = weighted_sum(features) for suppression
4. At inference time, subtract steering vector from hidden states

For PortKit, this means surgically suppressing "Java Forge API style" features
during Bedrock code generation without affecting general code quality.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SAEOutputType(str, Enum):
    """What the SAE model returns"""

    SPARSE_ACTIVATIONS = "sparse_activations"  # Top-k activated features
    DENSE_ACTIVATIONS = "dense_activations"  # All features before sparsification
    RECONSTRUCTED = "reconstructed"  # Reconstructed hidden states


@dataclass
class SAEConfig:
    """Configuration for SAE model"""

    # SAE model endpoint (OpenAI-compatible)
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str = "sae/sparse-autoencoder"  # Local SAE model ID

    # Feature extraction settings
    top_k: int = 50  # Number of top features to return
    threshold: float = 0.01  # Minimum activation to include

    # Steering settings
    steering_scale: float = 2.0  # Multiplier for steering vector magnitude
    normalize_steering: bool = True  # Normalize steering vector to unit length

    # Caching
    cache_enabled: bool = True
    max_cache_size: int = 1000


@dataclass
class SAEResult:
    """Result from running text through SAE"""

    text: str
    features: List[int]  # Feature indices
    activations: List[float]  # Activation values
    dense_activations: Optional[np.ndarray] = None  # All activations before top-k
    sparsity: float = 0.0  # What fraction of features are active
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @property
    def n_active_features(self) -> int:
        return len(self.features)

    def get_feature_weights(self) -> Dict[int, float]:
        """Get feature -> weight mapping"""
        return {f: w for f, w in zip(self.features, self.activations)}


class SAEClient:
    """
    Client for running text through a Sparse Autoencoder.

    Supports:
    - OpenAI-compatible SAE endpoints (local inference servers)
    - Direct numpy array inputs for local SAE models
    - Feature caching for efficiency

    The SAE decompresses the model's residual stream into a superposition of
    sparse, interpretable features. Each feature corresponds to a meaningful
    semantic concept (e.g., "contains Java keyword 'extends'", "has for-loop").

    Usage:
        client = SAEClient(config)
        result = client.run("public class MyItem extends Item { ... }")
        java_features = result.features
    """

    def __init__(self, config: Optional[SAEConfig] = None):
        self.config = config or SAEConfig()
        self._cache: Dict[str, SAEResult] = {}
        self._feature_stats: Dict[int, List[float]] = {}  # For debugging

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        # Simple hash - in production use better caching
        return hash(text) % (self.config.max_cache_size * 2)

    async def run_async(self, text: str, top_k: Optional[int] = None) -> SAEResult:
        """
        Run text through SAE to get feature activations.

        Args:
            text: Input text to analyze
            top_k: Override number of top features to return

        Returns:
            SAEResult with activated features and their weights
        """
        cache_key = self._get_cache_key(text)
        if self.config.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        top_k = top_k or self.config.top_k

        try:
            result = await self._run_sae_async(text, top_k)
        except Exception as e:
            logger.warning(f"SAE inference failed, using fallback: {e}")
            result = self._fallback_result(text)

        if self.config.cache_enabled:
            self._cache[cache_key] = result

        # Track stats for analysis
        self._update_feature_stats(result)

        return result

    def run(self, text: str, top_k: Optional[int] = None) -> SAEResult:
        """Synchronous wrapper for run_async"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create future if loop is running
                future = asyncio.ensure_future(self.run_async(text, top_k))
                return future.result() if hasattr(future, "result") else None
            else:
                return loop.run_until_complete(self.run_async(text, top_k))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.run_async(text, top_k))

    async def _run_sae_async(self, text: str, top_k: int) -> SAEResult:
        """Make actual SAE inference call"""
        if self.config.endpoint_url:
            return await self._run_remote_sae(text, top_k)
        else:
            return self._run_local_sae(text, top_k)

    async def _run_remote_sae(self, text: str, top_k: int) -> SAEResult:
        """Run SAE inference via remote endpoint"""
        try:
            import httpx

            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.config.endpoint_url}/sae",
                    headers=headers,
                    json={
                        "text": text,
                        "top_k": top_k,
                        "threshold": self.config.threshold,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return SAEResult(
                    text=text,
                    features=data.get("features", []),
                    activations=data.get("activations", []),
                    dense_activations=np.array(data.get("dense_activations", []))
                    if data.get("dense_activations")
                    else None,
                    sparsity=data.get("sparsity", 0.0),
                    metadata=data.get("metadata", {}),
                )
        except Exception as e:
            logger.error(f"Remote SAE call failed: {e}")
            raise

    def _run_local_sae(self, text: str, top_k: int) -> SAEResult:
        """
        Run local SAE inference.

        In production, this would load a local SAE model (e.g., via HuggingFace
        or a custom ONNX runtime) and extract features from text embeddings.

        For now, this is a placeholder that returns synthetic features for
        testing the steering pipeline. Replace with actual local inference.
        """
        # TODO: Implement actual local SAE inference
        # Options:
        # 1. Use HuggingFace transformers + SAE model
        # 2. Use ONNX runtime for optimized inference
        # 3. Call local inference server (vLLM/SGLang with SAE support)

        logger.debug(f"Local SAE called for text of length {len(text)}")
        return self._fallback_result(text)

    def _fallback_result(self, text: str) -> SAEResult:
        """
        Fallback when SAE is unavailable.

        This is a mock implementation that simulates what a real SAE would return.
        It detects Java idioms heuristically and returns synthetic features.

        In production, you would:
        1. Train your own SAE on model's hidden states
        2. Use a public SAE for your base model (when available)
        3. Or call a hosted SAE inference service
        """
        from .java_idiom_detector import JavaIdiomHeuristics

        heuristics = JavaIdiomHeuristics()
        idiom_features = heuristics.detect_features(text)

        # Convert detected patterns to synthetic features
        features = []
        activations = []

        for feature_id, confidence in idiom_features.items():
            features.append(feature_id)
            activations.append(confidence)

        # Add some noise to simulate real SAE behavior
        n_extra = min(5, self.config.top_k - len(features))
        for i in range(n_extra):
            features.append(1000 + i)  # Neutral features
            activations.append(0.05)

        # Sort by activation
        sorted_pairs = sorted(zip(features, activations), key=lambda x: -x[1])
        features = [f for f, _ in sorted_pairs]
        activations = [a for _, a in sorted_pairs]

        sparsity = 1.0 - (len(features) / self.config.top_k)

        return SAEResult(
            text=text,
            features=features[:top_k],
            activations=activations[:top_k],
            sparsity=sparsity,
            metadata={"source": "fallback", "idiom_count": len(idiom_features)},
        )

    def _update_feature_stats(self, result: SAEResult) -> None:
        """Track feature statistics for analysis"""
        for f, a in zip(result.features, result.activations):
            if f not in self._feature_stats:
                self._feature_stats[f] = []
            self._feature_stats[f].append(a)

    def get_feature_frequency(self, feature_id: int) -> float:
        """Get how often a feature appears across all inputs"""
        if feature_id not in self._feature_stats:
            return 0.0
        return len(self._feature_stats[feature_id])

    def clear_cache(self) -> None:
        """Clear the feature cache"""
        self._cache.clear()
        self._feature_stats.clear()


def create_sae_client(config: Optional[SAEConfig] = None) -> SAEClient:
    """Factory function to create SAE client"""
    return SAEClient(config=config)


# Feature index conventions for PortKit SAE
# These are placeholder IDs - actual SAE training determines real indices
JAVA_FORGE_FEATURE_BASE = 1000
JAVA_CLASS_PATTERN_BASE = 2000
JAVA_API_PATTERN_BASE = 3000
BEDROCK_DESIRED_BASE = 4000

FEATURE_NAMES = {
    # Java Forge patterns (suppress these)
    1000: "java_extends_keyword",
    1001: "java_implements_keyword",
    1002: "java_override_annotation",
    1003: "java_subscribe_event",
    1004: "java_mod_annotations",
    1005: "java_item_properties",
    1006: "java_block_properties",
    1007: "java_entity_superclass",
    1008: "java_capability_pattern",
    1009: "java_registry_pattern",
    # Java class structure patterns
    2000: "java_class_declaration",
    2001: "java_import_statement",
    2002: "java_package_declaration",
    2003: "java_method_signature",
    2004: "java_field_declaration",
    2005: "java_constructor",
    2006: "java_inner_class",
    2007: "java_enum_usage",
    2008: "java_interface_usage",
    2009: "java_abstract_class",
    # Java API patterns
    3000: "forge_event_handlers",
    3001: "minecraft_server_api",
    3002: "level_api_calls",
    3003: "entity_api_calls",
    3004: "block_api_calls",
    3005: "item_api_calls",
    3006: "forge_registries",
    3007: "client_side_handlers",
    3008: "server_side_handlers",
    3009: "network_packet_pattern",
    # Bedrock desired patterns (encourage these)
    4000: "bedrock_js_syntax",
    4001: "bedrock_event_subscribe",
    4002: "bedrock_dynamic_property",
    4003: "bedrock_component_system",
    4004: "bedrock_world_import",
    4005: "bedrock_system_run",
    4006: "bedrock_entity_spawn",
    4007: "bedrock_block_set_type",
    4008: "bedrock_player_interaction",
    4009: "bedrock_json_format",
}


def get_feature_name(feature_id: int) -> str:
    """Get human-readable name for a feature"""
    return FEATURE_NAMES.get(feature_id, f"unknown_feature_{feature_id}")
