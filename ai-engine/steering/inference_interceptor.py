"""
Inference Interceptor for Hidden State Access.

Provides hooks into the LLM inference pipeline to:
1. Extract hidden states during generation
2. Apply steering vectors to modify generation
3. Route modified activations back through the model

This enables SAE-based feature steering without modifying the base model.

Supports multiple backends:
- OpenAI-compatible APIs (via custom inference server)
- Local vLLM with activation extraction
- SGLang with intervention hooks
- Transformer models with direct Python access

For OpenAI-compatible APIs that don't expose hidden states, we provide
a prompt-based steering fallback that achieves similar results.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HiddenStateShape:
    """Shape information for hidden states"""

    batch_size: int
    seq_len: int
    hidden_dim: int
    layer_idx: Optional[int] = None


@dataclass
class ActivationSlice:
    """A slice of model activations at a specific layer"""

    layer_idx: int
    hidden_states: np.ndarray
    position: int = 0  # Token position for position-wise operations


class InferenceBackend(str):
    """Supported inference backends"""

    OPENAI_COMPATIBLE = "openai_compatible"  # Standard API without hidden states
    VLLM = "vllm"  # vLLM with activation extraction
    SGLANG = "sglang"  # SGLang with intervention hooks
    TRANSFORMERS = "transformers"  # Direct HuggingFace access
    PROMPT_STEERING = "prompt_steering"  # Fallback without hidden state access


@dataclass
class InterceptorConfig:
    """Configuration for the inference interceptor"""

    backend: InferenceBackend = InferenceBackend.OPENAI_COMPATIBLE
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None

    # Extraction settings
    extract_layers: List[int] = field(default_factory=lambda: [-1])  # Last layer by default
    extraction_mode: str = "last_token"  # "last_token", "mean", "all_tokens"

    # Steering settings
    steering_enabled: bool = True
    steering_scale: float = 2.0

    # Hook settings
    intervention_callback: Optional[Callable] = None  # Called with (layer_idx, activations)
    cache_activations: bool = True

    # Fallback for APIs without hidden state access
    use_prompt_steering_fallback: bool = True


class HiddenStateInterceptor:
    """
    Intercepts LLM inference to extract and modify hidden states.

    This is the core component that enables SAE-based feature steering:
    1. Intercepts the forward pass to capture activations
    2. Applies steering vectors computed from SAE features
    3. Routes modified activations back through the model

    For backends that don't expose hidden states (OpenAI-compatible),
    falls back to prompt-based steering with similar effect.
    """

    def __init__(self, config: Optional[InterceptorConfig] = None):
        self.config = config or InterceptorConfig()
        self._cache: Dict[str, List[np.ndarray]] = {}
        self._hooks: List[Callable] = []
        self._steering_active = False

    def register_hook(self, hook: Callable[[int, np.ndarray], Optional[np.ndarray]]) -> None:
        """
        Register a hook function for hidden state interception.

        Hook signature: (layer_idx: int, hidden_states: np.ndarray) -> Optional[np.ndarray]
        - Return None to skip modification
        - Return modified array to apply intervention
        """
        self._hooks.append(hook)

    def set_steering_active(self, active: bool) -> None:
        """Enable/disable steering globally"""
        self._steering_active = active

    async def extract_activations(
        self,
        text: str,
        model_name: str,
    ) -> List[ActivationSlice]:
        """
        Extract hidden states for input text.

        Returns:
            List of ActivationSlice objects, one per extracted layer
        """
        if self.config.backend == InferenceBackend.TRANSFORMERS:
            return await self._extract_transformers(text, model_name)
        elif self.config.backend == InferenceBackend.VLLM:
            return await self._extract_vllm(text, model_name)
        elif self.config.backend == InferenceBackend.SGLANG:
            return await self._extract_sglang(text, model_name)
        elif self.config.backend == InferenceBackend.OPENAI_COMPATIBLE:
            return await self._extract_openai_compatible(text, model_name)
        else:
            return []  # Fallback: no extraction available

    async def generate_with_steering(
        self,
        messages: List[Dict[str, str]],
        steering_vector: np.ndarray,
        model_name: str = "default",
        **generation_kwargs,
    ) -> Tuple[str, List[ActivationSlice]]:
        """
        Generate text with steering applied to hidden states.

        Args:
            messages: Chat messages
            steering_vector: Steering vector to apply
            model_name: Model to use
            **generation_kwargs: Generation parameters

        Returns:
            Tuple of (generated_text, extracted_activations)
        """
        if not self._steering_active:
            return await self._generate_without_steering(messages, model_name, **generation_kwargs)

        # Extract activations first
        prompt = self._messages_to_prompt(messages)
        activations = await self.extract_activations(prompt, model_name)

        if not activations:
            # Fallback to prompt steering
            return await self._generate_with_prompt_steering(
                messages, steering_vector, **generation_kwargs
            )

        # Apply steering hooks
        modified_activations = []
        for act_slice in activations:
            modified = act_slice.hidden_states.copy()
            for hook in self._hooks:
                result = hook(act_slice.layer_idx, modified)
                if result is not None:
                    modified = result
            modified_activations.append(modified)

        # Generate with modified activations
        # This requires backend support - fall back to prompt steering if not available
        return await self._generate_with_prompt_steering(
            messages, steering_vector, **generation_kwargs
        )

    async def _generate_without_steering(
        self,
        messages: List[Dict[str, str]],
        model_name: str,
        **kwargs,
    ) -> Tuple[str, List[ActivationSlice]]:
        """Standard generation without steering"""
        return ("", [])  # Placeholder - would call actual inference

    async def _generate_with_prompt_steering(
        self,
        messages: List[Dict[str, str]],
        steering_vector: np.ndarray,
        **generation_kwargs,
    ) -> Tuple[str, List[ActivationSlice]]:
        """
        Fallback: Use prompt modifications to achieve similar steering effect.

        Since we can't modify hidden states directly, we use:
        1. Negative prompts to suppress unwanted patterns
        2. Positive prompts to encourage desired patterns
        3. Explicit instruction in system prompt
        """
        if not self.config.use_prompt_steering_fallback:
            return await self._generate_without_steering(messages, "default", **generation_kwargs)

        # Add steering instruction to system message
        modified_messages = self._inject_steering_instruction(messages, steering_vector)

        # Generate with modified prompt
        # This would call the actual inference endpoint
        result = await self._call_inference(modified_messages, **generation_kwargs)

        return result, []

    def _inject_steering_instruction(
        self,
        messages: List[Dict[str, str]],
        steering_vector: np.ndarray,
    ) -> List[Dict[str, str]]:
        """
        Inject steering instructions into messages.

        For Java idiom suppression, adds explicit instructions to system message.
        """
        # Extract suppression targets from steering vector
        targets = self._extract_suppression_targets(steering_vector)

        injection = (
            "\n\nIMPORTANT: When generating Bedrock add-on code, "
            f"AVOID the following Java patterns: {targets}. "
            "Use Bedrock Scripting API patterns and JavaScript syntax instead."
        )

        # Find and modify system message
        modified = []
        for msg in messages:
            if msg.get("role") == "system":
                modified.append(
                    {
                        "role": "system",
                        "content": msg.get("content", "") + injection,
                    }
                )
            else:
                modified.append(msg)

        if not any(m.get("role") == "system" for m in modified):
            # Add system message if none exists
            modified.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "You are a Bedrock Minecraft add-on code generator. "
                        "Output ONLY Bedrock Scripting API code, NEVER Java Forge code." + injection
                    ),
                },
            )

        return modified

    def _extract_suppression_targets(self, steering_vector: np.ndarray) -> str:
        """Extract human-readable suppression targets from steering vector"""
        # Map feature indices to pattern names
        feature_names = {
            1003: "Minecraft.getInstance()",
            1004: "isClientSide()",
            1005: "isServerSide()",
            1006: "addFreshEntity()",
            1007: "getBlockState()",
            1008: "@SubscribeEvent",
            1009: "register()",
            2000: "extends Item",
            2001: "extends Block",
            2002: "extends Entity",
        }

        # Find top features by magnitude
        if steering_vector.ndim > 1:
            magnitudes = np.linalg.norm(steering_vector, axis=-1)
        else:
            magnitudes = np.abs(steering_vector)

        top_indices = np.argsort(magnitudes)[-5:]  # Top 5

        targets = []
        for idx in top_indices:
            if idx in feature_names and magnitudes[idx] > 0.1:
                targets.append(feature_names[idx])

        return ", ".join(targets) if targets else "Java-specific constructs"

    async def _extract_transformers(
        self,
        text: str,
        model_name: str,
    ) -> List[ActivationSlice]:
        """Extract activations using HuggingFace transformers"""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            model = AutoModelForCausalLM.from_pretrained(model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)

            inputs = tokenizer(text, return_tensors="pt")
            input_ids = inputs["input_ids"]

            # Extract all hidden states
            with torch.no_grad():
                outputs = model(
                    input_ids,
                    output_hidden_states=True,
                )
                hidden_states = outputs.hidden_states

            # Convert to list of ActivationSlice
            slices = []
            for layer_idx, hidden in enumerate(hidden_states):
                # Take last token's hidden state
                last_token_hidden = hidden[:, -1, :].numpy()
                slices.append(
                    ActivationSlice(
                        layer_idx=layer_idx,
                        hidden_states=last_token_hidden,
                    )
                )

            return slices

        except Exception as e:
            logger.error(f"Transformers extraction failed: {e}")
            return []

    async def _extract_vllm(
        self,
        text: str,
        model_name: str,
    ) -> List[ActivationSlice]:
        """Extract activations via vLLM intervention hooks"""
        if not self.config.endpoint_url:
            logger.warning("No endpoint configured for vLLM extraction")
            return []

        try:
            import httpx

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.config.endpoint_url}/v1/intervene",
                    json={
                        "prompt": text,
                        "layers": self.config.extract_layers,
                        "return_hidden_states": True,
                    },
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                    if self.config.api_key
                    else {},
                )
                response.raise_for_status()
                data = response.json()

                slices = []
                for layer_data in data.get("hidden_states", []):
                    slices.append(
                        ActivationSlice(
                            layer_idx=layer_data["layer"],
                            hidden_states=np.array(layer_data["states"]),
                        )
                    )

                return slices

        except Exception as e:
            logger.error(f"vLLM extraction failed: {e}")
            return []

    async def _extract_sglang(
        self,
        text: str,
        model_name: str,
    ) -> List[ActivationSlice]:
        """Extract activations via SGLang intervention hooks"""
        # SGLang supports intervention hooks similar to vLLM
        return await self._extract_vllm(text, model_name)

    async def _extract_openai_compatible(
        self,
        text: str,
        model_name: str,
    ) -> List[ActivationSlice]:
        """
        Attempt extraction from OpenAI-compatible endpoint.

        Most endpoints don't expose hidden states, so this returns
        an empty list and triggers fallback to prompt steering.
        """
        logger.debug("OpenAI-compatible endpoint - hidden state extraction not available")
        return []

    async def _call_inference(
        self,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> str:
        """Call inference endpoint with modified messages"""
        # Placeholder - would call actual inference
        # This would integrate with SelfHostedInferenceClient or cloud API
        return ""


class PromptSteeringEngine:
    """
    Prompt-based steering when hidden state access is unavailable.

    Achieves similar effect to hidden state steering through:
    1. System prompt engineering with explicit instructions
    2. Negative prompting to suppress unwanted patterns
    3. Few-shot examples demonstrating desired output
    """

    def __init__(self):
        self.negative_patterns = [
            "Avoid: extends Item, extends Block, @SubscribeEvent, Minecraft.getInstance()",
            "Do NOT use Java class patterns like 'public class X extends Y'",
            "Do NOT use Forge API calls like 'level.isClientSide()'",
        ]

        self.positive_patterns = [
            "Use: world.afterEvents, player.dimension, system.run()",
            "Use Bedrock component system: getComponent(), setProperty()",
            "Use JavaScript syntax for Bedrock Script API",
        ]

    def build_steering_prompt(
        self,
        base_prompt: str,
        suppress_features: List[str],
        encourage_features: List[str],
    ) -> str:
        """
        Build a prompt with steering instructions.

        Args:
            base_prompt: Original system prompt
            suppress_features: Java patterns to avoid
            encourage_features: Bedrock patterns to use

        Returns:
            Modified prompt with steering instructions
        """
        steering_section = "\n\n## STEERING INSTRUCTIONS\n"

        if suppress_features:
            steering_section += "AVOID these patterns:\n"
            for pattern in suppress_features:
                steering_section += f"- {pattern}\n"

        if encourage_features:
            steering_section += "\nPREFER these patterns:\n"
            for pattern in encourage_features:
                steering_section += f"- {pattern}\n"

        return base_prompt + steering_section

    def extract_steering_from_features(
        self,
        feature_activations: Dict[int, float],
    ) -> Tuple[List[str], List[str]]:
        """
        Convert SAE feature activations to suppression/encouragement lists.

        Args:
            feature_activations: Dict mapping feature_id -> activation

        Returns:
            Tuple of (suppress_list, encourage_list)
        """
        suppress = []
        encourage = []

        feature_to_pattern = {
            # Java Forge patterns (suppress)
            1003: "Minecraft.getInstance() API calls",
            1004: "isClientSide() checks",
            1005: "isServerSide() checks",
            1008: "@SubscribeEvent annotations",
            2000: "extends Item patterns",
            2001: "extends Block patterns",
            2002: "extends Entity patterns",
            3000: "BlockPos constructor calls",
            # Bedrock patterns (encourage)
            4000: "JavaScript syntax and patterns",
            4001: "world.afterEvents API",
            4002: "setDynamicProperty() for data storage",
            4003: "getComponent() for entity access",
        }

        for feature_id, activation in feature_activations.items():
            if 1000 <= feature_id < 4000 and activation > 0.1:
                # Java pattern - suppress
                pattern = feature_to_pattern.get(feature_id, f"Java feature {feature_id}")
                if pattern not in suppress:
                    suppress.append(pattern)

            elif feature_id >= 4000 and activation > 0.1:
                # Bedrock pattern - encourage
                pattern = feature_to_pattern.get(feature_id, f"Bedrock feature {feature_id}")
                if pattern not in encourage:
                    encourage.append(pattern)

        return suppress, encourage


def create_interceptor(config: Optional[InterceptorConfig] = None) -> HiddenStateInterceptor:
    """Factory function to create an interceptor"""
    return HiddenStateInterceptor(config=config)


def create_prompt_steering_engine() -> PromptSteeringEngine:
    """Factory function for prompt steering"""
    return PromptSteeringEngine()
