"""
Agentic Reasoning Pattern Discovery for Test-Time Scaling

Implements automatic discovery of optimal agentic reasoning patterns for
conversion tasks, inspired by "LLMs Improving LLMs" (arXiv:2605.08083v1).

The system learns which reasoning patterns lead to successful conversions
for different feature types (NBT logic, entity behavior, GUI, etc.)
through environment feedback, rather than relying on hand-crafted patterns.
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class FeatureCategory(str, Enum):
    """Categories of Java features for pattern matching."""

    NBT_DATA = "nbt_data"
    ENTITY_BEHAVIOR = "entity_behavior"
    BLOCK_LOGIC = "block_logic"
    ITEM_MECHANICS = "item_mechanics"
    GUI_FORMS = "gui_forms"
    DIMENSION_TERRAIN = "dimension_terrain"
    PARTICLE_EFFECTS = "particle_effects"
    SOUND_EVENTS = "sound_events"
    POTION_EFFECTS = "potion_effects"
    VILLAGER_TRADE = "villager_trade"
    WEAPON_TOOL = "weapon_tool"
    ADVANCEMENT = "advancement"
    COMMAND_SYSTEM = "command_system"
    RENDERING = "rendering"
    UNKNOWN = "unknown"


class PatternQuality(str, Enum):
    """Quality tiers for discovered patterns."""

    EXCELLENT = "excellent"  # >= 0.85 success rate
    GOOD = "good"  # >= 0.70 success rate
    ACCEPTABLE = "acceptable"  # >= 0.50 success rate
    POOR = "poor"  # < 0.50 success rate


@dataclass
class ReasoningStep:
    """A single step in a reasoning pattern."""

    step_id: str
    description: str
    agent_hint: str  # Which agent should execute this
    focus_area: str  # What to focus on (e.g., "data_structure", "semantic_mapping")
    success_indicator: str  # How to verify this step succeeded


@dataclass
class ReasoningPattern:
    """
    A discovered reasoning pattern for conversion.

    Contains an ordered sequence of reasoning steps that have
    proven effective for certain feature types.
    """

    pattern_id: str
    name: str
    description: str
    feature_category: FeatureCategory
    steps: List[ReasoningStep]
    success_rate: float
    sample_size: int
    avg_quality_score: float
    first_discovered: str
    last_updated: str
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "description": self.description,
            "feature_category": self.feature_category.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "agent_hint": s.agent_hint,
                    "focus_area": s.focus_area,
                    "success_indicator": s.success_indicator,
                }
                for s in self.steps
            ],
            "success_rate": self.success_rate,
            "sample_size": self.sample_size,
            "avg_quality_score": self.avg_quality_score,
            "first_discovered": self.first_discovered,
            "last_updated": self.last_updated,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningPattern":
        steps = [
            ReasoningStep(
                step_id=s["step_id"],
                description=s["description"],
                agent_hint=s["agent_hint"],
                focus_area=s["focus_area"],
                success_indicator=s["success_indicator"],
            )
            for s in data.get("steps", [])
        ]
        return cls(
            pattern_id=data["pattern_id"],
            name=data["name"],
            description=data["description"],
            feature_category=FeatureCategory(data.get("feature_category", "unknown")),
            steps=steps,
            success_rate=data.get("success_rate", 0.0),
            sample_size=data.get("sample_size", 0),
            avg_quality_score=data.get("avg_quality_score", 0.0),
            first_discovered=data.get("first_discovered", ""),
            last_updated=data.get("last_updated", ""),
            is_active=data.get("is_active", True),
        )


@dataclass
class ConversionContext:
    """Context about a conversion task for pattern selection."""

    feature_category: FeatureCategory
    feature_name: str
    mod_type: str
    mod_framework: str
    complexity_score: float  # 0-1
    has_nbt: bool
    has_custom_entity: bool
    has_gui: bool
    java_code_snippet: str
    previous_attempts: int = 0
    previous_failures: int = 0


@dataclass
class PatternEvaluation:
    """Result of evaluating a pattern on a conversion task."""

    pattern_id: str
    job_id: str
    feature_category: FeatureCategory
    quality_score: float
    conversion_success: bool
    execution_time_seconds: float
    steps_executed: int
    feedback: str
    timestamp: str


class ReasoningPatternGrammar:
    """
    Defines the grammar of possible reasoning steps.

    This provides the building blocks that the discovery system
    can combine to form candidate patterns.
    """

    STEP_TEMPLATES = {
        "understand_structure": ReasoningStep(
            step_id="understand_structure",
            description="Analyze the data structure or code organization",
            agent_hint="java_analyzer",
            focus_area="structure_analysis",
            success_indicator="Structure clearly identified",
        ),
        "identify_semantic_equivalents": ReasoningStep(
            step_id="identify_semantic_equivalents",
            description="Find semantic equivalents in Bedrock API",
            agent_hint="bedrock_architect",
            focus_area="semantic_mapping",
            success_indicator="Bedrock equivalents identified",
        ),
        "test_against_payload": ReasoningStep(
            step_id="test_against_payload",
            description="Test conversion against sample payloads or game state",
            agent_hint="qa_validator",
            focus_area="validation",
            success_indicator="Tests pass",
        ),
        "handle_edge_cases": ReasoningStep(
            step_id="handle_edge_cases",
            description="Handle edge cases and boundary conditions",
            agent_hint="logic_translator",
            focus_area="edge_case_handling",
            success_indicator="Edge cases addressed",
        ),
        "validate_completeness": ReasoningStep(
            step_id="validate_completeness",
            description="Validate all required components are converted",
            agent_hint="qa_validator",
            focus_area="completeness_check",
            success_indicator="All components present",
        ),
        "extract_data_model": ReasoningStep(
            step_id="extract_data_model",
            description="Extract the underlying data model or schema",
            agent_hint="java_analyzer",
            focus_area="data_model",
            success_indicator="Data model extracted",
        ),
        "map_api_calls": ReasoningStep(
            step_id="map_api_calls",
            description="Map Java API calls to Bedrock equivalents",
            agent_hint="logic_translator",
            focus_area="api_mapping",
            success_indicator="API calls mapped",
        ),
        "preserve_semantics": ReasoningStep(
            step_id="preserve_semantics",
            description="Ensure semantic equivalence is preserved",
            agent_hint="bedrock_architect",
            focus_area="semantic_preservation",
            success_indicator="Semantics preserved",
        ),
        "optimize_performance": ReasoningStep(
            step_id="optimize_performance",
            description="Optimize for Bedrock performance constraints",
            agent_hint="asset_converter",
            focus_area="performance",
            success_indicator="Performance optimized",
        ),
        "generate_test_cases": ReasoningStep(
            step_id="generate_test_cases",
            description="Generate test cases to verify conversion",
            agent_hint="qa_validator",
            focus_area="testing",
            success_indicator="Test cases generated",
        ),
    }

    @classmethod
    def get_step(cls, step_id: str) -> Optional[ReasoningStep]:
        return cls.STEP_TEMPLATES.get(step_id)

    @classmethod
    def get_steps_for_category(cls, category: FeatureCategory) -> List[str]:
        """Get recommended step sequences for a feature category."""
        category_strategies = {
            FeatureCategory.NBT_DATA: [
                "extract_data_model",
                "identify_semantic_equivalents",
                "test_against_payload",
            ],
            FeatureCategory.ENTITY_BEHAVIOR: [
                "understand_structure",
                "extract_data_model",
                "map_api_calls",
                "validate_completeness",
            ],
            FeatureCategory.BLOCK_LOGIC: [
                "understand_structure",
                "identify_semantic_equivalents",
                "handle_edge_cases",
            ],
            FeatureCategory.GUI_FORMS: [
                "extract_data_model",
                "identify_semantic_equivalents",
                "test_against_payload",
            ],
            FeatureCategory.DIMENSION_TERRAIN: [
                "understand_structure",
                "identify_semantic_equivalents",
                "optimize_performance",
            ],
            FeatureCategory.PARTICLE_EFFECTS: [
                "extract_data_model",
                "identify_semantic_equivalents",
                "validate_completeness",
            ],
            FeatureCategory.WEAPON_TOOL: [
                "understand_structure",
                "map_api_calls",
                "handle_edge_cases",
            ],
        }
        return category_strategies.get(
            category, ["understand_structure", "identify_semantic_equivalents"]
        )


class ReasoningPatternDiscovery:
    """
    Discovers and optimizes reasoning patterns through environment feedback.

    Based on the insight that optimal reasoning patterns vary by feature type:
    - For NBT logic: "1. Understand data structure. 2. Find semantic equivalents. 3. Test against payloads"
    - For entity behavior: "1. Extract behavior model. 2. Map to Bedrock entity system. 3. Validate completeness"

    The system uses feedback from conversion quality to learn which patterns
    work best for which feature types.
    """

    def __init__(
        self,
        db_path: str = "training_data/reasoning_patterns.db",
        min_sample_size: int = 0,
        exploration_rate: float = 0.2,
    ):
        self.db_path = db_path
        self.min_sample_size = min_sample_size
        self.exploration_rate = exploration_rate  # Rate of trying new patterns
        self.grammar = ReasoningPatternGrammar()
        self._init_db()

    def _init_db(self):
        """Initialize pattern database."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS reasoning_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    feature_category TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    success_rate REAL DEFAULT 0.0,
                    sample_size INTEGER DEFAULT 0,
                    avg_quality_score REAL DEFAULT 0.0,
                    first_discovered TEXT,
                    last_updated TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS pattern_evaluations (
                    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    feature_category TEXT NOT NULL,
                    quality_score REAL,
                    conversion_success INTEGER,
                    execution_time_seconds REAL,
                    steps_executed INTEGER,
                    feedback TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (pattern_id) REFERENCES reasoning_patterns(pattern_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS candidate_patterns (
                    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_json TEXT NOT NULL,
                    feature_category TEXT NOT NULL,
                    proposed_by TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feature_category ON reasoning_patterns(feature_category)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pattern_success ON reasoning_patterns(success_rate DESC)"
            )

    def propose_candidate_pattern(
        self,
        feature_category: FeatureCategory,
        context: ConversionContext,
    ) -> ReasoningPattern:
        """
        Propose a candidate reasoning pattern for a conversion task.

        Uses existing patterns as templates and adapts them based on context.
        Falls back to grammar-based generation when no patterns exist.

        Args:
            feature_category: Category of feature being converted
            context: Context about the conversion task

        Returns:
            A candidate ReasoningPattern
        """
        existing_patterns = self.get_patterns_for_category(feature_category)

        if existing_patterns and np.random.random() > self.exploration_rate:
            pattern = self._derive_pattern_from_existing(existing_patterns, context)
        else:
            pattern = self._generate_pattern_from_grammar(feature_category, context)

        return pattern

    def _derive_pattern_from_existing(
        self,
        existing_patterns: List[ReasoningPattern],
        context: ConversionContext,
    ) -> ReasoningPattern:
        """Derive a new pattern from best-performing existing patterns."""
        sorted_patterns = sorted(existing_patterns, key=lambda p: p.success_rate, reverse=True)
        best = sorted_patterns[0]

        new_steps = []
        for step in best.steps:
            base_step = self.grammar.get_step(step.step_id)
            if base_step and context.complexity_score > 0.7:
                new_step = ReasoningStep(
                    step_id=step.step_id,
                    description=step.description,
                    agent_hint=step.agent_hint,
                    focus_area=step.focus_area,
                    success_indicator=step.success_indicator,
                )
            else:
                new_step = ReasoningStep(
                    step_id=step.step_id,
                    description=step.description,
                    agent_hint=step.agent_hint,
                    focus_area=step.focus_area,
                    success_indicator=step.success_indicator,
                )
            new_steps.append(new_step)

        pattern_id = f"derived_{best.pattern_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return ReasoningPattern(
            pattern_id=pattern_id,
            name=f"Derived from {best.name}",
            description=f"Pattern derived for {context.feature_name} (complexity={context.complexity_score:.1f})",
            feature_category=best.feature_category,
            steps=new_steps,
            success_rate=best.success_rate,
            sample_size=0,
            avg_quality_score=0.0,
            first_discovered=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            is_active=True,
        )

    def _generate_pattern_from_grammar(
        self,
        feature_category: FeatureCategory,
        context: ConversionContext,
    ) -> ReasoningPattern:
        """Generate a new pattern from the grammar based on feature category."""
        step_ids = self.grammar.get_steps_for_category(feature_category)

        steps = []
        for i, step_id in enumerate(step_ids):
            template = self.grammar.get_step(step_id)
            if template:
                steps.append(
                    ReasoningStep(
                        step_id=f"step_{i}_{step_id}",
                        description=template.description,
                        agent_hint=template.agent_hint,
                        focus_area=template.focus_area,
                        success_indicator=template.success_indicator,
                    )
                )

        pattern_id = f"generated_{feature_category.value}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return ReasoningPattern(
            pattern_id=pattern_id,
            name=f"Generated {feature_category.value} Pattern",
            description=f"Automatically generated pattern for {feature_category.value} conversion",
            feature_category=feature_category,
            steps=steps,
            success_rate=0.0,
            sample_size=0,
            avg_quality_score=0.0,
            first_discovered=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            is_active=True,
        )

    def record_evaluation(self, evaluation: PatternEvaluation) -> None:
        """
        Record the result of applying a pattern to a conversion task.

        This is the core feedback mechanism that enables pattern discovery.

        Args:
            evaluation: PatternEvaluation with conversion results
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO pattern_evaluations (
                        pattern_id, job_id, feature_category, quality_score,
                        conversion_success, execution_time_seconds, steps_executed,
                        feedback, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        evaluation.pattern_id,
                        evaluation.job_id,
                        evaluation.feature_category.value,
                        evaluation.quality_score,
                        1 if evaluation.conversion_success else 0,
                        evaluation.execution_time_seconds,
                        evaluation.steps_executed,
                        evaluation.feedback,
                        evaluation.timestamp,
                    ),
                )
                conn.commit()

                self._update_pattern_stats(evaluation.pattern_id)

                logger.info(
                    f"Recorded evaluation: pattern={evaluation.pattern_id}, "
                    f"quality={evaluation.quality_score:.2f}, success={evaluation.conversion_success}"
                )

        except Exception as e:
            logger.error(f"Failed to record evaluation: {e}")

    def _update_pattern_stats(self, pattern_id: str) -> None:
        """Update pattern statistics based on all evaluations."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as sample_size,
                    AVG(quality_score) as avg_quality,
                    SUM(CASE WHEN conversion_success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate
                FROM pattern_evaluations
                WHERE pattern_id = ?
            """,
                (pattern_id,),
            )
            row = cursor.fetchone()

            if row and row[0] > 0:
                sample_size = row[0]
                avg_quality = row[1] or 0.0
                success_rate = row[2] or 0.0

                conn.execute(
                    """
                    UPDATE reasoning_patterns
                    SET sample_size = ?,
                        avg_quality_score = ?,
                        success_rate = ?,
                        last_updated = ?
                    WHERE pattern_id = ?
                """,
                    (
                        sample_size,
                        avg_quality,
                        success_rate,
                        datetime.now().isoformat(),
                        pattern_id,
                    ),
                )

    def get_best_pattern_for_category(
        self, feature_category: FeatureCategory
    ) -> Optional[ReasoningPattern]:
        """Get the best-performing active pattern for a feature category."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM reasoning_patterns
                WHERE feature_category = ?
                AND is_active = 1
                AND sample_size >= ?
                ORDER BY success_rate DESC, avg_quality_score DESC
                LIMIT 1
            """,
                (feature_category.value, self.min_sample_size),
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_pattern(row)
            return None

    def get_patterns_for_category(
        self, feature_category: FeatureCategory, limit: int = 10
    ) -> List[ReasoningPattern]:
        """Get all patterns for a feature category, sorted by success rate."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM reasoning_patterns
                WHERE feature_category = ?
                AND is_active = 1
                ORDER BY success_rate DESC, avg_quality_score DESC
                LIMIT ?
            """,
                (feature_category.value, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_pattern(row) for row in rows]

    def get_all_patterns(self, limit: int = 100) -> List[ReasoningPattern]:
        """Get all active patterns."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM reasoning_patterns
                WHERE is_active = 1
                ORDER BY success_rate DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [self._row_to_pattern(row) for row in rows]

    def _row_to_pattern(self, row: sqlite3.Row) -> ReasoningPattern:
        """Convert a database row to a ReasoningPattern."""
        steps_data = json.loads(row["steps_json"])
        steps = [
            ReasoningStep(
                step_id=s["step_id"],
                description=s["description"],
                agent_hint=s["agent_hint"],
                focus_area=s["focus_area"],
                success_indicator=s["success_indicator"],
            )
            for s in steps_data
        ]
        return ReasoningPattern(
            pattern_id=row["pattern_id"],
            name=row["name"],
            description=row["description"],
            feature_category=FeatureCategory(row["feature_category"]),
            steps=steps,
            success_rate=row["success_rate"],
            sample_size=row["sample_size"],
            avg_quality_score=row["avg_quality_score"],
            first_discovered=row["first_discovered"],
            last_updated=row["last_updated"],
            is_active=bool(row["is_active"]),
        )

    def store_pattern(self, pattern: ReasoningPattern) -> None:
        """Store a new or updated pattern."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reasoning_patterns (
                    pattern_id, name, description, feature_category, steps_json,
                    success_rate, sample_size, avg_quality_score,
                    first_discovered, last_updated, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    pattern.pattern_id,
                    pattern.name,
                    pattern.description,
                    pattern.feature_category.value,
                    json.dumps([asdict(s) for s in pattern.steps]),
                    pattern.success_rate,
                    pattern.sample_size,
                    pattern.avg_quality_score,
                    pattern.first_discovered,
                    pattern.last_updated,
                    1 if pattern.is_active else 0,
                ),
            )
        logger.info(f"Stored pattern: {pattern.pattern_id}")

    def deactivate_poor_patterns(self, threshold: float = 0.3, min_samples: int = 5) -> int:
        """
        Deactivate patterns that perform poorly.

        Args:
            threshold: Success rate below which to deactivate
            min_samples: Minimum samples required before deactivation

        Returns:
            Number of patterns deactivated
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE reasoning_patterns
                SET is_active = 0
                WHERE success_rate < ?
                AND sample_size >= ?
                AND is_active = 1
            """,
                (threshold, min_samples),
            )
            deactivated = cursor.rowcount

        if deactivated > 0:
            logger.info(f"Deactivated {deactivated} poor-performing patterns")

        return deactivated

    def get_discovery_stats(self) -> Dict[str, Any]:
        """Get statistics about pattern discovery."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT pattern_id) as total_patterns,
                    COUNT(DISTINCT feature_category) as categories_covered,
                    SUM(sample_size) as total_evaluations,
                    AVG(success_rate) as avg_success_rate,
                    MAX(success_rate) as best_success_rate
                FROM reasoning_patterns
                WHERE is_active = 1
            """
            )
            row = cursor.fetchone()

            return {
                "total_patterns": row[0] or 0,
                "categories_covered": row[1] or 0,
                "total_evaluations": row[2] or 0,
                "avg_success_rate": row[3] or 0.0,
                "best_success_rate": row[4] or 0.0,
            }


class ReasoningPatternSelector:
    """
    Selects the optimal pattern for a given conversion context.

    Uses exploration vs exploitation to balance between:
    - Exploiting known good patterns
    - Exploring new patterns to discover improvements
    """

    def __init__(self, discovery: ReasoningPatternDiscovery):
        self.discovery = discovery
        self.epsilon = 0.1  # Exploration rate

    def select_pattern(self, context: ConversionContext) -> Tuple[ReasoningPattern, bool]:
        """
        Select a pattern for the given conversion context.

        Args:
            context: Information about the conversion task

        Returns:
            Tuple of (selected_pattern, is_exploration)
            is_exploration indicates if a new pattern was tried vs exploiting known best
        """
        if np.random.random() < self.epsilon:
            pattern = self.discovery.propose_candidate_pattern(
                feature_category=context.feature_category,
                context=context,
            )
            self.discovery.store_pattern(pattern)
            return pattern, True

        best_pattern = self.discovery.get_best_pattern_for_category(context.feature_category)

        if best_pattern and best_pattern.sample_size >= self.discovery.min_sample_size:
            return best_pattern, False

        pattern = self.discovery.propose_candidate_pattern(
            feature_category=context.feature_category,
            context=context,
        )
        self.discovery.store_pattern(pattern)
        return pattern, True

    def record_outcome(self, pattern: ReasoningPattern, evaluation: PatternEvaluation) -> None:
        """Record the outcome of applying a pattern."""
        self.discovery.store_pattern(pattern)
        self.discovery.record_evaluation(evaluation)


def create_reasoning_pattern_discovery(
    db_path: str = "training_data/reasoning_patterns.db",
) -> ReasoningPatternDiscovery:
    """Factory function to create a pattern discovery instance."""
    return ReasoningPatternDiscovery(db_path=db_path)


def create_pattern_selector(
    discovery: Optional[ReasoningPatternDiscovery] = None,
) -> ReasoningPatternSelector:
    """Factory function to create a pattern selector."""
    if discovery is None:
        discovery = create_reasoning_pattern_discovery()
    return ReasoningPatternSelector(discovery)
