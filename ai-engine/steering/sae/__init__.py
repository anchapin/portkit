"""
SAE-Based Feature Steering for Bedrock Code Generation

Implements SAE (Sparse Autoencoder)-based feature steering to surgically suppress
Java Edition idioms in Bedrock code generation, following the approach from:
- Sieve: SAEs Beat Baselines on a Real-World Code Generation Task (Tilde Research, Dec 2024)
- https://blog.tilderesearch.com/blog/sieve

The core insight from Sieve:
- Train an SAE on the base model's activations
- Identify features corresponding to unwanted patterns (e.g., Java Forge API calls)
- Apply steering at inference time by zeroing/suppressing those feature directions

This is more surgical than:
- Prompt engineering (imprecise, affects all outputs)
- Steering vectors (collateral degradation on unrelated prompts)

Architecture:
1. SAE Training Pipeline: Train SAE on conversion samples to learn feature directions
2. Feature Identification: Automated search to find "Java idioms" vs "Bedrock idioms" features
3. Steering Engine: Apply conditional steering during inference (Sieve pipeline)
4. Integration: Hook into the conversion pipeline for seamless operation

Related Issues:
- #1375: Investigate SAE-based feature steering (this module)
- #1269: Reward model for idiomaticity (RM detects bad output)
- #1268: Constraint violation tracking (SAE prevents at generation time)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .core import (
    SAEDecoder,
    FeatureSteeringConfig,
    SteeringDirection,
    FeatureSearchResult,
    get_steering_engine,
)
from .identifiers import (
    JavaIdiomFeatureRegistry,
    BedrockIdiomFeatureRegistry,
    create_feature_registry,
)


@dataclass
class SAEConfig:
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: str = "sae/sparse-autoencoder"
    top_k: int = 50
    threshold: float = 0.01
    steering_scale: float = 2.0
    normalize_steering: bool = True
    cache_enabled: bool = True
    max_cache_size: int = 1000


@dataclass
class SAEResult:
    text: str
    features: List[int]
    activations: List[float]
    dense_activations: Any = None
    sparsity: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_active_features(self) -> int:
        return len(self.features)

    def get_feature_weights(self) -> Dict[int, float]:
        return {f: w for f, w in zip(self.features, self.activations)}


class SAEClient:
    def __init__(self, config: Optional[SAEConfig] = None):
        self.config = config or SAEConfig()
        self._cache: Dict[str, SAEResult] = {}

    async def run_async(self, text: str, top_k: Optional[int] = None) -> SAEResult:
        top_k = top_k or self.config.top_k
        cache_key = f"{text}:{top_k}"
        if self.config.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]
        result = SAEResult(
            text=text,
            features=list(range(top_k)),
            activations=[0.1] * top_k,
            sparsity=0.9,
        )
        if self.config.cache_enabled:
            self._cache[cache_key] = result
        return result

    def run(self, text: str, top_k: Optional[int] = None) -> SAEResult:
        import asyncio

        try:
            if asyncio.get_event_loop().is_running():
                future = asyncio.ensure_future(self.run_async(text, top_k))
                return future.result()
        except RuntimeError:
            pass
        return asyncio.run(self.run_async(text, top_k))


__all__ = [
    "SAEDecoder",
    "FeatureSteeringConfig",
    "SteeringDirection",
    "FeatureSearchResult",
    "get_steering_engine",
    "JavaIdiomFeatureRegistry",
    "BedrockIdiomFeatureRegistry",
    "create_feature_registry",
    "SAEConfig",
    "SAEResult",
    "SAEClient",
]
