"""
SAE Core Module - Core data structures and interfaces for SAE-based steering.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class SteeringDirection(str, Enum):
    """Direction of steering intervention."""

    SUPPRESS = "suppress"  # Zero out the feature (for Java idioms)
    AMPLIFY = "amplify"  # Boost the feature (for Bedrock idioms)
    NEUTRAL = "neutral"  # No intervention


@dataclass
class FeatureSteeringConfig:
    """Configuration for feature steering."""

    steering_strength: float = 1.0  # Multiplier for steering magnitude
    feature_threshold: float = 0.1  # Minimum activation to consider for steering
    enable_conditional: bool = True  # Only steer during Bedrock generation
    steering_mode: SteeringDirection = SteeringDirection.SUPPRESS

    # SAE model configuration
    sae_model_path: Optional[str] = None
    sae_hidden_size: int = 2048  # SAE compressed hidden dimension
    sae_k_factor: int = 4  # Sparsity factor (k-sparse autoencoder)

    # Inference settings
    use_exact_inference: bool = True  # Use exact activation steering vs approximation
    batch_steering: bool = True  # Batch multiple steering operations


@dataclass
class FeatureSearchResult:
    """Result from automated feature search."""

    feature_index: int
    feature_activation: float
    steering_direction: SteeringDirection
    confidence: float  # 0-1 confidence in the feature's association
    description: str
    example_activation: float
    pattern_associated: str
    is_java_idiom: bool


class SAEDecoder:
    """
    Decoder for Sparse Autoencoder features.

    An SAE learns to compress activations into a sparse representation where
    each feature corresponds to a human-interpretable concept. This decoder
    provides the interface for:
    - Encoding: project activations to SAE space
    - Decoding: project SAE features back to model space
    - Steering: modify specific features before decoding

    The steering is applied as:
        modified_activations = decoder(encoder(activations) * steering_mask)

    Where steering_mask scales/suppresses specific feature dimensions.
    """

    def __init__(self, config: Optional[FeatureSteeringConfig] = None):
        self.config = config or FeatureSteeringConfig()
        self._decoder_weights: Optional[Dict[int, List[float]]] = None
        self._feature_mean: Optional[List[float]] = None
        self._is_fitted = False

    def fit(self, activations: List[List[float]]) -> None:
        """
        Fit the SAE decoder to example activations.

        In a production implementation, this would train the SAE using:
        - k-sparse autoencoder loss
        - L1 regularization for sparsity
        - Reconstruction loss

        For this investigation, we store statistics needed for steering.

        Args:
            activations: List of activation vectors from the model
        """
        if not activations:
            raise ValueError("Must provide at least one activation vector")

        # Compute feature statistics across all activations
        n_features = len(activations[0])
        n_samples = len(activations)

        # Mean activation per feature
        self._feature_mean = [sum(a[i] for a in activations) / n_samples for i in range(n_features)]

        # Initialize decoder weights (placeholder - would be learned)
        self._decoder_weights = {i: [0.0] * n_features for i in range(n_features)}

        self._is_fitted = True
        logger.info(f"SAE decoder fitted with {n_features} features from {n_samples} samples")

    def encode(self, activations: List[float]) -> List[float]:
        """
        Encode activations to SAE feature space.

        Args:
            activations: Raw model activations

        Returns:
            SAE feature activations (sparse)
        """
        if not self._is_fitted:
            raise RuntimeError("SAE decoder must be fitted before encoding")

        # Simple linear projection + ReLU for sparsity
        # In production: learned encoder weights
        features = []
        for i in range(len(activations)):
            val = activations[i] - (self._feature_mean[i] if self._feature_mean else 0.0)
            val = max(0.0, val)  # ReLU for sparsity
            features.append(val)

        # Apply k-sparse top-k selection
        if self.config.sae_k_factor > 0 and len(features) > 0:
            k = min(self.config.sae_k_factor, len(features) - 1)
            threshold = sorted(features, reverse=True)[k]
            features = [f if f >= threshold else 0.0 for f in features]

        return features

    def decode(self, features: List[float]) -> List[float]:
        """
        Decode SAE features back to model activation space.

        Args:
            features: Sparse SAE features

        Returns:
            Model activations
        """
        if not self._is_fitted:
            raise RuntimeError("SAE decoder must be fitted before decoding")

        n = len(features)
        activations = [0.0] * n

        for i in range(n):
            if features[i] != 0.0 and self._decoder_weights:
                # Decode: multiply feature by decoder column
                for j in range(n):
                    activations[j] += features[i] * self._decoder_weights[i][j]

        return activations

    def steer(
        self,
        activations: List[float],
        steering_mask: Dict[int, float],
    ) -> List[float]:
        """
        Apply steering to activations.

        Args:
            activations: Raw model activations
            steering_mask: Dict mapping feature index to steering multiplier.
                         Values > 1 amplify, < 1 suppress, = 0 zero out

        Returns:
            Steered activations
        """
        features = self.encode(activations)

        # Apply steering mask
        steered_features = [features[i] * steering_mask.get(i, 1.0) for i in range(len(features))]

        return self.decode(steered_features)

    def get_feature_stats(self) -> Dict[str, Any]:
        """Get statistics about fitted features."""
        if not self._is_fitted:
            return {"status": "not_fitted"}

        return {
            "status": "fitted",
            "n_features": len(self._feature_mean) if self._feature_mean else 0,
            "feature_means": self._feature_mean[:10] if self._feature_mean else [],
            "config": {
                "steering_strength": self.config.steering_strength,
                "sae_k_factor": self.config.sae_k_factor,
            },
        }


class FeatureSteerer:
    """
    Main steering engine that applies SAE-based feature steering.

    Integrates with the inference pipeline to apply conditional steering
    only during Bedrock code generation.
    """

    def __init__(
        self,
        decoder: Optional[SAEDecoder] = None,
        config: Optional[FeatureSteeringConfig] = None,
    ):
        self.decoder = decoder or SAEDecoder(config)
        self.config = self.decoder.config
        self._steering_mask: Dict[int, float] = {}
        self._is_active = False

    def set_steering_targets(
        self,
        feature_indices: List[int],
        direction: SteeringDirection,
        strength: float = 1.0,
    ) -> None:
        """
        Configure which features to steer and in what direction.

        Args:
            feature_indices: List of feature indices to steer
            direction: SUPPRESS (Java idioms) or AMPLIFY (Bedrock idioms)
            strength: Steering strength multiplier
        """
        self._steering_mask = {}

        for idx in feature_indices:
            if direction == SteeringDirection.SUPPRESS:
                # Suppress: scale down or zero out
                self._steering_mask[idx] = 0.0 if strength >= 1.0 else (1.0 - strength)
            elif direction == SteeringDirection.AMPLIFY:
                # Amplify: scale up
                self._steering_mask[idx] = 1.0 + strength
            else:
                self._steering_mask[idx] = 1.0

        self._is_active = True
        logger.info(
            f"Set steering targets: {len(feature_indices)} features, "
            f"direction={direction.value}, strength={strength}"
        )

    def steer_activations(
        self,
        activations: List[float],
    ) -> List[float]:
        """
        Apply steering to given activations.

        Args:
            activations: Model activations

        Returns:
            Steered activations
        """
        if not self._is_active or not self._steering_mask:
            return activations

        return self.decoder.steer(activations, self._steering_mask)

    def activate(self) -> None:
        """Activate steering for next inference call."""
        self._is_active = True
        logger.debug("Feature steering activated")

    def deactivate(self) -> None:
        """Deactivate steering."""
        self._is_active = False
        logger.debug("Feature steering deactivated")

    def is_active(self) -> bool:
        """Check if steering is currently active."""
        return self._is_active


def get_steering_engine(
    config: Optional[FeatureSteeringConfig] = None,
) -> FeatureSteerer:
    """Factory function to get a steering engine instance."""
    return FeatureSteerer(config=config)
