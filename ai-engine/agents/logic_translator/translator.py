"""Logic Translator Agent — core orchestrator for Java to Bedrock translation.

This module is the composition root for :class:`LogicTranslatorAgent`. The
translation logic has been split into focused domain mixins per Issue #1746:

- :mod:`agents.logic_translator.rag_context` — RAG context augmentation
- :mod:`agents.logic_translator.ast_analyzer` — tree-sitter Java AST analysis
- :mod:`agents.logic_translator.code_translator` — Java→JS code translation
- :mod:`agents.logic_translator.block_translator` — Bedrock block JSON generation

This file keeps the class definition, singleton logic, tool wiring, and the
shared type/enum/API mappings, and re-exports the public symbols so existing
imports (``from agents.logic_translator.translator import LogicTranslatorAgent``)
continue to work unchanged.
"""

from typing import List

from agents.java_analyzer import JavaAnalyzerAgent
from agents.logic_translator.ast_analyzer import (
    TREE_SITTER_AVAILABLE,
    ASTAnalyzerMixin,
)
from agents.logic_translator.block_translator import BlockTranslatorMixin
from agents.logic_translator.code_translator import CodeTranslatorMixin
from agents.logic_translator.rag_context import RAGContextMixin
from models.smart_assumptions import (
    SmartAssumptionEngine,
)
from utils.logging_config import get_agent_logger

# Use enhanced agent logger
logger = get_agent_logger("logic_translator")

# LLM Translation temperature for code generation (per research: 0.2 is optimal)
LLM_CODE_TEMPERATURE = 0.2


class LogicTranslatorAgent(
    RAGContextMixin,
    ASTAnalyzerMixin,
    CodeTranslatorMixin,
    BlockTranslatorMixin,
):
    """
    Logic Translator Agent responsible for converting Java logic to Bedrock-compatible
    JavaScript as specified in PRD Feature 2.

    Domain behaviour is provided by the composed mixins:

    - :class:`RAGContextMixin` — retrieval-augmented context
    - :class:`ASTAnalyzerMixin` — Java AST analysis via tree-sitter
    - :class:`CodeTranslatorMixin` — method/class/API/event translation
    - :class:`BlockTranslatorMixin` — Bedrock block/recipe JSON generation
    """

    _instance = None

    def __init__(self):
        self.logger = logger
        self.smart_assumption_engine = SmartAssumptionEngine()
        self.java_analyzer_agent = JavaAnalyzerAgent()

        self._conversion_rag_pipeline = None
        self._rag_context_enabled = False

        # Java to JavaScript conversion mappings
        self.type_mappings = {
            "int": "number",
            "double": "number",
            "float": "number",
            "long": "number",
            "boolean": "boolean",
            "String": "string",
            "void": "void",
            "List": "Array",
            "ArrayList": "Array",
            "HashMap": "Map",
            "Map": "Map",
            # Enhanced Type Mappings (Issue #332)
            "Set": "Set",
            "HashSet": "Set",
            "TreeSet": "Set",
            "LinkedList": "Array",
            "Queue": "Array",
            "Stack": "Array",
            "Deque": "Array",
            "Optional": "null",  # Handle with null checks
            "OptionalInt": "number | null",
            "OptionalDouble": "number | null",
            "OptionalLong": "number | null",
            # Enum handling - convert to string constants
            "Enum": "string",
            # Custom classes become object prototypes
            "Object": "object",
            # Collection primitives
            "Iterator": "Iterator",
            "Iterable": "Iterable",
            # File and I/O types
            "File": "string",  # Path as string
            "InputStream": "Uint8Array",
            "OutputStream": "Uint8Array",
            "Reader": "string",
            "Writer": "string",
        }

        # Enum mappings for common Minecraft enums
        self.enum_mappings = {
            # Block-related enums
            "BlockFace": {
                "DOWN": "Directions.DOWN",
                "UP": "Directions.UP",
                "NORTH": "Directions.NORTH",
                "SOUTH": "Directions.SOUTH",
                "EAST": "Directions.EAST",
                "WEST": "Directions.WEST",
            },
            # Direction enums
            "Direction": {
                "DOWN": "Directions.DOWN",
                "UP": "Directions.UP",
                "NORTH": "Directions.NORTH",
                "SOUTH": "Directions.SOUTH",
                "EAST": "Directions.EAST",
                "WEST": "Directions.WEST",
            },
            # Entity enums
            "EntityType": {
                "ZOMBIE": "minecraft:zombie",
                "SKELETON": "minecraft:skeleton",
                "PLAYER": "minecraft:player",
            },
            # Material enums
            "Material": {
                "AIR": "minecraft:air",
                "STONE": "minecraft:stone",
                "GRASS": "minecraft:grass",
                "DIRT": "minecraft:dirt",
            },
            # Item enums
            "ItemStack": {"EMPTY": "ItemStack.empty()"},
        }

        # Null safety patterns
        self.null_safety_patterns = {
            "null": "null",
            "Optional.empty()": "null",
            "Optional.of(": "/* value */",
            "Optional.ofNullable(": "/* nullable */",
            ".orElse(": " ?? ",  # Null coalescing
            ".orElseGet(": " ?? (",
            ".isPresent()": " !== null",
            ".ifPresent(": "if (",
        }

        # Enhanced API Mappings (Issue #332 - API Mapping Expansion)
        self.api_mappings = {
            # ========== Player API Mappings ==========
            # Health
            "player.getHealth()": 'player.getComponent("minecraft:health").currentValue',
            "player.setHealth()": 'player.getComponent("minecraft:health").setCurrentValue()',
            "player.getMaxHealth()": 'player.getComponent("minecraft:health").effectiveMax',
            "player.isDead()": 'player.getComponent("minecraft:health").currentValue <= 0',
            # Inventory
            "player.getInventory()": "player.container",
            "player.getItemInHand()": "player.getComponent('minecraft:equipped_item').item",
            "player.getSelectedItem()": "player.getComponent('minecraft:equipped_item')",
            ".getItemStack()": ".getItem()",
            # Position
            "player.getLocation()": "player.location",
            "player.getX()": "player.location.x",
            "player.getY()": "player.location.y",
            "player.getZ()": "player.location.z",
            "player.getWorld()": "player.dimension",
            "player.getDirection()": "player.direction",
            # Status
            "player.isSneaking()": "player.isSneaking",
            "player.isSprinting()": "player.isSprinting",
            "player.isFlying()": "player.isFlying",
            "player.isOnGround()": "player.isOnGround",
            "player.getExperienceLevel()": "player.level",
            "player.getFoodLevel()": 'player.getComponent("minecraft:food").foodLevel',
            "player.getSaturation()": 'player.getComponent("minecraft:food").saturation',
            # Permissions
            "player.hasPermission()": "player.hasPermission()",  # Keep as-is for now
            "player.isOp()": "player.isOp()",
            # ========== World API Mappings ==========
            # Blocks
            "world.getBlockAt(": "world.getBlock(",  # x, y, z
            "world.setBlock(": "block.setPermutation(",  # Different approach needed
            "world.getBlockState(": "block.permutation",
            "world.setBlockState(": "block.setPermutation(",
            "world.isAirBlock(": "block.typeId === 'minecraft:air'",
            "world.getTypeId(": "block.typeId",
            "world.getBiome(": "world.getBiome(",
            "world.setBiome(": "world.setBiome(",
            # Time
            "world.getTime()": "world.getTime()",
            "world.setTime(": "world.setTime(",
            "world.getDayTime()": "world.dayTime",
            "world.setDayTime(": "world.dayTime =",
            # Weather
            "world.hasStorm()": "world.isRaining()",
            "world.setStorm(": "world.setRaining(",
            "world.getDifficulty()": "world.difficulty",
            "world.setDifficulty(": "world.difficulty =",
            # Spawning
            "world.spawnEntity(": "world.spawnEntity(",
            "world.spawnParticle(": "world.spawnParticle(",
            # ========== Entity API Mappings ==========
            # Movement
            "entity.getVelocity()": "entity.velocity",
            "entity.setVelocity(": "entity.velocity =",
            "entity.teleport(": "entity.teleport(",
            "entity.getLocation()": "entity.location",
            "entity.setRotation(": "entity.setRotation(",
            "entity.getPitch()": "entity.rotation.x",
            "entity.getYaw()": "entity.rotation.y",
            # Combat
            "entity.damage(": "applyDamage(",  # Custom function needed
            "entity.getHealth()": 'entity.getComponent("minecraft:health").currentValue',
            "entity.setHealth(": 'entity.getComponent("minecraft:health").setCurrentValue(',
            "entity.getMaxHealth()": 'entity.getComponent("minecraft:health").effectiveMax',
            "entity.isDead()": 'entity.getComponent("minecraft:health").currentValue <= 0',
            "entity.remove()": "entity.destroy()",
            "entity.remove(": "entity.destroy()",
            # Properties
            "entity.getType()": "entity.typeId",
            "entity.getName()": "entity.nameTag",
            "entity.setCustomName(": "entity.nameTag =",
            "entity.isSilent()": "entity.isSilent",
            "entity.setSilent(": "entity.isSilent =",
            "entity.hasGravity()": "entity.hasGravity",
            # Inventory
            "entity.getInventory()": "entity.container",
            "entity.getEquipment()": "entity.getComponent('minecraft:equipment')",
            # ========== Item API Mappings ==========
            # ItemStack
            "ItemStack": "ItemStack",
            "new ItemStack(": "new ItemStack(",
            ".getType()": ".typeId",
            ".setType(": ".typeId =",
            ".getAmount()": ".amount",
            ".setAmount(": ".amount =",
            ".getDurability()": ".getComponent('minecraft:damageable').damage",
            ".setDurability(": ".getComponent('minecraft:damageable').damage =",
            ".getItemMeta()": ".getComponent('minecraft:item')",
            ".setItemMeta(": "// Item meta not directly supported",
            ".hasItemMeta()": ".hasComponent('minecraft:item')",
            ".isEmpty()": ".amount === 0",
            # Item usage
            "item.canPickup()": "item.canPlaceOn",  # Approximate
            ".pickup(": "// Pickup not directly supported",
            # ========== Block API Mappings ==========
            # Block state
            "block.getType()": "block.typeId",
            "block.getTypeId()": "block.typeId",
            "block.setType(": "block.setType(",
            "block.getData()": "block.permutation",
            "block.getState(": "block.permutation",
            "block.setState(": "block.setPermutation(",
            "block.getLocation()": "block.location",
            "block.getX()": "block.location.x",
            "block.getY()": "block.location.y",
            "block.getZ()": "block.location.z",
            "block.getWorld()": "block.dimension",
            # Block properties
            "block.isEmpty()": "block.typeId === 'minecraft:air'",
            "block.isSolid()": "// Block solidity check not directly supported",
            "block.getLightLevel()": "block.getLight()",
            # Block physics
            "block.breakNaturally(": "block.destroy()",
            "BlockPosition": "BlockLocation",
            # Material
            "Material": "MinecraftItemType",
            # ========== Common Java to JS Conversions ==========
            "System.out.println": "console.log",
            "System.out.print": "console.log",
            "System.err.println": "console.error",
            "Thread.sleep(": "await new Promise(r => setTimeout(r,",  # Convert ms to ms
            "Math.random()": "Math.random()",
            "Math.abs(": "Math.abs(",
            "Math.max(": "Math.max(",
            "Math.min(": "Math.min(",
            # ========== Event Handler Mappings ==========
            "PlayerInteractEvent": "world.afterEvents.playerInteractWithBlock",
            "BlockBreakEvent": "world.afterEvents.playerBreakBlock",
            "BlockPlaceEvent": "world.afterEvents.blockPlace",
            "EntitySpawnEvent": "world.afterEvents.entitySpawn",
            "EntityDeathEvent": "world.afterEvents.entityDie",
            "PlayerJoinEvent": "world.afterEvents.playerJoin",
            "PlayerLeaveEvent": "world.afterEvents.playerLeave",
            "PlayerChatEvent": "world.afterEvents.chatSend",
            "PlayerCommandPreprocessEvent": "world.afterEvents.commandExecute",
            "EntityDamageEvent": "world.afterEvents.entityHit",
            "ItemUseEvent": "world.afterEvents.itemUse",
            "ItemUseOnEvent": "world.afterEvents.itemUseOn",
        }

        # Tools initialization
        self.tools = self.get_tools()

    @classmethod
    def get_instance(cls):
        """Get singleton instance of LogicTranslatorAgent"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tools(self) -> List:
        """Get tools available to this agent."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return [
            LogicTranslatorTools.translate_java_method_tool,
            LogicTranslatorTools.convert_java_class_tool,
            LogicTranslatorTools.map_java_apis_tool,
            LogicTranslatorTools.generate_event_handlers_tool,
            LogicTranslatorTools.validate_javascript_syntax_tool,
            LogicTranslatorTools.translate_crafting_recipe_tool,
            LogicTranslatorTools.generate_bedrock_block_tool,
            LogicTranslatorTools.validate_block_json_tool,
            LogicTranslatorTools.map_block_properties_tool,
            LogicTranslatorTools.get_rag_context_tool,
            LogicTranslatorTools.set_rag_context_tool,
        ]

    @property
    def translate_java_method_tool(self):
        """Tool-wrapped translate_java_method - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.translate_java_method_tool

    @property
    def convert_java_class_tool(self):
        """Tool-wrapped convert_java_class - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.convert_java_class_tool

    @property
    def map_java_apis_tool(self):
        """Tool-wrapped map_java_apis - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.map_java_apis_tool

    @property
    def generate_event_handlers_tool(self):
        """Tool-wrapped generate_event_handlers - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.generate_event_handlers_tool

    @property
    def validate_javascript_syntax_tool(self):
        """Tool-wrapped validate_javascript_syntax - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.validate_javascript_syntax_tool

    @property
    def translate_crafting_recipe_tool(self):
        """Tool-wrapped translate_crafting_recipe - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.translate_crafting_recipe_tool

    @property
    def generate_bedrock_block_tool(self):
        """Tool-wrapped generate_bedrock_block - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.generate_bedrock_block_tool

    @property
    def validate_block_json_tool(self):
        """Tool-wrapped validate_block_json - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.validate_block_json_tool

    @property
    def map_block_properties_tool(self):
        """Tool-wrapped map_block_properties - backwards compatible."""
        from agents.logic_translator.tools import LogicTranslatorTools

        return LogicTranslatorTools.map_block_properties_tool


__all__ = [
    "LogicTranslatorAgent",
    "LLM_CODE_TEMPERATURE",
    "TREE_SITTER_AVAILABLE",
    "ASTAnalyzerMixin",
    "CodeTranslatorMixin",
    "BlockTranslatorMixin",
    "RAGContextMixin",
]
