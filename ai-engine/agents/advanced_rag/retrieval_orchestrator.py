"""retrieval_orchestrator — Multi-source retrieval coordination.

Seam: Extracted from AdvancedRagAgent._retrieve_documents / _get_available_documents
/ _get_document_embeddings. Owns the embedding → document fetch → hybrid search
pipeline. Stateless orchestrator that takes the agent's cached state and shared
sub-components as parameters, so it can be tested in isolation.

Issue #1709 — Subpackage split for advanced_rag_agent.py (32K).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from schemas.multimodal_schema import (
    ContentType,
    MultiModalDocument,
    SearchQuery,
    SearchResult,
)
from search.hybrid_search_engine import (
    HybridSearchEngine,
    RankingStrategy,
    SearchMode,
)
from utils.multimodal_embedding_generator import (
    EmbeddingStrategy,
    MultiModalEmbeddingGenerator,
)

logger = logging.getLogger(__name__)


def _build_mock_documents() -> Dict[str, MultiModalDocument]:
    """Build the placeholder documentation set used in the demo flow.

    Returns:
        Mapping of document id → :class:`MultiModalDocument` for the bundled
        Java blocks, Bedrock blocks, and recipe documentation examples.
    """
    return {
        "java_blocks": MultiModalDocument(
            id="java_blocks",
            content_hash="mock_hash_1",
            source_path="docs/java/blocks.md",
            content_type=ContentType.DOCUMENTATION,
            content_text="""
            # Java Blocks in Minecraft Modding

            Blocks are the fundamental building components of Minecraft worlds.
            In Java Edition modding, blocks are defined as classes that extend
            the Block base class.

            ## Creating a Basic Block

            To create a basic block, you need to:
            1. Create a class that extends Block
            2. Define the block properties (material, hardness, etc.)
            3. Register the block with the game registry

            Example:
            ```java
            public class CopperBlock extends Block {
                public CopperBlock() {
                    super(Block.Properties.of(Material.METAL)
                        .strength(3.0F, 6.0F)
                        .sound(SoundType.METAL));
                }
            }
            ```
            """,
            tags=["java", "blocks", "modding", "tutorial"],
            project_context="minecraft_mod",
        ),
        "bedrock_blocks": MultiModalDocument(
            id="bedrock_blocks",
            content_hash="mock_hash_2",
            source_path="docs/bedrock/blocks.md",
            content_type=ContentType.DOCUMENTATION,
            content_text="""
            # Bedrock Blocks Documentation

            In Minecraft Bedrock Edition, blocks are defined using JSON
            files in behavior and resource packs.

            ## Block Behavior Definition

            Blocks in Bedrock are defined with behavior files that specify:
            - Block properties
            - Component behaviors
            - Event responses

            Example behavior file:
            ```json
            {
                "format_version": "1.20.10",
                "minecraft:block": {
                    "description": {
                        "identifier": "custom:copper_block"
                    },
                    "components": {
                        "minecraft:material_instances": {
                            "*": {
                                "texture": "copper_block",
                                "render_method": "opaque"
                            }
                        },
                        "minecraft:destroy_time": 3.0,
                        "minecraft:explosion_resistance": 6.0
                    }
                }
            }
            ```
            """,
            tags=["bedrock", "blocks", "json", "behavior"],
            project_context="minecraft_mod",
        ),
        "recipe_system": MultiModalDocument(
            id="recipe_system",
            content_hash="mock_hash_3",
            source_path="docs/recipes/crafting.md",
            content_type=ContentType.DOCUMENTATION,
            content_text="""
            # Recipe System in Minecraft

            Recipes define how players can craft items and blocks.
            Both Java and Bedrock editions support recipe systems.

            ## Java Recipe Format

            Java recipes are defined in JSON format:
            ```json
            {
                "type": "minecraft:crafting_shaped",
                "pattern": [
                    "CCC",
                    "CCC",
                    "CCC"
                ],
                "key": {
                    "C": {
                        "item": "minecraft:copper_ingot"
                    }
                },
                "result": {
                    "item": "minecraft:copper_block"
                }
            }
            ```

            ## Bedrock Recipe Format

            Bedrock uses a similar but slightly different format.
            """,
            tags=["recipes", "crafting", "java", "bedrock"],
            project_context="minecraft_mod",
        ),
    }


def _filter_documents(
    documents: Dict[str, MultiModalDocument],
    query: SearchQuery,
) -> Dict[str, MultiModalDocument]:
    """Filter documents according to the search query's constraints.

    Args:
        documents: Candidate documents keyed by id.
        query: :class:`SearchQuery` carrying the content-type, project, and
            tag filters.

    Returns:
        A new mapping containing only documents that match the filters.
    """
    filtered: Dict[str, MultiModalDocument] = {}
    for doc_id, document in documents.items():
        if query.content_types and document.content_type not in query.content_types:
            continue
        if query.project_context and document.project_context != query.project_context:
            continue
        if query.tags and not any(tag in document.tags for tag in query.tags):
            continue
        filtered[doc_id] = document
    return filtered


def get_available_documents(
    query: SearchQuery,
    document_cache: Dict[str, MultiModalDocument],
) -> Dict[str, MultiModalDocument]:
    """Return documents that match the query filters.

    Lazily seeds ``document_cache`` with the bundled mock set the first time
    it is empty so the demo flow has data to work with.

    Args:
        query: The active :class:`SearchQuery`.
        document_cache: Mutable cache held by the agent.

    Returns:
        Filtered documents keyed by id.
    """
    if not document_cache:
        document_cache.update(_build_mock_documents())
    return _filter_documents(document_cache, query)


async def get_document_embeddings(
    documents: Dict[str, MultiModalDocument],
    embedding_generator: MultiModalEmbeddingGenerator,
    embedding_cache: Dict[str, List[Any]],
) -> Dict[str, List[Any]]:
    """Generate and cache embeddings for ``documents``.

    Args:
        documents: Documents to embed.
        embedding_generator: The :class:`MultiModalEmbeddingGenerator` to use.
        embedding_cache: Mutable cache held by the agent.

    Returns:
        A mapping of document id → list of embedding results (one per chunk).
    """
    embeddings: Dict[str, List[Any]] = {}
    for doc_id, document in documents.items():
        if doc_id in embedding_cache:
            embeddings[doc_id] = embedding_cache[doc_id]
            continue
        if document.content_text:
            embedding_result = await embedding_generator.generate_embedding(
                document.content_text, EmbeddingStrategy.HYBRID
            )
            if embedding_result:
                embedding_cache[doc_id] = [embedding_result]
                embeddings[doc_id] = [embedding_result]
    return embeddings


async def retrieve_documents(
    query: SearchQuery,
    embedding_generator: MultiModalEmbeddingGenerator,
    hybrid_search: HybridSearchEngine,
    document_cache: Dict[str, MultiModalDocument],
    embedding_cache: Dict[str, List[Any]],
) -> List[SearchResult]:
    """End-to-end retrieval: embed → fetch documents → hybrid search.

    Args:
        query: The active :class:`SearchQuery`.
        embedding_generator: Embedding generator for the query and documents.
        hybrid_search: :class:`HybridSearchEngine` to perform the actual rank.
        document_cache: Mutable document cache held by the agent.
        embedding_cache: Mutable embedding cache held by the agent.

    Returns:
        Ranked list of :class:`SearchResult` instances. Empty on error.
    """
    try:
        query_embedding_result = await embedding_generator.generate_embedding(
            query.query_text, EmbeddingStrategy.HYBRID
        )
        if not query_embedding_result:
            logger.warning("Failed to generate query embedding, using keyword-only search")
            query_embedding = []
        else:
            query_embedding = query_embedding_result.embedding.tolist()

        documents = get_available_documents(query, document_cache)
        embeddings = await get_document_embeddings(documents, embedding_generator, embedding_cache)

        search_results = await hybrid_search.search(
            query=query,
            documents=documents,
            embeddings=embeddings,
            query_embedding=query_embedding,
            search_mode=SearchMode.HYBRID,
            ranking_strategy=RankingStrategy.WEIGHTED_SUM,
        )

        logger.info(f"Retrieved {len(search_results)} documents from hybrid search")
        return search_results

    except Exception as e:
        logger.error(f"Error in document retrieval: {e}")
        return []


class RetrievalOrchestrator:
    """Coordinates the multi-stage retrieval pipeline.

    Stateless facade — caches are passed in so the agent owns the canonical
    state. This keeps the orchestrator free of agent imports and side effects.
    """

    @staticmethod
    async def retrieve(
        query: SearchQuery,
        embedding_generator: MultiModalEmbeddingGenerator,
        hybrid_search: HybridSearchEngine,
        document_cache: Dict[str, MultiModalDocument],
        embedding_cache: Dict[str, List[Any]],
    ) -> List[SearchResult]:
        """Run the retrieval pipeline and return ranked :class:`SearchResult`s."""
        return await retrieve_documents(
            query=query,
            embedding_generator=embedding_generator,
            hybrid_search=hybrid_search,
            document_cache=document_cache,
            embedding_cache=embedding_cache,
        )

    @staticmethod
    def get_available(
        query: SearchQuery,
        document_cache: Dict[str, MultiModalDocument],
    ) -> Dict[str, MultiModalDocument]:
        """Return filtered documents (seeds the cache if empty)."""
        return get_available_documents(query, document_cache)

    @staticmethod
    async def embed(
        documents: Dict[str, MultiModalDocument],
        embedding_generator: MultiModalEmbeddingGenerator,
        embedding_cache: Dict[str, List[Any]],
    ) -> Dict[str, List[Any]]:
        """Return embeddings for ``documents`` using the agent's cache."""
        return await get_document_embeddings(documents, embedding_generator, embedding_cache)


__all__ = [
    "retrieve_documents",
    "get_available_documents",
    "get_document_embeddings",
    "RetrievalOrchestrator",
]
