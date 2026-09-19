"""
Steering Vector Computation and Application.

Implements the Sieve pipeline for feature steering:
1. Extract features from SAE for positive/negative examples
2. Compute steering vectors from feature differences
3. Apply steering at inference time via residual stream manipulation

Based on: "Sieve: SAEs Beat Baselines on a Real-World Task"
https://blog.tilderesearch.com/blog/sieve

Key insight: Instead of suppressing features directly, we compute:
    steering_vector = sum(w_i * feature_i) for i in java_features

And subtract this from the residual stream during generation.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SteeringMode(str, Enum):
    """How to apply steering"""

    SUPPRESS = "suppress"  # Subtract steering vector (reduce features)
    AMPLIFY = "amplify"  # Add steering vector (enhance features)
    REPLACE = "replace"  # Replace activations with steering vector


@dataclass
class SteeringVector:
    """A computed steering vector for feature manipulation"""

    name: str
    feature_ids: List[int]
    weights: np.ndarray  # Same length as feature_ids
    steering_direction: np.ndarray  # The actual steering vector
    magnitude: float
    mode: SteeringMode
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_features(
        cls,
        name: str,
        feature_activations: Dict[int, float],
        mode: SteeringMode = SteeringMode.SUPPRESS,
        normalize: bool = True,
    ) -> "SteeringVector":
        """
        Create a steering vector from feature activations.

        Args:
            name: Name for this steering vector
            feature_activations: Dict mapping feature_id -> activation
            mode: SUPPRESS (subtract) or AMPLIFY (add)
            normalize: Whether to normalize the steering vector

        Returns:
            SteeringVector ready for application
        """
        feature_ids = list(feature_activations.keys())
        weights = np.array(list(feature_activations.values()))

        # Convert to steering direction
        if mode == SteeringMode.SUPPRESS:
            direction = -weights  # Negative to suppress
        else:
            direction = weights

        if normalize:
            norm = np.linalg.norm(direction)
            if norm > 1e-8:
                direction = direction / norm

        return cls(
            name=name,
            feature_ids=feature_ids,
            weights=weights,
            steering_direction=direction,
            magnitude=float(np.linalg.norm(direction)),
            mode=mode,
        )

    def scale(self, scale: float) -> "SteeringVector":
        """Scale the steering magnitude"""
        return SteeringVector(
            name=self.name,
            feature_ids=self.feature_ids,
            weights=self.weights,
            steering_direction=self.steering_direction * scale,
            magnitude=self.magnitude * scale,
            mode=self.mode,
            metadata=self.metadata.copy(),
        )


@dataclass
class SteeringConfig:
    """Configuration for steering application"""

    steering_scale: float = 2.0  # Default steering magnitude
    steering_mode: SteeringMode = SteeringMode.SUPPRESS
    feature_threshold: float = 0.1  # Minimum activation to include in steering
    max_features: int = 50  # Maximum features to include
    apply_to_layers: List[int] = field(default_factory=lambda: [-1])  # Which layers to apply to
    normalize_steering: bool = True
    clamp_activations: bool = True
    clamp_min: float = -5.0
    clamp_max: float = 5.0


class SteeringVectorStore:
    """
    Stores and manages pre-computed steering vectors.

    In production, these would be trained on actual model activations
    and stored in a database or file.
    """

    def __init__(self):
        self._vectors: Dict[str, SteeringVector] = {}
        self._initialize_default_vectors()

    def _initialize_default_vectors(self) -> None:
        """Initialize with pre-computed steering vectors for Java idiom suppression"""
        # Java Forge API suppression vector
        java_forge_features = {
            1003: 0.8,  # Minecraft.getInstance()
            1004: 0.7,  # isClientSide
            1005: 0.7,  # isServerSide
            1006: 0.9,  # addFreshEntity
            1007: 0.6,  # getBlockState
            1008: 0.95,  # @SubscribeEvent
            1009: 0.8,  # register()
            1010: 0.8,  # EntityType.register
        }

        self._vectors["java_forge_suppress"] = SteeringVector.from_features(
            name="java_forge_suppress",
            feature_activations=java_forge_features,
            mode=SteeringMode.SUPPRESS,
        )

        # Java class structure suppression
        java_class_features = {
            2000: 0.9,  # extends Item
            2001: 0.8,  # extends Block
            2002: 0.9,  # extends Entity
            2005: 0.7,  # public class
            2006: 0.5,  # private field
        }

        self._vectors["java_class_suppress"] = SteeringVector.from_features(
            name="java_class_suppress",
            feature_activations=java_class_features,
            mode=SteeringMode.SUPPRESS,
        )

        # Bedrock desired features (amplify)
        bedrock_features = {
            4000: 0.9,  # bedrock_js_syntax
            4001: 0.95,  # bedrock_event_subscribe
            4002: 0.8,  # bedrock_dynamic_property
            4003: 0.85,  # bedrock_component_system
        }

        self._vectors["bedrock_amplify"] = SteeringVector.from_features(
            name="bedrock_amplify",
            feature_activations=bedrock_features,
            mode=SteeringMode.AMPLIFY,
        )

    def get(self, name: str) -> Optional[SteeringVector]:
        """Get a steering vector by name"""
        return self._vectors.get(name)

    def add(self, vector: SteeringVector) -> None:
        """Add a new steering vector"""
        self._vectors[vector.name] = vector

    def list_vectors(self) -> List[str]:
        """List all available steering vectors"""
        return list(self._vectors.keys())

    def compute_java_suppression_vector(
        self,
        idiom_detections: Dict[int, float],
        scale: float = 2.0,
    ) -> SteeringVector:
        """
        Compute a custom suppression vector from idiom detections.

        Args:
            idiom_detections: Dict mapping feature_id -> confidence
            scale: Steering magnitude

        Returns:
            Custom steering vector for these idioms
        """
        vector = SteeringVector.from_features(
            name=f"custom_java_suppress_{hash(str(idiom_detections))}",
            feature_activations=idiom_detections,
            mode=SteeringMode.SUPPRESS,
        )
        return vector.scale(scale)


class FeatureSteeringEngine:
    """
    Main engine for applying feature steering during inference.

    This engine intercepts model activations and applies steering vectors
    to manipulate the model's output.

    Usage:
        engine = FeatureSteeringEngine(config)
        steered_output = engine.apply_steering(
            hidden_states=activations,
            steering_vectors=[java_suppress_vector],
        )
    """

    def __init__(
        self,
        config: Optional[SteeringConfig] = None,
        vector_store: Optional[SteeringVectorStore] = None,
    ):
        self.config = config or SteeringConfig()
        self.vector_store = vector_store or SteeringVectorStore()
        self._stats = {
            "applications": 0,
            "total_magnitude": 0.0,
            "layers_modified": set(),
        }

    def apply_steering(
        self,
        hidden_states: np.ndarray,
        steering_vector: SteeringVector,
        layer_idx: Optional[int] = None,
        scale: Optional[float] = None,
    ) -> np.ndarray:
        """
        Apply a steering vector to hidden states.

        Args:
            hidden_states: Model hidden states (shape: [batch, seq_len, hidden_dim])
            steering_vector: Pre-computed steering vector
            layer_idx: Which layer this applies to (for logging)
            scale: Override steering scale

        Returns:
            Modified hidden states with steering applied
        """
        scale = scale or self.config.steering_scale

        # Steering vector should be 1D or match last dim
        if steering_vector.steering_direction.ndim == 1:
            steering = steering_vector.steering_direction * scale
        else:
            steering = steering_vector.steering_direction * scale

        # Apply to all positions (broadcasting handles batch/seq dims)
        modified = hidden_states + steering

        if self.config.clamp_activations:
            modified = np.clip(modified, self.config.clamp_min, self.config.clamp_max)

        self._stats["applications"] += 1
        self._stats["total_magnitude"] += abs(scale)
        if layer_idx is not None:
            self._stats["layers_modified"].add(layer_idx)

        return modified

    def apply_multiple_steering(
        self,
        hidden_states: np.ndarray,
        steering_vectors: List[SteeringVector],
        layer_idx: Optional[int] = None,
    ) -> np.ndarray:
        """
        Apply multiple steering vectors simultaneously.

        Combines steering vectors additively.
        """
        combined_steering = np.zeros_like(hidden_states)

        for sv in steering_vectors:
            if sv.steering_direction.ndim == 1:
                # Feature dimension steering
                steering = sv.steering_direction * self.config.steering_scale
            else:
                steering = sv.steering_direction * self.config.steering_scale

            combined_steering += steering

        modified = hidden_states + combined_steering

        if self.config.clamp_activations:
            modified = np.clip(modified, self.config.clamp_min, self.config.clamp_max)

        self._stats["applications"] += len(steering_vectors)
        if layer_idx is not None:
            self._stats["layers_modified"].add(layer_idx)

        return modified

    def compute_steering_from_text(
        self,
        text: str,
        idiom_features: Dict[int, float],
        scale: float = 2.0,
    ) -> SteeringVector:
        """
        Compute steering vector from detected idiom features.

        Args:
            text: Source text for the steering vector
            idiom_features: Features to suppress
            scale: Steering magnitude

        Returns:
            Steering vector ready for application
        """
        return self.vector_store.compute_java_suppression_vector(
            idiom_detections=idiom_features,
            scale=scale,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get steering statistics"""
        return {
            "applications": self._stats["applications"],
            "avg_magnitude": (
                self._stats["total_magnitude"] / self._stats["applications"]
                if self._stats["applications"] > 0
                else 0.0
            ),
            "layers_modified": list(self._stats["layers_modified"]),
        }


# Singleton store for the steering engine
_steering_engine: Optional[FeatureSteeringEngine] = None


def get_steering_engine() -> FeatureSteeringEngine:
    """Get singleton steering engine instance"""
    global _steering_engine
    if _steering_engine is None:
        _steering_engine = FeatureSteeringEngine()
    return _steering_engine


def configure_steering_engine(config: SteeringConfig) -> FeatureSteeringEngine:
    """Configure and return singleton steering engine"""
    global _steering_engine
    _steering_engine = FeatureSteeringEngine(config=config)
    return _steering_engine
