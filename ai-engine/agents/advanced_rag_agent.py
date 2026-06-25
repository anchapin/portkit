"""advanced_rag_agent - Backward compatibility stub.

This file provides backward compatibility for code that imports from
``agents.advanced_rag_agent`` (the old single-file module).

The actual implementation has been split into the ``advanced_rag/``
subpackage at ``agents/advanced_rag/``.

Issue #1709 — Stub file for backward compatibility.

For new code, import from submodules directly:
- ``from agents.advanced_rag.query_router import ...``
- ``from agents.advanced_rag.retrieval_orchestrator import ...``
- ``from agents.advanced_rag.result_fuser import ...``
- ``from agents.advanced_rag.strategy_selector import ...``
- ``from agents.advanced_rag.answer_synthesizer import ...``

For backward compatibility, continue importing from:
``from agents.advanced_rag_agent import AdvancedRAGAgent, RAGResponse``
"""

from __future__ import annotations

# Re-export the public API from the subpackage. The subpackage exposes both
# ``AdvancedRagAgent`` (PEP-8 spelling) and ``AdvancedRAGAgent`` (the
# original spelling) — both refer to the same class object.
from agents.advanced_rag import (
    AdvancedRAGAgent,
    AdvancedRagAgent,
    RAGResponse,
)

__all__ = [
    "AdvancedRAGAgent",
    "AdvancedRagAgent",
    "RAGResponse",
]
