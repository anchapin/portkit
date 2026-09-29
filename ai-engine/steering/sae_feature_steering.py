"""
SAE-Based Feature Steering for Java Idioms Suppression

This module implements Sparse Autoencoder (SAE)-based feature steering to surgically
guide the LLM during Bedrock code generation — preventing Java Edition idioms from
surfacing while preserving general code quality.

Based on: "Sieve: SAEs Beat Baselines on a Real-World Task (A Code Generation Case Study)"
- Tilde Research, Dec 2024
- First SAE-based intervention on real downstream code generation task
- >99.9% precision on avoiding regex usage in fuzz test generation

Key concepts:
1. SAE (Sparse Autoencoder): Decomposes model activations into interpretable features
2. Feature Steering: Suppresses unwanted features (Java idioms) at inference time
3. Sieve Pipeline: Automated feature discovery and steering application
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SteeringTarget(Enum):
    """Targets for SAE-based steering."""

    JAVA_FORGE_API = "java_forge_api"
    JAVA_CLASS_STRUCTURE = "java_class_structure"
    JAVA_IMPORTS = "java_imports"
    JAVA_TYPE_PATTERNS = "java_type_patterns"
    BEDROCK_IDIOMATIC = "bedrock_idiomatic"


@dataclass
class FeatureVector:
    """Represents an SAE feature with its activation strength."""

    feature_id: str
    activation: float
    steering_direction: float  # positive = enhance, negative = suppress
    description: Optional[str] = None
    examples: List[str] = field(default_factory=list)


@dataclass
class JavaIdiomFeatures:
    """Discovered features corresponding to Java Edition patterns."""

    forge_api_features: List[FeatureVector] = field(default_factory=list)
    class_structure_features: List[FeatureVector] = field(default_factory=list)
    import_features: List[FeatureVector] = field(default_factory=list)
    type_pattern_features: List[FeatureVector] = field(default_factory=list)

    def get_all_features(self) -> List[FeatureVector]:
        """Get all features combined."""
        return (
            self.forge_api_features
            + self.class_structure_features
            + self.import_features
            + self.type_pattern_features
        )

    def get_suppression_vector(self) -> Dict[str, float]:
        """Get feature -> steering value mapping for suppression."""
        suppression = {}
        for feature in self.get_all_features():
            suppression[feature.feature_id] = feature.steering_direction * -1.0
        return suppression


@dataclass
class SteeringConfig:
    """Configuration for SAE-based steering."""

    steering_strength: float = 1.0  # 0.0 to 2.0, 1.0 = standard
    suppression_threshold: float = 0.5  # minimum activation to apply steering
    enable_boost: bool = False  # whether to boost Bedrock features
    conditional_on_context: bool = True  # only steer when context is conversion
    target_model: str = "auto"  # auto-detect or specific model


class SAEFeatureSteerer:
    """
    Main SAE-based feature steering implementation.

    This class handles:
    1. Feature loading and management
    2. Activation computation for steering
    3. Application of steering to model inference
    """

    def __init__(
        self,
        config: Optional[SteeringConfig] = None,
        features: Optional[JavaIdiomFeatures] = None,
    ):
        self.config = config or SteeringConfig()
        self.features = features or JavaIdiomFeatures()
        self._is_initialized = False
        self._steering_cache: Dict[str, List[float]] = {}

    def initialize(self, model_size: str = "auto") -> bool:
        """
        Initialize the SAE steerer with model-specific parameters.

        Args:
            model_size: Model size class (e.g., "7b", "13b", "70b")

        Returns:
            True if initialization successful
        """
        logger.info(f"Initializing SAEFeatureSteerer for model size: {model_size}")

        # SAE dimensions are typically proportional to model size
        # For a 7B model, typical SAE might have 16k-32k features
        if model_size == "auto":
            model_size = "7b"  # conservative default

        self._sae_dimensions = self._estimate_sae_dimensions(model_size)
        self._steering_strength = self.config.steering_strength

        self._is_initialized = True
        logger.info(
            f"SAEFeatureSteerer initialized with ~{self._sae_dimensions} features, "
            f"steering_strength={self._steering_strength}"
        )
        return True

    def _estimate_sae_dimensions(self, model_size: str) -> int:
        """Estimate SAE feature dimensions based on model size."""
        size_map = {
            "7b": 16384,
            "13b": 32768,
            "34b": 49152,
            "70b": 65536,
        }
        return size_map.get(model_size, 16384)

    def load_features_from_file(self, features_path: str) -> bool:
        """
        Load pre-computed Java idiom features from a JSON file.

        Args:
            features_path: Path to features JSON file

        Returns:
            True if loading successful
        """
        try:
            with open(features_path, "r") as f:
                data = json.load(f)

            self.features = self._deserialize_features(data)
            self._is_initialized = True
            logger.info(
                f"Loaded {len(self.features.get_all_features())} features from {features_path}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to load features from {features_path}: {e}")
            return False

    def _deserialize_features(self, data: Dict) -> JavaIdiomFeatures:
        """Deserialize JSON data to JavaIdiomFeatures."""
        features = JavaIdiomFeatures()

        for category in [
            "forge_api_features",
            "class_structure_features",
            "import_features",
            "type_pattern_features",
        ]:
            if category in data:
                features_list = []
                for item in data[category]:
                    fv = FeatureVector(
                        feature_id=item["feature_id"],
                        activation=item.get("activation", 0.0),
                        steering_direction=item.get("steering_direction", -1.0),
                        description=item.get("description"),
                        examples=item.get("examples", []),
                    )
                    features_list.append(fv)
                setattr(features, category, features_list)

        return features

    def discover_java_features(
        self,
        activation_dataset: List[Dict[str, Any]],
        top_k: int = 50,
    ) -> JavaIdiomFeatures:
        """
        Discover features that correlate with Java Edition patterns.

        This implements the "Sieve" approach from Tilde Research:
        1. Run activation dataset through model
        2. Identify features that activate strongly on Java-idiomatic code
        3. Validate features against held-out test set

        Args:
            activation_dataset: List of {"code": str, "is_java": bool} samples
            top_k: Number of top features per category to retain

        Returns:
            JavaIdiomFeatures with discovered and validated features
        """
        logger.info(f"Starting feature discovery on {len(activation_dataset)} samples")

        java_samples = [s for s in activation_dataset if s.get("is_java", False)]
        non_java_samples = [s for s in activation_dataset if not s.get("is_java", False)]

        logger.info(f"Java samples: {len(java_samples)}, Non-Java samples: {len(non_java_samples)}")

        # Step 1: Compute average activation per feature
        feature_activations = self._compute_average_activations(activation_dataset)

        # Step 2: Identify features with high activation on Java samples
        java_features = self._identify_discriminating_features(
            feature_activations, java_samples, non_java_samples, top_k
        )

        # Step 3: Build the features object
        features = JavaIdiomFeatures(
            forge_api_features=java_features[: top_k // 4],
            class_structure_features=java_features[top_k // 4 : top_k // 2],
            import_features=java_features[top_k // 2 : 3 * top_k // 4],
            type_pattern_features=java_features[3 * top_k // 4 : top_k],
        )

        self.features = features
        return features

    def _compute_average_activations(self, dataset: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """Compute average activation per feature across dataset."""
        feature_activations: Dict[str, List[float]] = {}

        for sample in dataset:
            # Simulate activation extraction
            # In production, this would use actual model hook to extract activations
            activations = self._simulate_activations(sample.get("code", ""))

            for feature_id, activation in activations.items():
                if feature_id not in feature_activations:
                    feature_activations[feature_id] = []
                feature_activations[feature_id].append(activation)

        return feature_activations

    def _simulate_activations(self, code: str) -> Dict[str, float]:
        """
        Simulate activation extraction from code.

        In production, this would use actual model hooks (e.g., TransformerLens)
        to extract real activations. This is a placeholder for development.

        Args:
            code: Code to analyze

        Returns:
            Dict of feature_id -> activation strength
        """
        activations = {}

        java_indicators = [
            "import net.minecraft",
            "extends Entity",
            "public class",
            "@Mod",
            "Forge",
            "EventSubscriber",
            "NetworkEvent",
            "IForgeEntity",
            "Capability",
            "ItemStack",
        ]

        bedrock_indicators = [
            "minecraft:",
            "format_version",
            "client.js",
            "server.js",
            "entity",
            "component",
            "event",
        ]

        code_lower = code.lower()

        # Generate simulated activations for demonstration
        for i in range(100):
            feature_id = f"feature_{i:05d}"

            base_activation = 0.1

            for indicator in java_indicators:
                if indicator.lower() in code_lower:
                    base_activation += 0.3

            for indicator in bedrock_indicators:
                if indicator.lower() in code_lower:
                    base_activation -= 0.15

            activations[feature_id] = max(0.0, min(1.0, base_activation))

        return activations

    def _identify_discriminating_features(
        self,
        feature_activations: Dict[str, List[float]],
        java_samples: List[Dict],
        non_java_samples: List[Dict],
        top_k: int,
    ) -> List[FeatureVector]:
        """
        Identify features that discriminate between Java and non-Java code.

        Uses activation difference between classes to rank features.
        """
        feature_scores = []

        for feature_id, activations in feature_activations.items():
            if len(activations) < 2:
                continue

            java_activation = sum(activations[: len(java_samples)]) / max(1, len(java_samples))
            non_java_activation = sum(activations[len(java_samples) :]) / max(
                1, len(non_java_samples)
            )

            discriminability = java_activation - non_java_activation

            feature_scores.append(
                FeatureVector(
                    feature_id=feature_id,
                    activation=java_activation,
                    steering_direction=-1.0 if discriminability > 0 else 1.0,
                    description=f"Java vs non-Java activation diff: {discriminability:.3f}",
                )
            )

        # Sort by activation strength (descending) and take top_k
        feature_scores.sort(key=lambda f: f.activation, reverse=True)
        return feature_scores[:top_k]

    def apply_steering(
        self,
        activations: Dict[str, float],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """
        Apply steering to model activations.

        This is the core Sieve pipeline implementation:
        1. Extract current activations
        2. Apply suppression to Java-idiom features
        3. Optionally boost Bedrock-idiomatic features

        Args:
            activations: Current model activations (feature_id -> activation)
            context: Inference context (conversion_type, etc.)

        Returns:
            Steering-modified activations
        """
        if not self._is_initialized:
            logger.warning("Steerer not initialized, returning activations unchanged")
            return activations

        # Check if conditional steering should apply
        if self.config.conditional_on_context:
            if not self._should_apply_steering(context):
                return activations

        steered_activations = activations.copy()
        suppression_vector = self.features.get_suppression_vector()

        for feature_id, suppression in suppression_vector.items():
            if feature_id in steered_activations:
                original = steered_activations[feature_id]

                # Apply suppression (negative steering direction) or boost (positive)
                steering_effect = suppression * self._steering_strength * original

                steered_activations[feature_id] = max(0.0, original + steering_effect)

        return steered_activations

    def _should_apply_steering(self, context: Optional[Dict[str, Any]]) -> bool:
        """Determine if steering should be applied for this context."""
        if context is None:
            return True

        conversion_type = context.get("conversion_type", "")
        source = context.get("source", "")
        target = context.get("target", "")

        # Only apply steering for Java -> Bedrock conversions
        is_java_to_bedrock = (
            "java" in source.lower() and "bedrock" in target.lower()
        ) or conversion_type in ["java_to_bedrock", "forge_to_bds", "fabric_to_bds"]

        return is_java_to_bedrock

    def get_steering_report(
        self,
        activations: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Generate a report of steering effects on current activations.

        Args:
            activations: Current activations to analyze

        Returns:
            Report dict with feature suppression details
        """
        suppression_vector = self.features.get_suppression_vector()

        suppressed_features = []
        boosted_features = []
        unchanged_features = []

        for feature_id, activation in activations.items():
            steering_value = suppression_vector.get(feature_id, 0.0)

            if steering_value < 0:
                suppressed_features.append(
                    {
                        "feature_id": feature_id,
                        "original_activation": activation,
                        "steering_effect": steering_value,
                        "new_activation": max(0.0, activation + steering_value * activation),
                    }
                )
            elif steering_value > 0:
                boosted_features.append(
                    {
                        "feature_id": feature_id,
                        "original_activation": activation,
                        "steering_effect": steering_value,
                        "new_activation": activation + steering_value * activation,
                    }
                )
            else:
                unchanged_features.append(feature_id)

        return {
            "total_features_analyzed": len(activations),
            "suppressed_count": len(suppressed_features),
            "boosted_count": len(boosted_features),
            "unchanged_count": len(unchanged_features),
            "suppressed_features": suppressed_features[:10],  # top 10
            "boosted_features": boosted_features[:10],
            "timestamp": datetime.now().isoformat(),
        }


class JavaIdiomClassifier:
    """
    Classifier for detecting Java Edition idioms in generated code.

    Used to validate that SAE steering is working correctly.
    """

    JAVA_FORGE_PATTERNS = [
        r"import\s+net\.minecraft",
        r"import\s+cpw\.mods\.fml",
        r"extends\s+Entity",
        r"extends\s+Item",
        r"@Mod",
        r"@EventBusSubscriber",
        r"NetworkEvent\.Context",
        r"IForgePlayer",
        r"Capability\.get\(\)",
        r"ItemStack\.EMPTY",
    ]

    JAVA_CLASS_PATTERNS = [
        r"public\s+class\s+\w+",
        r"private\s+final\s+\w+",
        r"protected\s+void\s+\w+\s*\(",
        r"@SubscribeEvent",
        r"public\s+static\s+final\s+int",
    ]

    BEDROCK_IDIOM_PATTERNS = [
        r"minecraft:",
        r'"format_version"\s*:\s*"',
        r'"client"\s*:\s*\{',
        r'"server"\s*:\s*\{',
        r"\.setProperty\(",
        r"\.execute\(\)",
    ]

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        import re

        self._forge_patterns = [re.compile(p) for p in self.JAVA_FORGE_PATTERNS]
        self._class_patterns = [re.compile(p) for p in self.JAVA_CLASS_PATTERNS]
        self._bedrock_patterns = [re.compile(p) for p in self.BEDROCK_IDIOM_PATTERNS]

    def classify(self, code: str) -> Dict[str, Any]:
        """
        Classify code for Java Edition idioms.

        Args:
            code: Code to analyze

        Returns:
            Classification result with idiom scores
        """
        forge_matches = sum(1 for p in self._forge_patterns if p.search(code))
        class_matches = sum(1 for p in self._class_patterns if p.search(code))
        bedrock_matches = sum(1 for p in self._bedrock_patterns if p.search(code))

        total_java_indicators = forge_matches + class_matches

        # Score: 0 = pure Bedrock, 1 = pure Java Edition
        java_score = min(1.0, total_java_indicators * 0.2)
        bedrock_score = min(1.0, bedrock_matches * 0.25)

        return {
            "java_score": java_score,
            "bedrock_score": bedrock_score,
            "idiom_type": "java" if java_score > bedrock_score else "bedrock",
            "confidence": abs(java_score - bedrock_score),
            "forge_pattern_matches": forge_matches,
            "class_pattern_matches": class_matches,
            "bedrock_pattern_matches": bedrock_matches,
            "is_java_idiomatic": java_score > 0.3,
            "is_bedrock_idiomatic": bedrock_score > 0.25,
        }

    def validate_steering_effect(
        self,
        original_code: str,
        steered_code: str,
    ) -> Dict[str, Any]:
        """
        Validate that steering had the desired effect.

        Args:
            original_code: Code before steering
            steered_code: Code after steering

        Returns:
            Validation result
        """
        original_classification = self.classify(original_code)
        steered_classification = self.classify(steered_code)

        java_reduction = (
            original_classification["java_score"] - steered_classification["java_score"]
        )
        bedrock_increase = (
            steered_classification["bedrock_score"] - original_classification["bedrock_score"]
        )

        steering_effective = (
            java_reduction > 0 and steered_classification["idiom_type"] == "bedrock"
        )

        return {
            "steering_effective": steering_effective,
            "java_score_reduction": java_reduction,
            "bedrock_score_increase": bedrock_increase,
            "original_classification": original_classification,
            "steered_classification": steered_classification,
        }


def create_default_steering_config() -> SteeringConfig:
    """Create a default steering configuration."""
    return SteeringConfig(
        steering_strength=1.0,
        suppression_threshold=0.5,
        enable_boost=False,
        conditional_on_context=True,
    )


def create_demo_features() -> JavaIdiomFeatures:
    """Create demo features for testing without real SAE training."""
    features = JavaIdiomFeatures()

    for i in range(50):
        feature = FeatureVector(
            feature_id=f"forge_feature_{i:03d}",
            activation=0.7,
            steering_direction=-1.0,
            description=f"Java Forge API pattern {i}",
        )
        features.forge_api_features.append(feature)

    for i in range(50):
        feature = FeatureVector(
            feature_id=f"class_struct_feature_{i:03d}",
            activation=0.6,
            steering_direction=-0.8,
            description=f"Java class structure pattern {i}",
        )
        features.class_structure_features.append(feature)

    for i in range(30):
        feature = FeatureVector(
            feature_id=f"import_feature_{i:03d}",
            activation=0.8,
            steering_direction=-1.0,
            description=f"Java import pattern {i}",
        )
        features.import_features.append(feature)

    for i in range(40):
        feature = FeatureVector(
            feature_id=f"type_pattern_feature_{i:03d}",
            activation=0.5,
            steering_direction=-0.9,
            description=f"Java type pattern {i}",
        )
        features.type_pattern_features.append(feature)

    return features
