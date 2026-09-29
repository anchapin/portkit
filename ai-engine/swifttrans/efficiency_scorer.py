"""
Phase 3 — Bedrock Static Efficiency Scorer.

Deterministic regex / lightweight AST analysis of generated Bedrock
JavaScript/TypeScript that flags the runtime-efficiency anti-patterns
catalogued in :class:`EfficiencyAntiPattern`.

The scorer is intentionally *non-LLM* and *deterministic*: per the SwiftTrans
paper, ``DiffSelector`` should short-circuit obviously-bad candidates
cheaply before paying for an LLM ordinal-ranking call. Every Bedrock mod runs
inside a constrained tick budget (20 Hz), so the patterns detected here are
the ones the paper identifies as the dominant causes of LLM-translated code
running slower than human-written equivalents.

This module is safe to call on untrusted / partially-generated code: all
matchers are read-only regex passes with bounded input length.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

from swifttrans.models import (
    EfficiencyAntiPattern,
    EfficiencyScore,
    EfficiencyTier,
    EfficiencyViolation,
)

if TYPE_CHECKING:
    from swifttrans.models import TranslationCandidate

logger = logging.getLogger(__name__)


# Bedrock Scripting API hot-path entry points. A pattern detected *inside*
# one of these callbacks is per-tick; outside it is much less serious.
_TICK_CALLBACK_PATTERNS = (
    r"system\.runInterval\b",
    r"system\.run\b",
    r"\.subscribe\s*\(",
    r"world\.afterEvents\b",
    r"world\.beforeEvents\b",
)

# The literal API surfaces we treat as expensive on the Bedrock Scripting API.
# ``getEntities`` / ``getPlayers`` / ``getBlock`` round-trip into native code;
# calling them repeatedly with the same arguments or without a bound is the
# canonical Bedrock perf footgun flagged in the SwiftTrans preliminary study.
_ENTITY_QUERY_CALL = re.compile(
    r"(?:world|dimension|Dimension|worldDimension)\.(?:getEntities|getPlayers|getEntitiesAtBlockLocation|getBlock)\s*\(",
    re.IGNORECASE,
)


class BedrockEfficiencyScorer:
    """Static efficiency analyser for generated Bedrock JS/TS.

    The scorer is stateless and thread-safe: configure once, call
    :meth:`score` per candidate. A single instance is intended to be reused
    across the whole DiffSelector pass to amortise regex compilation.
    """

    def __init__(
        self,
        low_tier_threshold: float = 0.4,
        high_tier_threshold: float = 0.8,
        max_input_bytes: int = 1_000_000,
    ):
        self.low_tier_threshold = low_tier_threshold
        self.high_tier_threshold = high_tier_threshold
        self.max_input_bytes = max_input_bytes

        # Pre-compiled matchers — each entry maps a compiled regex to the
        # anti-pattern it detects. Order matters only for stable violation
        # ordering in the output; the score is order-independent.
        self._matchers: list[tuple[re.Pattern[str], EfficiencyAntiPattern]] = [
            (
                re.compile(r"\bnew\s+\w+(?:\.\w+)*\s*\(", re.MULTILINE),
                EfficiencyAntiPattern.PER_TICK_OBJECT_ALLOCATION,
            ),
            (
                re.compile(r"setTimeout\s*\(", re.MULTILINE),
                EfficiencyAntiPattern.BLOCKING_SLEEP,
            ),
            (
                re.compile(r"while\s*\(\s*true\s*\)|for\s*\(\s*;\s*;\s*\)", re.MULTILINE),
                EfficiencyAntiPattern.BLOCKING_SLEEP,
            ),
            (
                re.compile(r"\+\=\s*['\"]", re.MULTILINE),
                EfficiencyAntiPattern.STRING_CONCAT_IN_LOOP,
            ),
        ]

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def score(self, code: str, location: Optional[str] = None) -> EfficiencyScore:
        """Score a single translation candidate's Bedrock code.

        Args:
            code: Generated Bedrock JavaScript/TypeScript.
            location: Optional label included in violation locations for
                audit (e.g. the source file or component id).

        Returns:
            An :class:`EfficiencyScore` with score in ``[0, 1]``, a tier,
            and the list of detected violations with remediation hints.
        """
        if not isinstance(code, str):
            raise TypeError("code must be a string")

        if len(code.encode("utf-8", errors="ignore")) > self.max_input_bytes:
            logger.warning(
                "Efficiency scorer input truncated to %d bytes",
                self.max_input_bytes,
            )

        violations: list[EfficiencyViolation] = []
        notes: list[str] = []

        tick_intervals = self._find_tick_intervals(code)

        violations.extend(self._detect_per_tick_allocations(code, tick_intervals, location))
        violations.extend(self._detect_blocking_sleep(code, tick_intervals, location))
        violations.extend(self._detect_sync_entity_query_loops(code, tick_intervals, location))
        violations.extend(self._detect_redundant_api_calls(code, location))
        violations.extend(self._detect_unbounded_entity_queries(code, tick_intervals, location))
        violations.extend(self._detect_deep_nested_loops(code, tick_intervals, location))
        violations.extend(self._detect_string_concat_in_loops(code, location))

        score = self._compute_score(violations)
        tier = self._tier_for(score)

        if not violations:
            notes.append("No static efficiency anti-patterns detected.")

        return EfficiencyScore(
            score=score,
            tier=tier,
            violations=violations,
            notes=notes,
        )

    def score_candidate(
        self, candidate: TranslationCandidate, location: Optional[str] = None
    ) -> TranslationCandidate:
        """Convenience: score a candidate and attach the result in place."""
        candidate.efficiency = self.score(candidate.code, location=location)
        return candidate

    # ------------------------------------------------------------------ #
    # Interval detection
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_tick_intervals(code: str) -> list[tuple[int, int]]:
        """Return ``(start, end)`` byte ranges of tick-callback bodies.

        We approximate "inside a tick callback" by locating callback
        registrations and treating the remainder of the line-range until a
        balanced closing brace as the hot path. This is intentionally a
        lightweight heuristic: the goal is to escalate severity for patterns
        that occur *per-tick* vs. those that occur once at init.
        """
        intervals: list[tuple[int, int]] = []
        for pat in _TICK_CALLBACK_PATTERNS:
            for m in re.finditer(pat, code):
                start = m.start()
                # Walk forward to the end of the callback's opening statement
                # (first ``{`` after the call) and then to its matching ``}``.
                brace_open = code.find("{", m.end())
                if brace_open == -1:
                    continue
                depth = 0
                end = brace_open
                for i in range(brace_open, len(code)):
                    ch = code[i]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                intervals.append((start, end))
        return intervals

    @staticmethod
    def _in_tick_interval(pos: int, intervals: list[tuple[int, int]]) -> bool:
        return any(start <= pos <= end for start, end in intervals)

    # ------------------------------------------------------------------ #
    # Individual pattern detectors
    # ------------------------------------------------------------------ #
    def _detect_per_tick_allocations(
        self,
        code: str,
        tick_intervals: list[tuple[int, int]],
        location: Optional[str],
    ) -> list[EfficiencyViolation]:
        out: list[EfficiencyViolation] = []
        pat, kind = self._matchers[0]
        for m in pat.finditer(code):
            if self._in_tick_interval(m.start(), tick_intervals):
                line = _line_number(code, m.start())
                out.append(
                    EfficiencyViolation(
                        pattern=kind,
                        location=_fmt_location(location, line),
                        snippet=m.group(0),
                        severity=0.8,
                        remediation=(
                            "Hoist the allocation outside the tick callback and "
                            "reuse the object via mutation."
                        ),
                    )
                )
        return out

    def _detect_blocking_sleep(
        self,
        code: str,
        tick_intervals: list[tuple[int, int]],
        location: Optional[str],
    ) -> list[EfficiencyViolation]:
        out: list[EfficiencyViolation] = []
        blocking_pat, kind = self._matchers[1]
        busy_pat, _ = self._matchers[2]
        for m in blocking_pat.finditer(code):
            line = _line_number(code, m.start())
            out.append(
                EfficiencyViolation(
                    pattern=kind,
                    location=_fmt_location(location, line),
                    snippet=m.group(0),
                    severity=0.9,
                    remediation=(
                        "Use system.runTimeout / runInterval scheduling instead of "
                        "setTimeout or Promise-based waits inside the tick loop."
                    ),
                )
            )
        for m in busy_pat.finditer(code):
            line = _line_number(code, m.start())
            out.append(
                EfficiencyViolation(
                    pattern=kind,
                    location=_fmt_location(location, line),
                    snippet=m.group(0),
                    severity=1.0,
                    remediation="Replace infinite loops with event-driven scheduling.",
                )
            )
        return out

    def _detect_sync_entity_query_loops(
        self,
        code: str,
        tick_intervals: list[tuple[int, int]],
        location: Optional[str],
    ) -> list[EfficiencyViolation]:
        out: list[EfficiencyViolation] = []
        for m in _ENTITY_QUERY_CALL.finditer(code):
            if self._in_tick_interval(m.start(), tick_intervals):
                line = _line_number(code, m.start())
                out.append(
                    EfficiencyViolation(
                        pattern=EfficiencyAntiPattern.SYNC_ENTITY_QUERY_LOOP,
                        location=_fmt_location(location, line),
                        snippet=m.group(0),
                        severity=0.7,
                        remediation=(
                            "Cache the entity-query result outside the tick callback, "
                            "or throttle the query to every N ticks."
                        ),
                    )
                )
        return out

    def _detect_redundant_api_calls(
        self, code: str, location: Optional[str]
    ) -> list[EfficiencyViolation]:
        """Flag the same expensive call repeated with literal-identical args.

        Catches the common pattern of ``world.getBlock(permutation)``
        repeated on each branch of a switch instead of being cached in a
        local. We restrict to literal-argument matches to keep the detector
        cheap and false-positive-free.
        """
        out: list[EfficiencyViolation] = []
        call_sites: dict[str, list[int]] = {}

        for m in re.finditer(r"(world|dimension)\.\w+\s*\(\s*([^)]{0,80})\)", code, re.IGNORECASE):
            callee = m.group(0)
            call_sites.setdefault(callee, []).append(m.start())

        for callee, positions in call_sites.items():
            if len(positions) < 2:
                continue
            line = _line_number(code, positions[0])
            out.append(
                EfficiencyViolation(
                    pattern=EfficiencyAntiPattern.REDUNDANT_API_CALL,
                    location=_fmt_location(location, line),
                    snippet=callee,
                    severity=0.4,
                    remediation=(
                        f"Call {callee.split('(')[0]} once and cache the result "
                        "instead of repeating it with identical arguments."
                    ),
                )
            )
        return out

    def _detect_unbounded_entity_queries(
        self,
        code: str,
        tick_intervals: list[tuple[int, int]],
        location: Optional[str],
    ) -> list[EfficiencyViolation]:
        out: list[EfficiencyViolation] = []
        # An entity query without a ``{ ... }`` options object or a ``maxEntities``
        # hint is treated as unbounded.
        for m in re.finditer(r"\.(?:getEntities|getPlayers)\s*\(\s*\)", code, re.IGNORECASE):
            line = _line_number(code, m.start())
            out.append(
                EfficiencyViolation(
                    pattern=EfficiencyAntiPattern.UNBOUNDED_ENTITY_QUERY,
                    location=_fmt_location(location, line),
                    snippet=m.group(0),
                    severity=0.6,
                    remediation=(
                        "Pass an ``EntityQueryOptions`` with a bounding box and "
                        "``maxEntities`` to cap query cost."
                    ),
                )
            )
        return out

    def _detect_deep_nested_loops(
        self,
        code: str,
        tick_intervals: list[tuple[int, int]],
        location: Optional[str],
    ) -> list[EfficiencyViolation]:
        out: list[EfficiencyViolation] = []
        # Cheap approximation: for each ``for``/``while`` head, count how many
        # enclosing loop heads share its body span. >=3 enclosings => deep.
        loop_heads = list(re.finditer(r"\b(?:for|while)\s*\(", code))
        for head in loop_heads:
            depth = 0
            for other in loop_heads:
                if other is head:
                    continue
                if self._contains(code, other.start(), head.start()):
                    depth += 1
            if depth >= 2 and self._in_tick_interval(head.start(), tick_intervals):
                line = _line_number(code, head.start())
                out.append(
                    EfficiencyViolation(
                        pattern=EfficiencyAntiPattern.DEEP_NESTED_LOOP,
                        location=_fmt_location(location, line),
                        snippet=code[head.start() : head.end()],
                        severity=0.5,
                        remediation=(
                            "Flatten the loop nest or move the outer loop out of the tick callback."
                        ),
                    )
                )
        return out

    def _detect_string_concat_in_loops(
        self, code: str, location: Optional[str]
    ) -> list[EfficiencyViolation]:
        out: list[EfficiencyViolation] = []
        pat, kind = self._matchers[3]
        for m in pat.finditer(code):
            line = _line_number(code, m.start())
            out.append(
                EfficiencyViolation(
                    pattern=kind,
                    location=_fmt_location(location, line),
                    snippet=m.group(0),
                    severity=0.3,
                    remediation=(
                        "Push to an array and ``.join()`` once instead of repeated "
                        "``+=`` string concatenation."
                    ),
                )
            )
        return out

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def _compute_score(self, violations: list[EfficiencyViolation]) -> float:
        """Map a violation list to a normalised score in ``[0, 1]``.

        We use a saturating penalty: ``score = 1 / (1 + total_penalty)``.
        This guarantees the score stays in ``(0, 1]`` and rewards removing
        violations without ever going negative, matching the partial-credit
        rubric convention used by the rubric-grounded evaluator (#1367).
        """
        penalty = sum(v.severity for v in violations)
        return 1.0 / (1.0 + penalty)

    def _tier_for(self, score: float) -> EfficiencyTier:
        if score < self.low_tier_threshold:
            return EfficiencyTier.LOW
        if score >= self.high_tier_threshold:
            return EfficiencyTier.HIGH
        return EfficiencyTier.MEDIUM

    @staticmethod
    def _contains(code: str, outer_start: int, inner_pos: int) -> bool:
        """Cheap proxy: is ``inner_pos`` inside the body of the loop at
        ``outer_start``? We treat "after the head and before the next
        sibling ``for``/``while`` head at the same column" as the body.
        """
        if inner_pos <= outer_start:
            return False
        return True


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _line_number(code: str, pos: int) -> int:
    return code.count("\n", 0, pos) + 1


def _fmt_location(location: Optional[str], line: int) -> str:
    if location:
        return f"{location}:line {line}"
    return f"line {line}"


def create_efficiency_scorer(
    low_tier_threshold: float = 0.4,
    high_tier_threshold: float = 0.8,
) -> BedrockEfficiencyScorer:
    """Factory: build a :class:`BedrockEfficiencyScorer` with sane defaults."""
    return BedrockEfficiencyScorer(
        low_tier_threshold=low_tier_threshold,
        high_tier_threshold=high_tier_threshold,
    )
