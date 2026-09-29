"""answer_synthesizer — Answer generation and citation tracking.

Seam: Extracted from AdvancedRagAgent._generate_answer and its five
_specialized generators (_generate_simple_answer, _generate_how_to_answer,
_generate_explanation_answer, _generate_example_answer, _generate_general_answer).
Turns a fused context block + ranked sources into the final answer string,
the confidence score, and the citation metadata returned in
:class:`RAGResponse`. Statless — dependencies (config, trimmer) are passed in.

Issue #1709 — Subpackage split for advanced_rag_agent.py (32K).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from schemas.multimodal_schema import SearchResult
from utils.token_optimizer import ContextTrimmer

from .query_router import (
    INTENT_EXAMPLE,
    INTENT_EXPLANATION,
    INTENT_HOW_TO,
    classify_query_intent,
)

logger = logging.getLogger(__name__)

# Roughly 4 characters per token in English text
CHARS_PER_TOKEN = 4


def _extract_how_to_steps(query: str, sources: List[SearchResult]) -> List[str]:
    """Pull numbered/bulleted step-like lines from the top sources."""
    steps: List[str] = []
    for source in sources[:3]:
        if not source.document.content_text:
            continue
        for line in source.document.content_text.split("\n"):
            line = line.strip()
            if (
                line.startswith(("1.", "2.", "3.", "-", "*"))
                or "step" in line.lower()
                or any(word in line.lower() for word in ["create", "define", "register", "add"])
            ):
                if 20 < len(line) < 200:
                    steps.append(line)
    return steps


def _generate_how_to_answer(query: str, context: str, sources: List[SearchResult]) -> str:
    """Generate a how-to style answer from step-like content."""
    steps = _extract_how_to_steps(query, sources)
    if steps:
        answer = f"Based on the available documentation, here's how to {query.lower()}:\n\n"
        for i, step in enumerate(steps[:5], 1):
            answer += f"{i}. {step.lstrip('123456789.-* ')}\n"
        answer += f"\nThis information is based on {len(sources)} relevant sources."
        return answer
    return _generate_general_answer(query, context, sources)


def _generate_explanation_answer(query: str, context: str, sources: List[SearchResult]) -> str:
    """Generate an explanatory answer focused on the most relevant source."""
    best_source = sources[0] if sources else None
    if best_source and best_source.document.content_text:
        content = best_source.document.content_text
        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 50]
        if paragraphs:
            main_explanation = paragraphs[0]
            answer = f"{main_explanation}\n\n"
            if len(sources) > 1:
                answer += "Additional details:\n"
                for source in sources[1:3]:
                    if source.document.content_text:
                        sentences = source.document.content_text.split(".")
                        key_sentence = next(
                            (
                                s.strip()
                                for s in sentences
                                if len(s.strip()) > 30
                                and any(word in s.lower() for word in query.lower().split())
                            ),
                            None,
                        )
                        if key_sentence:
                            answer += f"• {key_sentence}.\n"
            answer += f"\nSource: {best_source.document.source_path}"
            return answer
    return _generate_general_answer(query, context, sources)


def _generate_example_answer(query: str, context: str, sources: List[SearchResult]) -> str:
    """Generate an answer that surfaces code blocks and example sections."""
    examples: List[Tuple[str, str, str]] = []
    for source in sources:
        if not source.document.content_text:
            continue
        content = source.document.content_text

        code_blocks = re.findall(r"```[\w]*\n(.*?)```", content, re.DOTALL)
        for code in code_blocks:
            if len(code.strip()) > 20:
                examples.append(("code", code.strip(), source.document.source_path))

        lines = content.split("\n")
        in_example = False
        example_content: List[str] = []
        for line in lines:
            if "example" in line.lower() and ":" in line:
                in_example = True
                example_content = [line]
            elif in_example:
                if line.strip() and not line.startswith("#"):
                    example_content.append(line)
                elif len(example_content) > 2:
                    examples.append(
                        ("text", "\n".join(example_content), source.document.source_path)
                    )
                    in_example = False
                    example_content = []

    if examples:
        answer = "Here are examples related to your query:\n\n"
        for i, (example_type, content, source_path) in enumerate(examples[:3], 1):
            answer += f"**Example {i}** (from {source_path}):\n"
            if example_type == "code":
                answer += f"```\n{content}\n```\n\n"
            else:
                answer += f"{content}\n\n"
        return answer
    return _generate_general_answer(query, context, sources)


def _generate_general_answer(query: str, context: str, sources: List[SearchResult]) -> str:
    """Generate a generic answer from the most relevant source's paragraphs."""
    if not sources:
        return (
            "I couldn't find specific information about your query in the available documentation."
        )

    answer_parts: List[str] = []
    primary_source = sources[0]
    if primary_source.document.content_text:
        content = primary_source.document.content_text
        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 50]
        if paragraphs:
            query_words = set(query.lower().split())
            best_paragraph = max(
                paragraphs,
                key=lambda p: len(query_words.intersection(set(p.lower().split()))),
            )
            answer_parts.append(best_paragraph)

    if len(sources) > 1:
        supplementary_info: List[str] = []
        for source in sources[1:3]:
            if source.document.content_text:
                sentences = source.document.content_text.split(".")
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 30 and any(
                        word in sentence.lower() for word in query.lower().split()
                    ):
                        supplementary_info.append(sentence)
                        break
        if supplementary_info:
            answer_parts.append(
                "Additional information:\n" + "\n".join(f"• {info}." for info in supplementary_info)
            )

    if answer_parts:
        answer = "\n\n".join(answer_parts)
        answer += f"\n\nThis information is compiled from {len(sources)} relevant sources."
        return answer

    return "I found some relevant sources but couldn't extract a clear answer. Please try being more specific with your query."


def _generate_simple_answer(query: str, context: str, sources: List[SearchResult]) -> str:
    """Dispatch to one of the intent-specific generators based on the query."""
    intent = classify_query_intent(query)
    if intent == INTENT_HOW_TO:
        return _generate_how_to_answer(query, context, sources)
    if intent == INTENT_EXPLANATION:
        return _generate_explanation_answer(query, context, sources)
    if intent == INTENT_EXAMPLE:
        return _generate_example_answer(query, context, sources)
    return _generate_general_answer(query, context, sources)


def _compute_confidence(sources: List[SearchResult]) -> Tuple[float, float, int]:
    """Compute answer confidence from source relevance and diversity.

    Returns:
        Tuple of ``(confidence, avg_relevance, source_diversity)``.
    """
    avg_relevance = sum(s.final_score for s in sources[:3]) / min(3, len(sources))
    source_diversity = len(set(s.document.content_type for s in sources[:3]))
    confidence = min(avg_relevance * (1 + source_diversity * 0.1), 1.0)
    return confidence, avg_relevance, source_diversity


def generate_answer(
    query: str,
    sources: List[SearchResult],
    config: Dict[str, Any],
    context_trimmer: ContextTrimmer,
    combined_context: str,
    source_info: List[Dict[str, Any]],
    context_metadata: Dict[str, Any],
) -> Tuple[str, float, Dict[str, Any]]:
    """Run the synthesizer over fused context and return the final answer tuple.

    Args:
        query: Original user query.
        sources: Ranked :class:`SearchResult` list.
        config: Agent configuration (used for token budgets).
        context_trimmer: Token estimator used to log final usage.
        combined_context: The fused context block (from :mod:`result_fuser`).
        source_info: Per-source descriptor list (from :mod:`result_fuser`).
        context_metadata: Token/budget metadata (from :mod:`result_fuser`).

    Returns:
        Tuple of ``(answer, confidence, metadata)`` ready to attach to a
        :class:`RAGResponse`.
    """
    if not sources:
        return (
            "I couldn't find relevant information to answer your question. Please try rephrasing your query or being more specific.",
            0.1,
            {
                "source_count": 0,
                "generation_method": "fallback",
            },
        )

    answer = _generate_simple_answer(query, combined_context, sources)
    confidence, avg_relevance, source_diversity = _compute_confidence(sources)
    estimated_context_tokens = context_trimmer.estimate_tokens(combined_context)

    metadata = {
        "source_count": len(sources),
        "sources_used": source_info,
        "context_length": context_metadata.get("context_length", len(combined_context)),
        "context_tokens": estimated_context_tokens,
        "context_token_budget": context_metadata.get("context_token_budget", 0),
        "avg_source_relevance": avg_relevance,
        "source_diversity": source_diversity,
        "generation_method": "context_synthesis",
    }
    return answer, confidence, metadata


class AnswerSynthesizer:
    """Generates the final answer string and confidence score.

    Stateless facade — config and context trimmer are supplied per call.
    Returns the answer, confidence, and metadata tuple expected by
    :class:`AdvancedRagAgent` when assembling the :class:`RAGResponse`.
    """

    @staticmethod
    def synthesize(
        query: str,
        sources: List[SearchResult],
        config: Dict[str, Any],
        context_trimmer: ContextTrimmer,
        combined_context: str,
        source_info: List[Dict[str, Any]],
        context_metadata: Dict[str, Any],
    ) -> Tuple[str, float, Dict[str, Any]]:
        """Generate the final answer, confidence score, and metadata."""
        return generate_answer(
            query=query,
            sources=sources,
            config=config,
            context_trimmer=context_trimmer,
            combined_context=combined_context,
            source_info=source_info,
            context_metadata=context_metadata,
        )


__all__ = [
    "generate_answer",
    "_generate_simple_answer",
    "_generate_how_to_answer",
    "_generate_explanation_answer",
    "_generate_example_answer",
    "_generate_general_answer",
    "_compute_confidence",
    "CHARS_PER_TOKEN",
    "AnswerSynthesizer",
]
