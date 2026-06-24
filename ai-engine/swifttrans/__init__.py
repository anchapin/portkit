"""
SwiftTrans Dual-Stage Strategy for runtime-efficient Bedrock code generation.

Implements the two-stage translation framework from *SwiftTrans: Bridging
Functional Correctness and Runtime Efficiency Gaps in LLM-Based Code
Translation* (https://arxiv.org/abs/2606.17683) for the PortKit Java →
Bedrock conversion pipeline.

Stages
------

* **Stage 1 — MpTranslator** (:mod:`swifttrans.candidate_generator`):
  generates ``N`` diverse translation candidates in parallel using
  Hierarchical Guidance prompt variants. Each variant emphasises a
  different secondary constraint (efficiency, idiomaticity, minimal
  allocation, structural fidelity) so Stage 2 has genuine differences to
  compare.
* **Stage 2 — DiffSelector** (:mod:`swifttrans.diff_selector`):
  ranks the candidates using *Difference-Aware Selection*. A deterministic
  :class:`BedrockEfficiencyScorer` (Phase 3) acts as a cheap pre-filter,
  then a pluggable :class:`RankingJudge` performs Ordinal Guidance ranking
  over the survivors.

The full flow is opt-in via :class:`SwiftTransConfig.enabled`. The default
is ``False`` so landing this module does not change the existing single-pass
behaviour of the LangGraph conversion pipeline.

Scope vs. the issue
-------------------

* Phase 1 (parallel candidate generation): **implemented**.
* Phase 2 (difference-aware selection): **implemented** (heuristic judge by
  default; LLM judge is pluggable via :class:`RankingJudge`).
* Phase 3 (Bedrock static efficiency scorer): **implemented**.
* Phase 4 (MMSD fine-tuning data enrichment): **deferred** — it is a
  data-labelling task on the training pipeline and is tracked separately
  in ``docs/swifttrans-dual-stage.md``.

See ``docs/swifttrans-dual-stage.md`` for the design notes and remaining
integration work.
"""

from swifttrans.candidate_generator import (
    MpTranslator,
    StubTranslator,
    Translator,
    TranslatorCallable,
    create_mp_translator,
    create_stub_translator,
)
from swifttrans.diff_selector import (
    DiffSelector,
    HeuristicRankingJudge,
    RankingJudge,
    create_diff_selector,
    create_heuristic_judge,
)
from swifttrans.efficiency_scorer import (
    BedrockEfficiencyScorer,
    create_efficiency_scorer,
)
from swifttrans.models import (
    CandidateRanking,
    CandidateVariant,
    DualStageResult,
    EfficiencyAntiPattern,
    EfficiencyScore,
    EfficiencyTier,
    EfficiencyViolation,
    SwiftTransConfig,
    TranslationCandidate,
)
from swifttrans.strategy import (
    SwiftTransStrategy,
    create_swifttrans_strategy,
)

__version__ = "0.1.0"

__all__ = [
    # Strategy orchestrator
    "SwiftTransStrategy",
    "create_swifttrans_strategy",
    # Stage 1
    "MpTranslator",
    "Translator",
    "TranslatorCallable",
    "StubTranslator",
    "create_mp_translator",
    "create_stub_translator",
    # Stage 2
    "DiffSelector",
    "RankingJudge",
    "HeuristicRankingJudge",
    "create_diff_selector",
    "create_heuristic_judge",
    # Phase 3
    "BedrockEfficiencyScorer",
    "create_efficiency_scorer",
    # Models
    "CandidateRanking",
    "CandidateVariant",
    "DualStageResult",
    "EfficiencyAntiPattern",
    "EfficiencyScore",
    "EfficiencyTier",
    "EfficiencyViolation",
    "SwiftTransConfig",
    "TranslationCandidate",
]
