"""
Phase 1 — MpTranslator: multi-perspective translation candidate generation.

Implements the *Multi-Perspective Exploration* stage of SwiftTrans
(https://arxiv.org/abs/2606.17683, §3.1). Instead of a single LLM call that
produces one translation, Stage 1 fans out N parallel translation requests
whose prompts apply *Hierarchical Guidance*: structural constraints first,
then semantic / efficiency constraints. Each variant emphasises a different
axis so the DiffSelector in Stage 2 has genuine, comparable differences to
rank — the core empirical finding of the paper.

The actual LLM call is injected via a ``translator`` callable so the
component is unit-testable without a live model, and so PortKit's existing
:class:`LogicTranslatorAgent` (or any future LangGraph node) can be wired in
without coupling.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from swifttrans.models import CandidateVariant, SwiftTransConfig, TranslationCandidate

logger = logging.getLogger(__name__)


@runtime_checkable
class Translator(Protocol):
    """Minimal interface a Stage 1 translator callable must satisfy.

    The callable receives the *fully-built* variant prompt plus the original
    Java source and returns a Bedrock JS/TS candidate. Defining this as a
    Protocol (rather than a concrete class) keeps the strategy decoupled
    from any specific agent framework — a plain ``def``, a LangChain
    ``Runnable``, or a bound :meth:`LogicTranslatorAgent.translate` method
    all satisfy it.
    """

    def __call__(self, prompt: str, java_source: str) -> str: ...


# Variant prompt templates.
#
# These are the *Hierarchical Guidance* instructions: each variant leads
# with the structural constraint (output must be valid Bedrock JS), then
# layers a different secondary constraint. Keeping the structural prefix
# identical across variants isolates the variable the DiffSelector is
# supposed to be sensitive to.
_STRUCTURAL_PREFIX = (
    "You are translating Java Minecraft mod logic to Bedrock Edition JavaScript "
    "(Script API 2.x). The output MUST be syntactically valid JavaScript that runs "
    "inside the Bedrock tick budget (20 Hz). Preserve the original mod's observable "
    "behaviour (block interactions, entity spawning, event handling).\n\n"
)

_VARIANT_GUIDANCE: dict[CandidateVariant, str] = {
    CandidateVariant.BASELINE: (
        _STRUCTURAL_PREFIX + "Translate the following Java code as faithfully as possible. Do not "
        "optimise beyond what is required for correctness.\n\n"
    ),
    CandidateVariant.EFFICIENCY_FOCUSED: (
        _STRUCTURAL_PREFIX
        + "PRIMARY SECONDARY CONSTRAINT — RUNTIME EFFICIENCY: the generated code "
        "must minimise per-tick work. Hoist object allocations out of tick "
        "callbacks, cache repeated API calls, and avoid unbounded entity queries. "
        "Prefer event-driven scheduling over polling. If two implementations are "
        "equally correct, emit the faster one.\n\n"
    ),
    CandidateVariant.IDIOMATIC_BEDROCK: (
        _STRUCTURAL_PREFIX + "PRIMARY SECONDARY CONSTRAINT — BEDROCK IDIOMATICITY: prefer native "
        "Bedrock Scripting APIs (@minecraft/server) over reimplementing Java "
        "constructs. Use ``system.runInterval`` for tick scheduling, "
        "``EntityQueryOptions`` for entity filtering, and the ``world.afterEvents`` "
        "API surface instead of polling. Avoid mimicking Java's class hierarchy "
        "when a Bedrock component does the same job.\n\n"
    ),
    CandidateVariant.MINIMAL_ALLOCATION: (
        _STRUCTURAL_PREFIX + "PRIMARY SECONDARY CONSTRAINT — MINIMAL ALLOCATION: treat the Bedrock "
        "garbage collector as a budget. Reuse objects by mutation, avoid ``new`` "
        "inside ``runInterval`` callbacks, and prefer typed arrays over object "
        "arrays for hot paths. String-build with ``.join()`` rather than ``+=``.\n\n"
    ),
    CandidateVariant.STRUCTURAL_FIRST: (
        _STRUCTURAL_PREFIX + "PRIMARY SECONDARY CONSTRAINT — STRUCTURAL FIDELITY: the translation "
        "must mirror the Java control flow as closely as Bedrock allows so a "
        "human reviewer can diff the two. Optimisations are acceptable only when "
        "they do not obscure the structural correspondence.\n\n"
    ),
}


class MpTranslator:
    """Stage 1 — generate N diverse translation candidates in parallel.

    The SwiftTrans paper shows that prompt-engineering a single LLM call is
    *not* enough to close the runtime-efficiency gap; you need genuine
    diversity across candidates. This class produces that diversity by
    fanning out one prompt per :class:`CandidateVariant` and collecting the
    outputs as a ranked *set* (ranked later by the DiffSelector).
    """

    def __init__(
        self,
        translator: Optional[Translator] = None,
        config: Optional[SwiftTransConfig] = None,
    ):
        self.translator = translator
        self.config = config or SwiftTransConfig()

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_prompt(variant: CandidateVariant, java_source: str) -> str:
        """Return the full prompt for ``variant`` applied to ``java_source``.

        Exposed as a staticmethod so callers (and tests) can audit the
        exact prompt sent to the LLM for any variant without invoking the
        translator — a requirement for reproducible B2B conversions.
        """
        if variant not in _VARIANT_GUIDANCE:
            raise ValueError(f"Unknown candidate variant: {variant!r}")
        guidance = _VARIANT_GUIDANCE[variant]
        return f"{guidance}Java source:\n```java\n{java_source}\n```"

    # ------------------------------------------------------------------ #
    # Candidate generation
    # ------------------------------------------------------------------ #
    def generate_candidates(self, java_source: str) -> list[TranslationCandidate]:
        """Generate one candidate per configured variant.

        Args:
            java_source: The Java source to translate. If empty, the
                ``java_source`` from ``self.config`` is used as a fallback.

        Returns:
            A list of :class:`TranslationCandidate`, one per configured
            variant. Order matches ``self.config.variants``.

        Raises:
            RuntimeError: If no translator callable was provided. The
                strategy module is responsible for short-circuiting when
                no real translator is wired in (e.g. in tests).
        """
        if self.translator is None:
            raise RuntimeError(
                "MpTranslator.generate_candidates requires a translator callable; "
                "configure SwiftTransStrategy with a Translator or call "
                "build_prompt() directly for prompt-only auditing."
            )

        source = java_source or self.config.java_source
        variants = list(self.config.variants)

        candidates: list[TranslationCandidate] = []
        for variant in variants:
            prompt = self.build_prompt(variant, source)
            logger.debug("MpTranslator generating candidate for variant=%s", variant.value)
            code = self.translator(prompt, source)
            candidates.append(
                TranslationCandidate(
                    code=code,
                    variant=variant,
                    prompt=prompt,
                    metadata={"generator": "MpTranslator"},
                )
            )
        return candidates

    def generate_prompts(self, java_source: str) -> list[tuple[CandidateVariant, str]]:
        """Return ``(variant, prompt)`` pairs without invoking the translator.

        Useful when the caller wants to drive the LLM fan-out through a
        different scheduler (e.g. a LangGraph ``Send`` fan-out) while still
        using the canonical SwiftTrans prompt variants.
        """
        source = java_source or self.config.java_source
        return [(v, self.build_prompt(v, source)) for v in self.config.variants]


# ---------------------------------------------------------------------- #
# Factory + a deterministic stub translator for testing / dry-runs
# ---------------------------------------------------------------------- #
def create_mp_translator(
    translator: Optional[Translator] = None,
    config: Optional[SwiftTransConfig] = None,
) -> MpTranslator:
    """Factory: build an :class:`MpTranslator`."""
    return MpTranslator(translator=translator, config=config)


class StubTranslator:
    """Deterministic translator used by tests and as a dry-run default.

    Produces variant-distinguishable output by echoing the variant name as
    a comment, so downstream stages (DiffSelector, efficiency scorer) have
    something concrete to rank. This mirrors the SwiftTrans evaluation
    harness, which uses stub translators to validate the ranking logic in
    isolation from LLM variance.
    """

    def __init__(self, *, echo_java: bool = False):
        self.echo_java = echo_java

    def __call__(self, prompt: str, java_source: str) -> str:
        # Identify which variant produced this output so downstream ranking
        # has a signal; we sniff the guidance constraint from the prompt.
        if "RUNTIME EFFICIENCY" in prompt:
            tag = "efficiency-focused"
            body = self._efficient_body()
        elif "BEDROCK IDIOMATICITY" in prompt:
            tag = "idiomatic-bedrock"
            body = self._idiomatic_body()
        elif "MINIMAL ALLOCATION" in prompt:
            tag = "minimal-allocation"
            body = self._minimal_alloc_body()
        elif "STRUCTURAL FIDELITY" in prompt:
            tag = "structural-first"
            body = self._structural_body()
        else:
            tag = "baseline"
            body = self._baseline_body()

        echo = f"// java_source_lines={len(java_source.splitlines())}\n" if self.echo_java else ""
        return f"// generated by SwiftTrans StubTranslator ({tag})\n{echo}{body}"

    @staticmethod
    def _efficient_body() -> str:
        return (
            "import { system, world } from '@minecraft/server';\n"
            "const cached = new Map();\n"  # hoisted allocation — efficient
            "system.runInterval(() => {\n"
            "  if (!cached.has('k')) cached.set('k', computeOnce());\n"
            "  handle(cached.get('k'));\n"
            "}, 20);\n"
        )

    @staticmethod
    def _idiomatic_body() -> str:
        return (
            "import { world } from '@minecraft/server';\n"
            "world.afterEvents.entitySpawn.subscribe(ev => handle(ev));\n"
        )

    @staticmethod
    def _minimal_alloc_body() -> str:
        return (
            "import { system } from '@minecraft/server';\n"
            "const buf = new Array(16);\n"  # reused buffer — minimal alloc
            "system.runInterval(() => {\n"
            "  for (let i = 0; i < buf.length; i++) buf[i] = i;\n"
            "}, 20);\n"
        )

    @staticmethod
    def _structural_body() -> str:
        return "// structural mirror of Java control flow\nfunction onTick() { handleState(); }\n"

    @staticmethod
    def _baseline_body() -> str:
        # Deliberately contains an inefficiency so the scorer has signal.
        return (
            "import { system, world } from '@minecraft/server';\n"
            "system.runInterval(() => {\n"
            "  const fresh = new Object();\n"  # per-tick allocation — flagged
            "  fresh.x = world.getEntities();\n"  # unbounded + redundant
            "}, 20);\n"
        )


def create_stub_translator(*, echo_java: bool = False) -> StubTranslator:
    """Factory: build a :class:`StubTranslator`."""
    return StubTranslator(echo_java=echo_java)


# Convenience: a callable type alias for callers that don't want to import
# the Protocol. This is the signature any real PortKit translator must match.
TranslatorCallable = Callable[[str, str], str]

# Public re-export so ``from swifttrans.candidate_generator import Translator`` works.
__all__ = [
    "MpTranslator",
    "Translator",
    "TranslatorCallable",
    "StubTranslator",
    "create_mp_translator",
    "create_stub_translator",
]


# Silence unused-import linter for ``Any`` (kept for forward-compat typing).
_ = Any
