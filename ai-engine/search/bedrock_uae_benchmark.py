"""
UAE Benchmark Dataset for Bedrock API Documentation RAG.

This module provides evaluation datasets for benchmarking the UAE (Utility-Aligned Embeddings)
retriever against the baseline similarity-based retriever.

Based on: "Aligning Dense Retrievers with LLM Utility via Distillation"
(Sandhu et al., https://arxiv.org/abs/2604.22722v1)

The core problem: cosine similarity retrieves Bedrock API docs that LOOK similar
to a Java query but aren't the ones that produce valid Bedrock code.

Example:
- Java query: "register entity with custom AI goal"
- Similarity-based retrieval: returns general Bedrock entity docs (high word overlap)
- What LLM actually needs: the specific Bedrock behavior pack component for custom AI goals
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BedrockDoc:
    """A Bedrock API documentation document."""

    doc_id: str
    title: str
    content: str
    component_type: str
    api_class: str
    minecraft_version: str
    tags: List[str]


@dataclass
class EvaluationQuery:
    """A query for evaluation with ground truth useful documents."""

    query_id: str
    java_query: str
    description: str
    useful_doc_ids: List[str]
    hallucination_risk: bool
    expected_components: List[str]


@dataclass
class ConversionHistoryEntry:
    """A historical conversion entry with utility labels."""

    job_id: str
    java_query: str
    retrieved_doc_ids: List[str]
    output: str
    successful: bool
    hallucinated_components: List[str]
    used_doc_ids: List[str]


class BedrockUAEBenchmarkDataset:
    """
    Dataset for benchmarking UAE retriever vs baseline on Bedrock API documentation.

    This dataset contains:
    1. Core Bedrock API documents (30 docs covering essential components)
    2. Evaluation queries with ground truth useful documents
    3. Simulated conversion history for training
    """

    CORE_BEDROCK_DOCS = [
        BedrockDoc(
            doc_id="bedrock_entity_001",
            title="Entity Registration",
            content="""Entity Registration using Minecraft.Edible
Registration: server EntityComponent.register('minecraft:behavior.nearest_attackable')
Component: 'minecraft:behavior.nearest_attackable'
Provides AI goal for finding nearest attackable entity.
""",
            component_type="entity",
            api_class="EntityComponent",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "goal", "attackable"],
        ),
        BedrockDoc(
            doc_id="bedrock_entity_002",
            title="Custom AI Goal",
            content="""Custom AI Goal Component Registration
Using Minecraft BE's behavior pack system:
server.EntityComponent.register('minecraft:behavior.custom_goal')
For custom AI behavior not covered by built-in goals.
""",
            component_type="entity",
            api_class="EntityComponent",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "custom", "goal"],
        ),
        BedrockDoc(
            doc_id="bedrock_entity_003",
            title="Entity Move To Goal",
            content="""EntityAI Goal: Move To Position
server.EntityComponent.register('minecraft:behavior.move_to_goal')
Used for pathfinding to specific coordinates.
""",
            component_type="entity",
            api_class="EntityComponent",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "movement", "pathfinding"],
        ),
        BedrockDoc(
            doc_id="bedrock_block_001",
            title="Block Component Registration",
            content="""Block Component Registration
server.block.registerComponent('minecraft:geometry', {
  'minecraft:light_emission': 15,
  'minecraft:light_filter': 0
})
""",
            component_type="block",
            api_class="BlockComponent",
            minecraft_version="1.20.0",
            tags=["block", "component", "registration", "geometry", "light"],
        ),
        BedrockDoc(
            doc_id="bedrock_block_002",
            title="Block State Component",
            content="""Block State Component
server.block.registerComponent('minecraft:block_state', {
  'minecraft:geometry': 'geometry.myblock'
})
""",
            component_type="block",
            api_class="BlockComponent",
            minecraft_version="1.20.0",
            tags=["block", "state", "component"],
        ),
        BedrockDoc(
            doc_id="bedrock_item_001",
            title="Item Component Registration",
            content="""Item Component Registration
server.item.registerComponent('myitem', {
  'minecraft:icon': { 'texture' : 'myitem' },
  'minecraft:render_offsets': 'diamond_sword'
})
""",
            component_type="item",
            api_class="ItemComponent",
            minecraft_version="1.20.0",
            tags=["item", "component", "registration", "icon", "render"],
        ),
        BedrockDoc(
            doc_id="bedrock_item_002",
            title="Item Use Animation",
            content="""Item Use Animation Component
server.item.registerComponent('myitem', {
  'minecraft:use_animation': 'eat',
  'minecraft:use_duration': 1.0
})
""",
            component_type="item",
            api_class="ItemComponent",
            minecraft_version="1.20.0",
            tags=["item", "animation", "use"],
        ),
        BedrockDoc(
            doc_id="bedrock_events_001",
            title="Entity Event Handler",
            content="""Entity Event Handler Registration
entity.initialize({
  'minecraft:entity_definition_event': {
    'events': {
      'my_custom_event': {
        'add': { 'component_groups': ['group1'] }
      }
    }
  }
})
""",
            component_type="entity",
            api_class="EntityEventHandler",
            minecraft_version="1.20.0",
            tags=["entity", "event", "handler", "definition"],
        ),
        BedrockDoc(
            doc_id="bedrock_events_002",
            title="Event Response Component",
            content="""Event Response in Behavior Pack
Using 'add' and 'remove' component groups:
'event_response': [
  { 'event': 'my_event', 'add': { 'component_groups': ['g1'] } }
]
""",
            component_type="entity",
            api_class="EventResponse",
            minecraft_version="1.20.0",
            tags=["entity", "event", "response", "component_groups"],
        ),
        BedrockDoc(
            doc_id="bedrock_ai_001",
            title="Behavior Goals",
            content="""Behavior Goal System
Goals control entity AI behavior:
'behavior': {
  'minecraft:behavior.nearest_attackable': {
    'priority': 2,
    'must_see': true
  }
}
""",
            component_type="entity",
            api_class="BehaviorGoal",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "goal", "attackable"],
        ),
        BedrockDoc(
            doc_id="bedrock_ai_002",
            title="Look At Player Behavior",
            content="""Look At Player Behavior
'behavior': {
  'minecraft:behavior.look_at_player': {
    'priority': 8,
    'look_distance': 8.0
  }
}
""",
            component_type="entity",
            api_class="BehaviorLookAt",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "look", "player"],
        ),
        BedrockDoc(
            doc_id="bedrock_ai_003",
            title="Wander Behavior",
            content="""Wander Behavior Component
'behavior': {
  'minecraft:behavior.wander': {
    'priority': 7,
    'speed': 1.0,
    'landmark_dist': 5
  }
}
""",
            component_type="entity",
            api_class="BehaviorWander",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "wander", "movement"],
        ),
        BedrockDoc(
            doc_id="bedrock_ai_004",
            title="Floating Behavior",
            content="""Floating Behavior for entities
'behavior': {
  'minecraft:behavior.float': {
    'priority': 0,
    'jump_chance': 0.0
  }
}
""",
            component_type="entity",
            api_class="BehaviorFloat",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "float"],
        ),
        BedrockDoc(
            doc_id="bedrock_ai_005",
            title="Custom Behavior Implementation",
            content="""Custom Behavior Implementation
Using server.EntityComponent.register() for custom behaviors:
EntityComponent.register('custom_ai_behavior', { ... })
""",
            component_type="entity",
            api_class="EntityComponent",
            minecraft_version="1.20.0",
            tags=["entity", "ai", "behavior", "custom", "register"],
        ),
        BedrockDoc(
            doc_id="bedrock_loot_001",
            title="Loot Table Reference",
            content="""Loot Table in Component
'minecraft:loot': {
  'table': 'loot_tables/blocks/dirt.json'
}
""",
            component_type="block",
            api_class="LootComponent",
            minecraft_version="1.20.0",
            tags=["block", "loot", "table"],
        ),
        BedrockDoc(
            doc_id="bedrock_loot_002",
            title="Entity Loot Table",
            content="""Entity Death Loot Table
'minecraft:loot': {
  'table': 'loot_tables/entities/zombie.json'
}
""",
            component_type="entity",
            api_class="LootComponent",
            minecraft_version="1.20.0",
            tags=["entity", "loot", "table", "death"],
        ),
        BedrockDoc(
            doc_id="bedrock_equipment_001",
            title="Equipment Component",
            content="""Equipment Component for Entities
'minecraft:equipment': {
  'table': 'equipment/myzombie.json',
  'slot_drop_chance': [
    { 'slot': 0, 'drop_chance': 0.1 }
  ]
}
""",
            component_type="entity",
            api_class="EquipmentComponent",
            minecraft_version="1.20.0",
            tags=["entity", "equipment", "loot", "slot"],
        ),
        BedrockDoc(
            doc_id="bedrock_equipment_002",
            title="Hand Equipment",
            content="""Hand Equipment Component
'minecraft:equipment': {
  'table': 'equipment/hand.json'
}
""",
            component_type="entity",
            api_class="EquipmentComponent",
            minecraft_version="1.20.0",
            tags=["entity", "equipment", "hand"],
        ),
        BedrockDoc(
            doc_id="bedrock_spawn_001",
            title="Spawn Rules Component",
            content="""Spawn Rules Component
'minecraft:spawn_rules': {
  'spawn_algorithm': 'water',
  'spawns_above_block': 'water'
}
""",
            component_type="entity",
            api_class="SpawnRulesComponent",
            minecraft_version="1.20.0",
            tags=["entity", "spawn", "rules"],
        ),
        BedrockDoc(
            doc_id="bedrock_health_001",
            title="Health Component",
            content="""Health Component
'minecraft:health': {
  'value': 20,
  'max': 20,
  'min': 0
}
""",
            component_type="entity",
            api_class="HealthComponent",
            minecraft_version="1.20.0",
            tags=["entity", "health", "attribute"],
        ),
        BedrockDoc(
            doc_id="bedrock_movement_001",
            title="Movement Component",
            content="""Movement Speed Modifier
'minecraft:movement': {
  'value': 0.25
}
""",
            component_type="entity",
            api_class="MovementComponent",
            minecraft_version="1.20.0",
            tags=["entity", "movement", "speed", "attribute"],
        ),
        BedrockDoc(
            doc_id="bedrock_movement_002",
            title="Flying Speed Component",
            content="""Flying Speed Modifier
'minecraft:movement.flying': {
  'value': 0.5
}
""",
            component_type="entity",
            api_class="FlyingSpeedComponent",
            minecraft_version="1.20.0",
            tags=["entity", "movement", "flying", "speed"],
        ),
        BedrockDoc(
            doc_id="bedrock_burn_001",
            title="Burnable Component",
            content="""Burnable Component for blocks/entities
'minecraft:burnable': {
  'burn_time': 100,
  'destroy_chance': 1.0
}
""",
            component_type="block",
            api_class="BurnableComponent",
            minecraft_version="1.20.0",
            tags=["block", "burn", "fire"],
        ),
        BedrockDoc(
            doc_id="bedrock_geometry_001",
            title="Geometry Component",
            content="""Geometry Component for entities/blocks
'minecraft:geometry': {
  'value': 'geometry.myentity'
}
""",
            component_type="entity",
            api_class="GeometryComponent",
            minecraft_version="1.20.0",
            tags=["entity", "geometry", "model"],
        ),
        BedrockDoc(
            doc_id="bedrock_material_001",
            title="Material Instance",
            content="""Material Instance in Render Component
'minecraft:render': {
  'materials': [
    { 'resource': 'material.stone', 'texture_source': 'stone' }
  ]
}
""",
            component_type="block",
            api_class="MaterialComponent",
            minecraft_version="1.20.0",
            tags=["block", "material", "render", "texture"],
        ),
        BedrockDoc(
            doc_id="bedrock_identifier_001",
            title="Entity Identifier",
            content="""Entity Identifier Component
Format: 'namespace:name'
Description: Unique identifier for the entity type
""",
            component_type="entity",
            api_class="IdentifierComponent",
            minecraft_version="1.20.0",
            tags=["entity", "identifier", "namespace"],
        ),
        BedrockDoc(
            doc_id="bedrock_family_001",
            title="Entity Family Component",
            content="""Entity Family Component
'minecraft:family': {
  'groups': ['undead', 'zombie']
}
""",
            component_type="entity",
            api_class="FamilyComponent",
            minecraft_version="1.20.0",
            tags=["entity", "family", "type", "group"],
        ),
        BedrockDoc(
            doc_id="bedrock_collision_001",
            title="Collision Box Component",
            content="""Collision Box Component
'minecraft:collision_box': {
  'width': 1.0,
  'height': 2.0
}
""",
            component_type="entity",
            api_class="CollisionComponent",
            minecraft_version="1.20.0",
            tags=["entity", "collision", "box", "physics"],
        ),
        BedrockDoc(
            doc_id="bedrock_navigation_001",
            title="Navigation Component",
            content="""Navigation Component for pathfinding
'minecraft:navigation.generic': {
  'can_walk': true,
  'can_swim': false,
  'can_jump': true
}
""",
            component_type="entity",
            api_class="NavigationComponent",
            minecraft_version="1.20.0",
            tags=["entity", "navigation", "pathfinding", "walk", "swim"],
        ),
    ]

    EVALUATION_QUERIES = [
        EvaluationQuery(
            query_id="eval_001",
            java_query="register entity with custom AI goal",
            description="Java entity registration with custom AI goal",
            useful_doc_ids=["bedrock_entity_002", "bedrock_ai_001", "bedrock_events_001"],
            hallucination_risk=True,
            expected_components=["EntityComponent.register", "minecraft:behavior.custom_goal"],
        ),
        EvaluationQuery(
            query_id="eval_002",
            java_query="nearest attackable entity AI behavior",
            description="AI behavior for finding nearest attackable entity",
            useful_doc_ids=["bedrock_ai_001", "bedrock_entity_001"],
            hallucination_risk=True,
            expected_components=["minecraft:behavior.nearest_attackable"],
        ),
        EvaluationQuery(
            query_id="eval_003",
            java_query="entity wander behavior",
            description="Wandering behavior for entity",
            useful_doc_ids=["bedrock_ai_003", "bedrock_ai_004"],
            hallucination_risk=False,
            expected_components=["minecraft:behavior.wander", "minecraft:behavior.float"],
        ),
        EvaluationQuery(
            query_id="eval_004",
            java_query="block geometry registration",
            description="Block geometry registration in Bedrock",
            useful_doc_ids=["bedrock_block_001", "bedrock_geometry_001"],
            hallucination_risk=True,
            expected_components=["minecraft:geometry", "server.block.registerComponent"],
        ),
        EvaluationQuery(
            query_id="eval_005",
            java_query="item component registration",
            description="Item component registration",
            useful_doc_ids=["bedrock_item_001", "bedrock_item_002"],
            hallucination_risk=True,
            expected_components=["server.item.registerComponent", "minecraft:use_animation"],
        ),
        EvaluationQuery(
            query_id="eval_006",
            java_query="entity look at player behavior",
            description="Entity looking at player",
            useful_doc_ids=["bedrock_ai_002", "bedrock_ai_001"],
            hallucination_risk=False,
            expected_components=["minecraft:behavior.look_at_player"],
        ),
        EvaluationQuery(
            query_id="eval_007",
            java_query="health component for entity",
            description="Health attribute for entity",
            useful_doc_ids=["bedrock_health_001"],
            hallucination_risk=False,
            expected_components=["minecraft:health"],
        ),
        EvaluationQuery(
            query_id="eval_008",
            java_query="loot table for entity death",
            description="Loot table on entity death",
            useful_doc_ids=["bedrock_loot_002", "bedrock_equipment_001"],
            hallucination_risk=True,
            expected_components=["minecraft:loot", "table"],
        ),
        EvaluationQuery(
            query_id="eval_009",
            java_query="spawn rules for entity",
            description="Entity spawn rules",
            useful_doc_ids=["bedrock_spawn_001"],
            hallucination_risk=True,
            expected_components=["minecraft:spawn_rules"],
        ),
        EvaluationQuery(
            query_id="eval_010",
            java_query="navigation for entity pathfinding",
            description="Entity navigation and pathfinding",
            useful_doc_ids=["bedrock_navigation_001", "bedrock_movement_001"],
            hallucination_risk=True,
            expected_components=["minecraft:navigation.generic", "can_walk"],
        ),
    ]

    SIMULATED_CONVERSION_HISTORY = [
        ConversionHistoryEntry(
            job_id="job_001",
            java_query="register custom AI goal for entity",
            retrieved_doc_ids=[
                "bedrock_entity_001",
                "bedrock_entity_002",
                "bedrock_ai_001",
                "bedrock_block_001",
                "bedrock_events_001",
            ],
            output="Used EntityComponent.register('minecraft:behavior.custom_goal') and event handlers",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_entity_002", "bedrock_events_001"],
        ),
        ConversionHistoryEntry(
            job_id="job_002",
            java_query="entity nearest attackable",
            retrieved_doc_ids=[
                "bedrock_entity_001",
                "bedrock_ai_001",
                "bedrock_block_001",
                "bedrock_ai_002",
            ],
            output="Applied behavior.nearest_attackable with priority 2",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_ai_001", "bedrock_entity_001"],
        ),
        ConversionHistoryEntry(
            job_id="job_003",
            java_query="entity wander behavior",
            retrieved_doc_ids=[
                "bedrock_ai_003",
                "bedrock_ai_004",
                "bedrock_ai_001",
                "bedrock_block_001",
            ],
            output="Added wander and float behaviors",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_ai_003", "bedrock_ai_004"],
        ),
        ConversionHistoryEntry(
            job_id="job_004",
            java_query="block geometry",
            retrieved_doc_ids=[
                "bedrock_block_001",
                "bedrock_geometry_001",
                "bedrock_block_002",
                "bedrock_material_001",
            ],
            output="Registered geometry component with block",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_block_001", "bedrock_geometry_001"],
        ),
        ConversionHistoryEntry(
            job_id="job_005",
            java_query="item use animation",
            retrieved_doc_ids=["bedrock_item_001", "bedrock_item_002", "bedrock_block_001"],
            output="Applied eat animation to item",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_item_002"],
        ),
        ConversionHistoryEntry(
            job_id="job_006",
            java_query="custom entity AI",
            retrieved_doc_ids=[
                "bedrock_entity_001",
                "bedrock_entity_002",
                "bedrock_ai_005",
                "bedrock_events_001",
            ],
            output="Created custom AI behavior using EntityComponent.register",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_entity_002", "bedrock_ai_005"],
        ),
        ConversionHistoryEntry(
            job_id="job_007",
            java_query="entity health",
            retrieved_doc_ids=["bedrock_health_001", "bedrock_movement_001", "bedrock_entity_001"],
            output="Added health component",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_health_001"],
        ),
        ConversionHistoryEntry(
            job_id="job_008",
            java_query="entity loot on death",
            retrieved_doc_ids=[
                "bedrock_loot_001",
                "bedrock_loot_002",
                "bedrock_equipment_001",
                "bedrock_equipment_002",
            ],
            output="Applied loot table to entity",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_loot_002"],
        ),
        ConversionHistoryEntry(
            job_id="job_009",
            java_query="entity spawn rules",
            retrieved_doc_ids=["bedrock_spawn_001", "bedrock_entity_001", "bedrock_block_001"],
            output="Set spawn rules for water",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_spawn_001"],
        ),
        ConversionHistoryEntry(
            job_id="job_010",
            java_query="entity navigation pathfinding",
            retrieved_doc_ids=["bedrock_navigation_001", "bedrock_movement_001", "bedrock_ai_001"],
            output="Configured generic navigation with walk and swim",
            successful=True,
            hallucinated_components=[],
            used_doc_ids=["bedrock_navigation_001"],
        ),
    ]

    def __init__(self):
        self.documents = {doc.doc_id: doc for doc in self.CORE_BEDROCK_DOCS}
        self.queries = {q.query_id: q for q in self.EVALUATION_QUERIES}
        self.conversion_history = self.SIMULATED_CONVERSION_HISTORY

    def get_document(self, doc_id: str) -> Optional[BedrockDoc]:
        """Get a document by ID."""
        return self.documents.get(doc_id)

    def get_all_documents(self) -> List[BedrockDoc]:
        """Get all documents."""
        return list(self.documents.values())

    def get_evaluation_queries(self) -> List[EvaluationQuery]:
        """Get all evaluation queries."""
        return list(self.queries.values())

    def get_conversion_history(self) -> List[ConversionHistoryEntry]:
        """Get simulated conversion history."""
        return self.conversion_history

    def get_documents_by_type(self, component_type: str) -> List[BedrockDoc]:
        """Get documents filtered by component type."""
        return [doc for doc in self.documents.values() if doc.component_type == component_type]

    def get_retrieved_docs_for_query(self, query: str) -> Dict[str, float]:
        """Get mock retrieval scores for a query based on keyword overlap."""
        scores = {}
        query_terms = set(query.lower().split())

        for doc_id, doc in self.documents.items():
            doc_terms = set(doc.content.lower().split()) | set(doc.title.lower().split())
            overlap = len(query_terms & doc_terms)
            if overlap > 0:
                scores[doc_id] = overlap / len(query_terms)

        return scores

    def export_to_json(self, path: str) -> None:
        """Export dataset to JSON file."""
        data = {
            "documents": [{**asdict(doc), "_type": "BedrockDoc"} for doc in self.CORE_BEDROCK_DOCS],
            "evaluation_queries": [
                {**asdict(q), "_type": "EvaluationQuery"} for q in self.EVALUATION_QUERIES
            ],
            "conversion_history": [
                {**asdict(h), "_type": "ConversionHistoryEntry"}
                for h in self.SIMULATED_CONVERSION_HISTORY
            ],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported dataset to {path}")


def create_bedrock_uae_dataset() -> BedrockUAEBenchmarkDataset:
    """Factory function to create the Bedrock UAE benchmark dataset."""
    return BedrockUAEBenchmarkDataset()
