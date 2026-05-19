"""
Multi-Candidate Consistency Checker (DPC-Style)

Implements training-free multi-candidate selection based on:
"Dual-Paradigm Consistency" (DPC) - arxiv.org/abs/2604.15163v1

Generates N candidate Bedrock outputs per Java segment, applies
conformal prediction to identify the most reliable one, and flags
inconsistent candidates rather than arbitrarily picking one.

This reduces hallucination in AI-generated Bedrock entity behaviors
and reduces manual review burden for beta users.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from qa.veccisc import ReasoningTrace, VecCISCCandidateResult, VecCISCSelector

logger = structlog.get_logger(__name__)

DEFAULT_CANDIDATE_COUNT = 3
DEFAULT_TEMPERATURE_LOW = 0.2
DEFAULT_TEMPERATURE_HIGH = 0.5


class SelectionStrategy(Enum):
    """Strategy for selecting best candidate from multiple."""

    MAJORITY_VOTE = "majority_vote"
    STRUCTURAL_SIMILARITY = "structural_similarity"
    SEMANTIC_EMBEDDING = "semantic_embedding"
    CONFORMAL_SCORE = "conformal_score"
    DPC_CONSISTENCY = "dpc_consistency"


@dataclass
class ConversionCandidate:
    """A single conversion candidate output."""

    candidate_id: int
    code: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    temperature: float = 0.3
    prompt_suffix: str = ""

    def get_fingerprint(self) -> str:
        """Get normalized fingerprint for comparison."""
        normalized = self.code.lower()
        normalized = normalized.replace(" ", "").replace("\n", "").replace("\t", "")
        normalized = normalized.replace("_", "").replace("-", "")
        return hashlib.md5(normalized.encode()).hexdigest()[:16]


@dataclass
class ConsistencyResult:
    """Result of DPC consistency check."""

    selected_candidate: Optional[ConversionCandidate]
    agreement_score: float
    candidate_rankings: List[Tuple[int, float]]
    flagged_candidates: List[int]
    consensus_code: Optional[str]
    confidence: float
    needs_review: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_candidate_id": self.selected_candidate.candidate_id
            if self.selected_candidate
            else None,
            "agreement_score": round(self.agreement_score, 3),
            "candidate_rankings": [
                (cid, round(score, 3)) for cid, score in self.candidate_rankings
            ],
            "flagged_candidates": self.flagged_candidates,
            "consensus_code": self.consensus_code,
            "confidence": round(self.confidence, 3),
            "needs_review": self.needs_review,
        }


@dataclass
class CandidateConfig:
    """Configuration for candidate generation."""

    candidate_count: int = DEFAULT_CANDIDATE_COUNT
    temperature_low: float = DEFAULT_TEMPERATURE_LOW
    temperature_high: float = DEFAULT_TEMPERATURE_HIGH
    selection_strategy: SelectionStrategy = SelectionStrategy.DPC_CONSISTENCY
    agreement_threshold: float = 0.7
    structural_threshold: float = 0.8
    min_candidates_for_selection: int = 2


class MultiCandidateConsistencyChecker:
    """
    DPC-style multi-candidate consistency checker.

    Generates N candidate conversions and selects the most consistent one
    using Dual-Paradigm Consistency principles:

    1. Generate N candidates with varied parameters (temperature, prompts)
    2. Compute pairwise similarity between candidates
    3. Select candidate with highest agreement to others
    4. Flag candidates that disagree with consensus for review
    """

    def __init__(self, config: Optional[CandidateConfig] = None):
        self.config = config or CandidateConfig()

    def generate_candidate_configs(self) -> List[Dict[str, Any]]:
        """Generate configuration for each candidate."""
        configs = []
        step = (
            (self.config.temperature_high - self.config.temperature_low)
            / (self.config.candidate_count - 1)
            if self.config.candidate_count > 1
            else 0
        )

        prompt_suffixes = [
            "Ensure precise semantic equivalence with Java source.",
            "Focus on idiomatic Bedrock patterns and best practices.",
            "Prioritize performance and simplicity.",
        ]

        for i in range(self.config.candidate_count):
            temp = (
                self.config.temperature_low + step * i
                if self.config.candidate_count > 1
                else (self.config.temperature_low + self.config.temperature_high) / 2
            )
            configs.append(
                {
                    "candidate_id": i,
                    "temperature": temp,
                    "prompt_suffix": prompt_suffixes[i % len(prompt_suffixes)],
                }
            )
        return configs

    def compute_pairwise_agreement(
        self, candidates: List[ConversionCandidate]
    ) -> List[List[float]]:
        """
        Compute pairwise agreement matrix.

        Returns matrix where matrix[i][j] is agreement score between
        candidate i and candidate j (0.0 to 1.0).
        """
        n = len(candidates)
        matrix = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 1.0
                elif j > i:
                    agree = self._structural_similarity(
                        candidates[i].get_fingerprint(),
                        candidates[j].get_fingerprint(),
                    )
                    matrix[i][j] = agree
                    matrix[j][i] = agree

        return matrix

    def _structural_similarity(self, fp1: str, fp2: str) -> float:
        """Calculate structural similarity between two fingerprints."""
        if fp1 == fp2:
            return 1.0
        if len(fp1) == 0 or len(fp2) == 0:
            return 0.0
        matches = sum(c1 == c2 for c1, c2 in zip(fp1, fp2))
        max_len = max(len(fp1), len(fp2))
        return matches / max_len

    def compute_agreement_scores(self, candidates: List[ConversionCandidate]) -> List[float]:
        """
        Compute agreement score for each candidate.

        Score is the average agreement with all other candidates.
        """
        if len(candidates) < 2:
            return [1.0] * len(candidates)

        matrix = self.compute_pairwise_agreement(candidates)
        scores = []
        n = len(candidates)

        for i in range(n):
            total = sum(matrix[i][j] for j in range(n) if j != i)
            avg = total / (n - 1)
            scores.append(avg)

        return scores

    def rank_candidates(self, candidates: List[ConversionCandidate]) -> List[Tuple[int, float]]:
        """
        Rank candidates by agreement score (highest first).

        Returns list of (candidate_id, score) tuples sorted by score.
        """
        scores = self.compute_agreement_scores(candidates)
        rankings = list(enumerate(scores))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def find_consensus_code(
        self, candidates: List[ConversionCandidate]
    ) -> Tuple[Optional[str], float]:
        """
        Find consensus code among candidates.

        Returns (code, agreement_rate) where code is the most common
        normalized form and agreement_rate is fraction of candidates
        that agree with it.
        """
        if not candidates:
            return None, 0.0

        fingerprints = [c.get_fingerprint() for c in candidates]
        unique_fps = set(fingerprints)

        if len(unique_fps) == 1:
            return candidates[0].code, 1.0

        fp_counts: Dict[str, int] = {}
        fp_to_code: Dict[str, str] = {}
        for cand, fp in zip(candidates, fingerprints):
            fp_counts[fp] = fp_counts.get(fp, 0) + 1
            if fp not in fp_to_code:
                fp_to_code[fp] = cand.code

        max_count = max(fp_counts.values())
        consensus_fp = max(fp_counts, key=fp_counts.get)
        agreement = max_count / len(candidates)

        return fp_to_code[consensus_fp], agreement

    def check_consistency(self, candidates: List[ConversionCandidate]) -> ConsistencyResult:
        """
        Check consistency across all candidates using DPC strategy.

        Returns ConsistencyResult with:
        - selected_candidate: The most consistent candidate
        - agreement_score: Overall agreement score
        - candidate_rankings: Ranked list of (id, score) pairs
        - flagged_candidates: IDs that need review
        - consensus_code: Code that most candidates agree on
        - confidence: Calibrated confidence score
        - needs_review: Whether any candidate was flagged
        """
        if len(candidates) < self.config.min_candidates_for_selection:
            return ConsistencyResult(
                selected_candidate=candidates[0] if candidates else None,
                agreement_score=1.0,
                candidate_rankings=[(c.candidate_id, 1.0) for c in candidates],
                flagged_candidates=[],
                consensus_code=candidates[0].code if candidates else None,
                confidence=1.0,
                needs_review=False,
            )

        rankings = self.rank_candidates(candidates)
        dict(rankings)
        overall_agreement = sum(s for _, s in rankings) / len(rankings)

        consensus_code, consensus_rate = self.find_consensus_code(candidates)

        avg_agreement = sum(s for _, s in rankings) / len(rankings)
        conformity_offset = 1.0 - (1.0 / (len(candidates) + 1))
        confidence = avg_agreement * conformity_offset + (1 - conformity_offset) * 0.5
        confidence = max(0.0, min(1.0, confidence))

        flagged = []
        for cand_id, score in rankings:
            if score < self.config.agreement_threshold:
                flagged.append(cand_id)

        selected_id = rankings[0][0] if rankings else None
        selected = next((c for c in candidates if c.candidate_id == selected_id), None)

        return ConsistencyResult(
            selected_candidate=selected,
            agreement_score=overall_agreement,
            candidate_rankings=rankings,
            flagged_candidates=flagged,
            consensus_code=consensus_code,
            confidence=confidence,
            needs_review=len(flagged) > 0 or confidence < 0.6,
        )

    def select_best_candidate(
        self,
        candidates: List[ConversionCandidate],
        strategy: Optional[SelectionStrategy] = None,
    ) -> Tuple[Optional[ConversionCandidate], ConsistencyResult]:
        """
        Select the best candidate using specified strategy.

        Returns (selected_candidate, consistency_result).
        """
        strategy = strategy or self.config.selection_strategy
        consistency = self.check_consistency(candidates)

        if strategy == SelectionStrategy.MAJORITY_VOTE:
            selected = self._select_by_majority(candidates)
        elif strategy == SelectionStrategy.DPC_CONSISTENCY:
            selected = consistency.selected_candidate
        elif strategy == SelectionStrategy.STRUCTURAL_SIMILARITY:
            rankings = self.rank_candidates(candidates)
            best_id = rankings[0][0]
            selected = next((c for c in candidates if c.candidate_id == best_id), None)
        else:
            selected = consistency.selected_candidate

        return selected, consistency

    def _select_by_majority(
        self, candidates: List[ConversionCandidate]
    ) -> Optional[ConversionCandidate]:
        """Select candidate by majority vote on fingerprints."""
        fingerprints = [c.get_fingerprint() for c in candidates]
        unique_fps = set(fingerprints)

        if len(unique_fps) == 1:
            return candidates[0]

        fp_counts: Dict[str, List[ConversionCandidate]] = {}
        for cand, fp in zip(candidates, fingerprints):
            if fp not in fp_counts:
                fp_counts[fp] = []
            fp_counts[fp].append(cand)

        most_common_fp = max(fp_counts, key=lambda fp: len(fp_counts[fp]))
        return fp_counts[most_common_fp][0]


class CandidateGenerator:
    """
    Generates multiple candidate conversions with varied parameters.

    Used to produce N candidates for DPC-style selection where each
    candidate uses different temperature/prompt settings to capture
    different interpretation possibilities.
    """

    def __init__(self, config: Optional[CandidateConfig] = None):
        self.config = config or CandidateConfig()
        self.consistency_checker = MultiCandidateConsistencyChecker(self.config)

    def create_candidate(
        self,
        candidate_id: int,
        code: str,
        temperature: float = 0.3,
        prompt_suffix: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversionCandidate:
        """Create a single conversion candidate."""
        return ConversionCandidate(
            candidate_id=candidate_id,
            code=code,
            temperature=temperature,
            prompt_suffix=prompt_suffix,
            metadata=metadata or {},
        )

    def generate_candidates(
        self,
        segment_id: str,
        conversion_func: Callable[[str, Dict[str, Any]], str],
        java_segment: str,
    ) -> List[ConversionCandidate]:
        """
        Generate N candidate conversions for a Java segment.

        Args:
            segment_id: Unique identifier for this segment
            conversion_func: Function that converts Java to Bedrock code
                              signature: (java_code: str, config: dict) -> str
            java_segment: The Java code segment to convert

        Returns:
            List of ConversionCandidate objects
        """
        configs = self.consistency_checker.generate_candidate_configs()
        candidates = []

        for cfg in configs:
            try:
                config_dict = {
                    "temperature": cfg["temperature"],
                    "prompt_suffix": cfg["prompt_suffix"],
                    "segment_id": segment_id,
                }
                code = conversion_func(java_segment, config_dict)
                candidate = self.create_candidate(
                    candidate_id=cfg["candidate_id"],
                    code=code,
                    temperature=cfg["temperature"],
                    prompt_suffix=cfg["prompt_suffix"],
                    metadata={"segment_id": segment_id},
                )
                candidates.append(candidate)
            except Exception as e:
                logger.warning(
                    f"Failed to generate candidate {cfg['candidate_id']} for {segment_id}: {e}"
                )

        return candidates

    def select_and_validate(
        self,
        candidates: List[ConversionCandidate],
    ) -> Tuple[Optional[ConversionCandidate], ConsistencyResult]:
        """
        Select best candidate and validate consistency.

        Returns (selected_candidate, consistency_result).
        """
        return self.consistency_checker.select_best_candidate(candidates)


def create_candidate_result(
    candidate_id: int,
    code: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> ConversionCandidate:
    """Helper function to create a candidate result."""
    return ConversionCandidate(
        candidate_id=candidate_id,
        code=code,
        metadata=metadata or {},
    )


def dpc_consistency_check(
    candidates: List[ConversionCandidate],
    agreement_threshold: float = 0.7,
) -> ConsistencyResult:
    """
    Convenience function for DPC consistency check.

    Args:
        candidates: List of conversion candidates
        agreement_threshold: Minimum agreement score to avoid flagging

    Returns:
        ConsistencyResult with selection and flagging info
    """
    config = CandidateConfig(
        agreement_threshold=agreement_threshold,
        selection_strategy=SelectionStrategy.DPC_CONSISTENCY,
    )
    checker = MultiCandidateConsistencyChecker(config)
    return checker.check_consistency(candidates)


def convert_candidates_to_traces(
    candidates: List[ConversionCandidate],
    traces_data: Optional[List[List[Dict[str, Any]]]] = None,
    default_confidence: float = 0.7,
) -> List["ReasoningTrace"]:
    """
    Convert ConversionCandidates to ReasoningTraces for VecCISC analysis.

    Args:
        candidates: List of conversion candidates from multi-candidate pipeline
        traces_data: Optional list of reasoning traces (step content + embeddings)
                     for each candidate. If not provided, generates synthetic
                     traces from candidate code.
        default_confidence: Default confidence for candidates without explicit traces

    Returns:
        List of ReasoningTrace objects for VecCISC analysis
    """
    from qa.veccisc import create_reasoning_trace

    traces = []
    for i, cand in enumerate(candidates):
        if traces_data and i < len(traces_data) and traces_data[i]:
            steps = traces_data[i]
            confidence = cand.metadata.get("confidence", default_confidence)
        else:
            reasoning_content = (
                f"Converting Java code with candidate {cand.candidate_id} "
                f"(temp={cand.temperature}). "
                f"Code structure: {cand.get_fingerprint()[:8]}"
            )
            steps = [
                {"content": f"Step 1: Parse Java source structure"},
                {"content": f"Step 2: Map Java patterns to Bedrock equivalents"},
                {"content": f"Step 3: Generate Bedrock JSON and TypeScript"},
                {"content": reasoning_content},
            ]
            confidence = cand.metadata.get("confidence", default_confidence)

        trace = create_reasoning_trace(
            candidate_id=cand.candidate_id,
            steps=steps,
            confidence=confidence,
            final_answer=cand.code,
            metadata=cand.metadata,
        )
        traces.append(trace)

    return traces


def veccisc_multi_candidate_selection(
    candidates: List[ConversionCandidate],
    traces_data: Optional[List[List[Dict[str, Any]]]] = None,
    n_candidates: int = 3,
    trace_similarity_threshold: float = 0.75,
    confidence_threshold: float = 0.5,
) -> Tuple[Optional[ConversionCandidate], "VecCISCCandidateResult"]:
    """
    Select best candidate using VecCISC on multi-candidate outputs.

    Combines the multi-candidate generation pipeline with VecCISC reasoning
    trace clustering for improved selection.

    Args:
        candidates: List of conversion candidates
        traces_data: Optional reasoning traces for each candidate
        n_candidates: Number of candidates (for selector config)
        trace_similarity_threshold: Minimum similarity for clustering
        confidence_threshold: Minimum confidence threshold

    Returns:
        Tuple of (selected ConversionCandidate, VecCISCCandidateResult)
    """
    from qa.veccisc import VecCISCSelector

    if not candidates:
        return None, None

    traces = convert_candidates_to_traces(candidates, traces_data)

    selector = VecCISCSelector(
        n_candidates=n_candidates,
        trace_similarity_threshold=trace_similarity_threshold,
        confidence_threshold=confidence_threshold,
    )

    result = selector.select_with_fallback(traces)

    selected_candidate = next(
        (c for c in candidates if c.candidate_id == result.selected_candidate_id),
        None,
    )

    return selected_candidate, result
