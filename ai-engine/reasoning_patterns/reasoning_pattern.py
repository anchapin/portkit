"""
Reasoning Pattern Data Structures

Defines the core data structures for representing and scoring
agentic reasoning patterns for Java-to-Bedrock conversion.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class FeatureType(Enum):
    """Feature categories for conversion patterns."""

    NBT_LOGIC = "nbt_logic"
    GUI = "gui"
    ENTITY = "entity"
    BLOCK = "block"
    ITEM = "item"
    RECIPE = "recipe"
    EVENT = "event"
    NETWORK = "network"
    CAPABILITY = "capability"
    DIMENSION = "dimension"
    PARTICLE = "particle"
    SOUND = "sound"
    RENDERING = "rendering"
    COMMAND = "command"
    UNKNOWN = "unknown"


@dataclass
class ReasoningStep:
    """
    A single step in a reasoning pattern.

    Each step represents an action the agent should take when
    approaching a specific type of conversion problem.
    """

    order: int
    action: str
    description: str
    examples: List[str] = field(default_factory=list)
    expected_output: Optional[str] = None

    def to_prompt_fragment(self) -> str:
        """Convert step to prompt text fragment."""
        return f"{self.order}. {self.action}: {self.description}"


@dataclass
class ReasoningPattern:
    """
    An agentic reasoning pattern for conversion.

    A pattern consists of ordered steps that guide the agent's
    reasoning process when tackling a specific conversion task.
    """

    id: str
    name: str
    description: str
    feature_type: FeatureType
    steps: List[ReasoningStep]
    success_threshold: float = 0.7
    sample_size: int = 0
    is_discovered: bool = False
    is_handcrafted: bool = False
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate pattern data."""
        if not self.id:
            raise ValueError("Pattern ID cannot be empty")
        if not self.steps:
            raise ValueError("Pattern must have at least one step")
        if self.success_threshold < 0 or self.success_threshold > 1:
            raise ValueError(f"Success threshold must be 0.0-1.0, got {self.success_threshold}")

    def to_prompt(self) -> str:
        """Convert pattern to full reasoning prompt."""
        steps_text = "\n".join(step.to_prompt_fragment() for step in self.steps)
        return f"{self.name}\n\n{self.description}\n\nSteps:\n{steps_text}"

    def to_dict(self) -> Dict:
        """Convert pattern to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "feature_type": self.feature_type.value,
            "steps": [
                {
                    "order": s.order,
                    "action": s.action,
                    "description": s.description,
                    "examples": s.examples,
                    "expected_output": s.expected_output,
                }
                for s in self.steps
            ],
            "success_threshold": self.success_threshold,
            "sample_size": self.sample_size,
            "is_discovered": self.is_discovered,
            "is_handcrafted": self.is_handcrafted,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ReasoningPattern":
        """Create pattern from dictionary."""
        steps = [
            ReasoningStep(
                order=s["order"],
                action=s["action"],
                description=s["description"],
                examples=s.get("examples", []),
                expected_output=s.get("expected_output"),
            )
            for s in data["steps"]
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            feature_type=FeatureType(data.get("feature_type", "unknown")),
            steps=steps,
            success_threshold=data.get("success_threshold", 0.7),
            sample_size=data.get("sample_size", 0),
            is_discovered=data.get("is_discovered", False),
            is_handcrafted=data.get("is_handcrafted", False),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PatternPerformance:
    """
    Performance metrics for a reasoning pattern on a feature type.

    Tracks how well a pattern performs on conversions of a specific type,
    enabling selection of optimal patterns.
    """

    pattern_id: str
    feature_type: FeatureType
    total_attempts: int = 0
    successful_attempts: int = 0
    total_reward: float = 0.0
    avg_reward: float = 0.0
    avg_confidence: float = 0.0
    success_rate: float = 0.0
    last_updated: Optional[str] = None

    def record_attempt(self, success: bool, reward: float = 0.0, confidence: float = 0.0) -> None:
        """
        Record a conversion attempt with this pattern.

        Args:
            success: Whether the conversion succeeded
            reward: Reward score (0.0-1.0)
            confidence: Confidence score (0.0-1.0)
        """
        self.total_attempts += 1
        if success:
            self.successful_attempts += 1
        self.total_reward += reward
        self.avg_reward = self.total_reward / self.total_attempts
        self.avg_confidence = (
            self.avg_confidence * (self.total_attempts - 1) + confidence
        ) / self.total_attempts
        self.success_rate = self.successful_attempts / self.total_attempts

    def get_score(self) -> float:
        """
        Get combined performance score.

        Combines success rate and reward into single score for ranking.
        """
        return (self.success_rate * 0.6) + (self.avg_reward * 0.4)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "feature_type": self.feature_type.value,
            "total_attempts": self.total_attempts,
            "successful_attempts": self.successful_attempts,
            "avg_reward": round(self.avg_reward, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "success_rate": round(self.success_rate, 4),
            "score": round(self.get_score(), 4),
            "last_updated": self.last_updated,
        }


# Handcrafted baseline patterns for common feature types
HANDCRAFTED_PATTERNS: List[ReasoningPattern] = [
    ReasoningPattern(
        id="handcrafted_nbt_logic",
        name="NBT Logic Conversion Pattern",
        description="Approach NBT (Named Binary Tag) data structure conversions by understanding the data hierarchy first",
        feature_type=FeatureType.NBT_LOGIC,
        steps=[
            ReasoningStep(
                1,
                "Analyze NBT Structure",
                "Identify all NBT tags and their types (compound, list, primitive)",
            ),
            ReasoningStep(
                2,
                "Map to Bedrock Schema",
                "Find semantic equivalents in Bedrock's JSON component system",
            ),
            ReasoningStep(
                3,
                "Handle Nested Data",
                "Convert nested structures to Bedrock's flat component model",
            ),
            ReasoningStep(
                4,
                "Test with Payloads",
                "Validate against sample NBT payloads to ensure data integrity",
            ),
        ],
        is_handcrafted=True,
    ),
    ReasoningPattern(
        id="handcrafted_gui",
        name="GUI Conversion Pattern",
        description="Convert Java GUI systems to Bedrock interfaces using sign-based interactions",
        feature_type=FeatureType.GUI,
        steps=[
            ReasoningStep(
                1,
                "Identify GUI Components",
                "List all GUI elements: containers, buttons, text fields",
            ),
            ReasoningStep(
                2,
                "Map to Bedrock Alternatives",
                "Find Bedrock equivalents (signs, hoppers,Lecterns)",
            ),
            ReasoningStep(3, "Handle Events", "Convert event handlers to Bedrock's trigger system"),
            ReasoningStep(4, "Test Interactions", "Verify all interaction paths work correctly"),
        ],
        is_handcrafted=True,
    ),
    ReasoningPattern(
        id="handcrafted_entity",
        name="Entity Conversion Pattern",
        description="Convert Java entities to Bedrock with proper AI goals and behaviors",
        feature_type=FeatureType.ENTITY,
        steps=[
            ReasoningStep(
                1,
                "Identify Entity Type",
                "Determine entity category: mob, projectile, vehicle, etc.",
            ),
            ReasoningStep(
                2,
                "Map Attributes",
                "Convert health, speed, damage attributes to Bedrock attributes",
            ),
            ReasoningStep(3, "Convert AI Goals", "Map Java goal selectors to Bedrock AI goals"),
            ReasoningStep(4, "Handle Events", "Convert entity events to Bedrock's event system"),
            ReasoningStep(5, "Test in Game", "Verify entity spawns and behaves correctly"),
        ],
        is_handcrafted=True,
    ),
    ReasoningPattern(
        id="handcrafted_block",
        name="Block Conversion Pattern",
        description="Convert Java blocks with state properties to Bedrock blocks",
        feature_type=FeatureType.BLOCK,
        steps=[
            ReasoningStep(
                1,
                "Analyze Block Properties",
                "Identify state properties, block states, and behaviors",
            ),
            ReasoningStep(
                2, "Create Bedrock Definition", "Create JSON block definition with components"
            ),
            ReasoningStep(
                3, "Map Block States", "Convert Java block states to Bedrock permutation system"
            ),
            ReasoningStep(
                4, "Handle Block Events", "Convert block interaction events to Bedrock triggers"
            ),
        ],
        is_handcrafted=True,
    ),
    ReasoningPattern(
        id="handcrafted_default",
        name="Default Conversion Pattern",
        description="General-purpose pattern for any Java-to-Bedrock conversion",
        feature_type=FeatureType.UNKNOWN,
        steps=[
            ReasoningStep(
                1, "Extract Java Structure", "Identify class structure, methods, and dependencies"
            ),
            ReasoningStep(2, "Map to Bedrock Type", "Find appropriate Bedrock equivalent type"),
            ReasoningStep(3, "Translate Methods", "Convert Java logic to Bedrock JavaScript"),
            ReasoningStep(
                4, "Handle Differences", "Document incompatibilities and apply workarounds"
            ),
            ReasoningStep(5, "Validate Output", "Ensure generated code is syntactically correct"),
        ],
        is_handcrafted=True,
    ),
]
