"""
Sieve Pipeline - Integration of SAE steering with code generation.

Implements the Sieve pipeline from Tilde Research's blog post:
https://blog.tilderesearch.com/blog/sieve

The Sieve approach:
1. Collect activation samples from the model during generation
2. Pass through SAE encoder to get sparse features
3. Identify target features via automated search
4. Apply steering by modifying features before decoder
5. Continue generation with steered activations

This module provides:
- SievePipeline: Main integration with conversion crew
- ActivationCollector: Collects activations during generation
- SteeringContext: Manages conditional steering (Bedrock vs general)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from .core import (
    FeatureSteerer,
    FeatureSteeringConfig,
    SteeringDirection,
)
from .identifiers import (
    JavaIdiomFeatureRegistry,
    BedrockIdiomFeatureRegistry,
)

logger = logging.getLogger(__name__)


class GenerationMode(str, Enum):
    """Mode for code generation."""

    BEDROCK_CONVERSION = "bedrock_conversion"
    GENERAL = "general"


@dataclass
class SievePipelineConfig:
    """Configuration for the Sieve steering pipeline."""

    enable_steering: bool = True
    steering_strength: float = 1.0
    conditional_steering: bool = True  # Only steer in BEDROCK_CONVERSION mode
    collect_activations: bool = True  # Collect activations for analysis
    auto_identify_features: bool = True  # Auto-identify features vs manual config

    # SAE configuration
    sae_hidden_size: int = 2048
    sae_k_factor: int = 4

    # Feature thresholds
    java_suppression_threshold: float = 0.7  # Min confidence to suppress
    bedrock_amplification_threshold: float = 0.7  # Min confidence to amplify

    # Logging
    log_activations: bool = False
    log_steering_events: bool = True


@dataclass
class ActivationSample:
    """A single activation sample from the model."""

    features: List[float]
    position: int  # Token position in sequence
    mode: GenerationMode
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SteeringEvent:
    """Records a steering intervention."""

    timestamp: str
    feature_index: int
    original_activation: float
    steered_activation: float
    direction: SteeringDirection
    success: bool


class SievePipeline:
    """
    Implements the Sieve SAE-steering pipeline for code generation.

    Integration points:
    1. Called before LLM generation to configure steering
    2. Intercepts activations during generation (via callback)
    3. Applies steering to identified features
    4. Returns modified activations to the model

    Usage:
        sieve = SievePipeline(enable_steering=True)
        sieve.configure_for_bedrock_conversion()
        # ... run conversion ...
        results = sieve.get_steering_summary()
    """

    def __init__(
        self,
        config: Optional[SievePipelineConfig] = None,
        steering_config: Optional[FeatureSteeringConfig] = None,
    ):
        self.config = config or SievePipelineConfig()
        self.steering_config = steering_config or FeatureSteeringConfig(
            steering_strength=self.config.steering_strength,
            sae_hidden_size=self.config.sae_hidden_size,
            sae_k_factor=self.config.sae_k_factor,
        )

        self.steerer = FeatureSteerer(config=self.steering_config)
        self.java_registry = JavaIdiomFeatureRegistry()
        self.bedrock_registry = BedrockIdiomFeatureRegistry()

        self._activation_samples: List[ActivationSample] = []
        self._steering_events: List[SteeringEvent] = []
        self._current_mode = GenerationMode.GENERAL
        self._is_configured = False

    def configure_for_bedrock_conversion(self) -> None:
        """
        Configure steering specifically for Bedrock code generation.

        This sets up suppression of Java idioms and amplification of
        Bedrock idioms.
        """
        logger.info("Configuring Sieve pipeline for Bedrock conversion")

        java_targets = self.java_registry.get_suppression_targets()
        bedrock_targets = self.bedrock_registry.get_amplification_targets()
        logger.debug(
            f"Steering targets: {len(java_targets)} suppress, {len(bedrock_targets)} amplify"
        )

        if java_targets:
            self.steerer.set_steering_targets(
                java_targets,
                SteeringDirection.SUPPRESS,
                strength=self.config.steering_strength,
            )
            logger.info(f"Set {len(java_targets)} Java idiom suppression targets")

        self._current_mode = GenerationMode.BEDROCK_CONVERSION
        self._is_configured = True

        if self.config.enable_steering:
            self.steerer.activate()

    def configure_for_general(self) -> None:
        """
        Configure for general-purpose generation (steering disabled).
        """
        logger.info("Configuring Sieve pipeline for general generation")
        self.steerer.deactivate()
        self._current_mode = GenerationMode.GENERAL
        self._is_configured = True

    def steer_activations(
        self,
        activations: List[float],
        mode: Optional[GenerationMode] = None,
    ) -> List[float]:
        """
        Apply steering to activations.

        Args:
            activations: Model activations
            mode: Override generation mode

        Returns:
            Steered activations (or original if steering disabled)
        """
        effective_mode = mode or self._current_mode

        if not self.config.enable_steering:
            return activations

        if self.config.conditional_steering and effective_mode != GenerationMode.BEDROCK_CONVERSION:
            return activations

        if not self._is_configured:
            logger.warning("Sieve pipeline not configured, skipping steering")
            return activations

        return self.steerer.steer_activations(activations)

    def collect_activation(
        self,
        features: List[float],
        position: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Collect an activation sample for analysis.

        Args:
            features: Activation features
            position: Position in sequence
            metadata: Additional metadata
        """
        if not self.config.collect_activations:
            return

        sample = ActivationSample(
            features=features,
            position=position,
            mode=self._current_mode,
            metadata=metadata or {},
        )
        self._activation_samples.append(sample)

    def record_steering_event(
        self,
        feature_index: int,
        original: float,
        steered: float,
        direction: SteeringDirection,
        success: bool = True,
    ) -> None:
        """Record a steering event for analysis."""
        if not self.config.log_steering_events:
            return

        event = SteeringEvent(
            timestamp=datetime.now().isoformat(),
            feature_index=feature_index,
            original_activation=original,
            steered_activation=steered,
            direction=direction,
            success=success,
        )
        self._steering_events.append(event)

    def get_steering_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for steering analysis.

        Returns:
            Dict with steering metrics
        """
        return {
            "is_configured": self._is_configured,
            "current_mode": self._current_mode.value,
            "steering_enabled": self.config.enable_steering,
            "steering_active": self.steerer.is_active(),
            "activation_samples": len(self._activation_samples),
            "steering_events": len(self._steering_events),
            "java_suppression_targets": len(self.java_registry.get_suppression_targets()),
            "bedrock_amplification_targets": len(self.bedrock_registry.get_amplification_targets()),
            "config": {
                "steering_strength": self.config.steering_strength,
                "conditional_steering": self.config.conditional_steering,
                "sae_hidden_size": self.config.sae_hidden_size,
                "sae_k_factor": self.config.sae_k_factor,
            },
        }

    def reset(self) -> None:
        """Reset collected data and deactivate steering."""
        self._activation_samples.clear()
        self._steering_events.clear()
        self._is_configured = False
        self.steerer.deactivate()
        logger.info("Sieve pipeline reset")


class ActivationCollector:
    """
    Utility class for collecting activations during LLM generation.

    This would integrate with the LLM inference stack to capture
    intermediate activations for SAE processing.

    Integration requires:
    - Hook into model's forward pass
    - Capture residual stream activations
    - Pass to SievePipeline for steering
    """

    def __init__(self, pipeline: SievePipeline):
        self.pipeline = pipeline
        self._collecting = False

    def start_collection(self) -> None:
        """Start collecting activations."""
        self._collecting = True
        logger.debug("Activation collection started")

    def stop_collection(self) -> None:
        """Stop collecting activations."""
        self._collecting = False
        logger.debug("Activation collection stopped")

    def on_activation(
        self,
        activations: List[float],
        position: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Callback for activation interception.

        Args:
            activations: Model activations
            position: Token position
            metadata: Additional context
        """
        if not self._collecting:
            return

        self.pipeline.collect_activation(activations, position, metadata)

        if self.pipeline.config.enable_steering:
            steered = self.pipeline.steer_activations(activations)
            if steered != activations:
                for i, (orig, new) in enumerate(zip(activations, steered)):
                    if orig != new:
                        self.pipeline.record_steering_event(
                            feature_index=i,
                            original=orig,
                            steered=new,
                            direction=SteeringDirection.SUPPRESS
                            if new < orig
                            else SteeringDirection.AMPLIFY,
                        )


def create_sieve_pipeline(
    enable_steering: bool = True,
    steering_strength: float = 1.0,
) -> SievePipeline:
    """
    Factory function to create a configured Sieve pipeline.

    Args:
        enable_steering: Whether to enable SAE steering
        steering_strength: Strength of steering intervention

    Returns:
        Configured SievePipeline instance
    """
    config = SievePipelineConfig(
        enable_steering=enable_steering,
        steering_strength=steering_strength,
        conditional_steering=True,
        collect_activations=True,
    )

    return SievePipeline(config=config)
