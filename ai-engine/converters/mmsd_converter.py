"""
MMSD Converter - Integrates trained GRPO models into the PortKit conversion pipeline.

This module provides:
- MMSDConverter: Main converter class supporting both Ollama local inference and API fallback
- MMSDConversionResult: Structured result with Bedrock code, confidence, and variants
- A/B testing framework for model vs API comparison

Usage:
    # Basic usage with Ollama local inference
    converter = MMSDConverter()
    result = converter.convert(java_code)

    # Force API fallback
    converter = MMSDConverter(engine="api")
    result = converter.convert(java_code)

    # A/B testing mode
    converter = MMSDConverter(engine="ab")
    result = converter.convert(java_code)
    # result.ab_result contains both model and API results for comparison

Latency target: <5s for conversion (Ollama), with API fallback on failure.
"""

import os
import re
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class EngineMode(Enum):
    """Engine mode for MMSD conversion."""

    OLLAMA = "ollama"  # Use Ollama local inference
    API = "api"  # Use premium API fallback
    AB = "ab"  # A/B testing: run both and compare


@dataclass
class MMSDConversionVariant:
    """A variant of the conversion result."""

    bedrock_manifest: str
    bedrock_script: str
    reasoning: str
    confidence: float  # 0.0 to 1.0
    source: str  # "ollama" or "api"


@dataclass
class MMSDConversionResult:
    """Result of a Java → Bedrock conversion via MMSD engine."""

    success: bool
    bedrock_manifest: str = ""
    bedrock_script: str = ""
    reasoning: str = ""
    confidence: float = 0.0  # 0.0 to 1.0
    variants: list[MMSDConversionVariant] = field(default_factory=list)
    model_used: str = ""
    engine_mode: str = "ollama"
    latency_ms: int = 0
    error: str = ""
    ollama_available: bool = True


# Ollama configuration
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "portkit-coder-grpo8")

# Model configurations for Ollama
OLLAMA_MODELS = {
    "grpo6": {
        "name": "portkit-coder-grpo6",
        "description": "GRPO6 model - Group REINFORCE + SFT init",
        "reward": 0.6177,
    },
    "grpo7": {
        "name": "portkit-coder-grpo7",
        "description": "GRPO7 model - Self-reflection RL",
        "reward": 0.6172,
    },
    "grpo8": {
        "name": "portkit-coder-grpo8",
        "description": "GRPO8 model - Anti-hallucination focus",
        "reward": 0.62,  # estimated
    },
    "sft1": {
        "name": "portkit-coder-sft1",
        "description": "SFT v1 model - Supervised Fine-tuning",
        "reward": 0.58,  # estimated
    },
}


def _check_ollama_available() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def _list_ollama_models() -> list[str]:
    """List available models in Ollama."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


def _call_ollama(
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    timeout: float = 30.0,
) -> tuple[str, int]:
    """
    Call Ollama for inference.

    Returns:
        Tuple of (response_text, latency_ms)
    """
    start_time = time.time()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        },
    }

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        response = data["message"]["content"]

    latency_ms = int((time.time() - start_time) * 1000)
    return response, latency_ms


# System prompt for MMSD conversion
MMSD_SYSTEM_PROMPT = """You are PortKit, an expert at converting Minecraft Java Edition Forge mods to Bedrock Edition Add-ons.

Given a mod description and Java source code, you must:
1. **Reason** through the conversion — map each Java class/event/registry to its Bedrock equivalent
2. **Produce** a complete Bedrock Add-on implementation

Key mapping rules:
- Java `RegistryEvent.Register<Block/Item>` → Bedrock `blocks.json` / `items.json` definitions
- Java `onItemRightClick` → Bedrock `@minecraft/server` `beforeEvents.itemUse`
- Java `onItemUse` (on block) → Bedrock `beforeEvents.itemUseOn`
- Java entity spawning (`new EntityX(world)`) → Bedrock `dimension.spawnEntity()`
- Java NBT data → Bedrock entity properties / components
- Java `@Mod.EventHandler` lifecycle → Bedrock `world.afterEvents.worldInitialize`
- Java packages (`com.example.mod`) → Bedrock namespace prefixes (`namespace:item_name`)
- Use `@minecraft/server` module for all scripting (NOT the deprecated `mojang-*` modules)
- Target Bedrock format_version 2 and engine version 1.20.0+
- Always include a complete manifest.json with script module and `@minecraft/server` dependency
- Use `system.run()` for operations that require write access in beforeEvents callbacks

Output format:
1. Start with "## Conversion Plan" — explain each mapping decision
2. Then "## Bedrock Add-on Output" — provide all files with proper code blocks

Be concise and produce working Bedrock JavaScript code."""


class MMSDConverter:
    """
    MMSD Converter - Integrates trained GRPO models into the PortKit conversion pipeline.

    Supports three modes:
    - ollama: Use Ollama local inference (fastest, private)
    - api: Use premium API fallback (OpenRouter)
    - ab: Run both and compare results

    Usage:
        converter = MMSDConverter(engine="ollama")
        result = converter.convert(java_code, instruction="Custom sword mod")
        print(result.bedrock_script)
        print(result.confidence)

    Fallback:
        If Ollama is unavailable in ollama mode, automatically falls back to API.
        Set engine="api" to force API-only mode.
    """

    def __init__(
        self,
        engine: str = "ollama",
        ollama_model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        force_fallback: bool = False,
    ):
        """
        Initialize MMSD converter.

        Args:
            engine: Engine mode - "ollama", "api", or "ab" (A/B testing)
            ollama_model: Ollama model name (default: from OLLAMA_MODEL env or best available)
            api_key: OpenRouter API key (default: from OPENROUTER_API_KEY env)
            timeout: Request timeout in seconds
            force_fallback: If True, skip Ollama and use API directly
        """
        self.engine_mode = EngineMode(engine)
        self.timeout = timeout
        self.force_fallback = force_fallback

        # Set up Ollama
        self.ollama_model = ollama_model or DEFAULT_OLLAMA_MODEL
        self._ollama_available = _check_ollama_available() if not force_fallback else False

        # Set up API fallback
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")

        # In AB mode, we need API key for comparison
        if self.engine_mode == EngineMode.AB and not self.api_key:
            logger.warning(
                "A/B testing mode requires OPENROUTER_API_KEY, falling back to ollama-only"
            )
            self.engine_mode = EngineMode.OLLAMA

        if self._ollama_available:
            available_models = _list_ollama_models()
            if self.ollama_model not in available_models:
                logger.warning(
                    f"Model {self.ollama_model} not found in Ollama. "
                    f"Available: {available_models}. Will use first available."
                )
                self.ollama_model = available_models[0] if available_models else ""

    @property
    def ollama_available(self) -> bool:
        """Check if Ollama is available."""
        return self._ollama_available

    def convert(
        self,
        java_code: str,
        instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> MMSDConversionResult:
        """
        Convert Java source code to Bedrock using MMSD engine.

        Args:
            java_code: Java source code to convert
            instruction: Optional mod description/instruction
            temperature: Sampling temperature (default 0.1 for reproducible output)

        Returns:
            MMSDConversionResult with Bedrock code, confidence, and variants
        """
        if self.engine_mode == EngineMode.AB:
            return self._convert_ab(java_code, instruction, temperature)

        if self.engine_mode == EngineMode.API or not self._ollama_available:
            return self._convert_api(java_code, instruction, temperature)

        return self._convert_ollama(java_code, instruction, temperature)

    def _convert_ollama(
        self,
        java_code: str,
        instruction: Optional[str],
        temperature: float,
    ) -> MMSDConversionResult:
        """Convert using Ollama local inference."""
        prompt = self._build_prompt(java_code, instruction)

        try:
            response, latency_ms = _call_ollama(
                model=self.ollama_model,
                prompt=prompt,
                system_prompt=MMSD_SYSTEM_PROMPT,
                timeout=self.timeout,
            )

            result = self._parse_output(response, self.ollama_model, latency_ms)
            result.engine_mode = "ollama"
            result.ollama_available = self._ollama_available
            return result

        except Exception as e:
            logger.warning(f"Ollama conversion failed: {e}")

            # Fallback to API if available
            if self.api_key:
                logger.info("Falling back to API...")
                return self._convert_api(java_code, instruction, temperature)

            return MMSDConversionResult(
                success=False,
                error=f"Ollama failed: {e}",
                engine_mode="ollama",
                ollama_available=self._ollama_available,
            )

    def _convert_api(
        self,
        java_code: str,
        instruction: Optional[str],
        temperature: float,
    ) -> MMSDConversionResult:
        """Convert using premium API (OpenRouter)."""
        try:
            from mmsd.premium_client import PortKitPremium, ConversionResult

            client = PortKitPremium(api_key=self.api_key)
            api_result = client.convert(
                instruction=instruction or "Minecraft Java mod conversion",
                java_source=java_code,
            )
            client.close()

            # Convert API result to MMSDConversionResult
            if api_result.success:
                result = MMSDConversionResult(
                    success=True,
                    bedrock_manifest=api_result.bedrock_manifest,
                    bedrock_script=api_result.bedrock_script,
                    reasoning=api_result.reasoning,
                    confidence=0.85,  # API models are reliable
                    model_used=api_result.model_used,
                    engine_mode="api",
                    latency_ms=api_result.latency_ms,
                )
                return result
            else:
                return MMSDConversionResult(
                    success=False,
                    error=api_result.error,
                    engine_mode="api",
                    latency_ms=api_result.latency_ms,
                )

        except Exception as e:
            return MMSDConversionResult(
                success=False,
                error=f"API conversion failed: {e}",
                engine_mode="api",
            )

    def _convert_ab(
        self,
        java_code: str,
        instruction: Optional[str],
        temperature: float,
    ) -> MMSDConversionResult:
        """A/B test: Run both Ollama and API, compare results."""
        variants = []

        # Run Ollama if available
        if self._ollama_available:
            ollama_result = self._convert_ollama(java_code, instruction, temperature)
            if ollama_result.success:
                variants.append(
                    MMSDConversionVariant(
                        bedrock_manifest=ollama_result.bedrock_manifest,
                        bedrock_script=ollama_result.bedrock_script,
                        reasoning=ollama_result.reasoning,
                        confidence=ollama_result.confidence,
                        source="ollama",
                    )
                )
        else:
            ollama_result = None

        # Run API
        api_result = self._convert_api(java_code, instruction, temperature)
        if api_result.success:
            variants.append(
                MMSDConversionVariant(
                    bedrock_manifest=api_result.bedrock_manifest,
                    bedrock_script=api_result.bedrock_script,
                    reasoning=api_result.reasoning,
                    confidence=api_result.confidence,
                    source="api",
                )
            )

        # Use the best result (highest confidence) as primary
        best_result = max(variants, key=lambda v: v.confidence) if variants else None

        if best_result:
            return MMSDConversionResult(
                success=True,
                bedrock_manifest=best_result.bedrock_manifest,
                bedrock_script=best_result.bedrock_script,
                reasoning=best_result.reasoning,
                confidence=best_result.confidence,
                variants=variants,
                model_used=best_result.source,
                engine_mode="ab",
                latency_ms=(ollama_result.latency_ms if ollama_result else 0)
                + api_result.latency_ms,
                ollama_available=self._ollama_available,
            )
        else:
            return MMSDConversionResult(
                success=False,
                error="Both Ollama and API conversions failed",
                engine_mode="ab",
                variants=variants,
                ollama_available=self._ollama_available,
            )

    def _build_prompt(self, java_code: str, instruction: Optional[str]) -> str:
        """Build the conversion prompt."""
        instruction = instruction or "Minecraft Java mod conversion"
        return f"""Mod Description: {instruction}

Java Source:
```java
{java_code}
```

Convert this to a Bedrock Add-on."""

    def _parse_output(
        self,
        output: str,
        model_used: str,
        latency_ms: int,
    ) -> MMSDConversionResult:
        """Parse model output into structured result."""
        # Extract reasoning
        reasoning = ""
        plan_match = re.search(r"## Conversion Plan\s*(.*?)(?=## Bedrock|$)", output, re.DOTALL)
        if plan_match:
            reasoning = plan_match.group(1).strip()

        # Extract JSON blocks (manifest, etc.)
        json_blocks = re.findall(r"```json\s*(.*?)\s*```", output, re.DOTALL)
        manifest = ""
        for block in json_blocks:
            if any(key in block for key in ["format_version", "header", "modules"]):
                manifest = block.strip()
                break

        # Extract JS blocks
        js_blocks = re.findall(r"```(?:javascript|js)\b\s*(.*?)\s*```", output, re.DOTALL)
        script = max(js_blocks, key=len).strip() if js_blocks else ""

        success = bool(reasoning and (manifest or script))

        # Estimate confidence based on output completeness
        confidence = 0.0
        if success:
            confidence = 0.7  # Base confidence
            if manifest:
                confidence += 0.1
            if script:
                confidence += 0.1
            if reasoning:
                confidence += 0.1

        return MMSDConversionResult(
            success=success,
            reasoning=reasoning,
            bedrock_manifest=manifest,
            bedrock_script=script,
            confidence=min(confidence, 1.0),
            model_used=model_used,
            latency_ms=latency_ms,
        )

    def get_metrics(self) -> dict:
        """Get converter metrics and status."""
        return {
            "engine_mode": self.engine_mode.value,
            "ollama_available": self._ollama_available,
            "ollama_model": self.ollama_model,
            "api_key_configured": bool(self.api_key),
            "timeout": self.timeout,
        }


def create_converter(
    engine: str = "ollama",
    ollama_model: Optional[str] = None,
) -> MMSDConverter:
    """
    Factory function to create an MMSD converter.

    Args:
        engine: "ollama", "api", or "ab"
        ollama_model: Specific Ollama model to use

    Returns:
        Configured MMSDConverter instance
    """
    return MMSDConverter(engine=engine, ollama_model=ollama_model)
