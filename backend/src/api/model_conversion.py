"""
MMSD Model Conversion API Endpoints

Uses trained GRPO models via Ollama for local inference with API fallback.
Integrates with ai-engine/converters/mmsd_converter.py.

Endpoints:
- POST /api/v1/model/convert - Model-based conversion using Ollama or API
- GET /api/v1/model/status - Check Ollama and model status
- GET /api/v1/model/metrics - Get converter metrics
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db
from db.models import User
from security.auth import verify_api_key
from api._authz import get_current_user
from utils.ai_engine_path import ensure_ai_engine_on_path
from services.feature_flags import is_feature_enabled, FeatureFlagNotEnabledError

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/model", tags=["MMSD Model Conversion"])


class ModelConvertRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=5000)
    java_source: str = Field(..., min_length=1)
    engine: str = Field(
        "ollama",
        description="Engine to use: 'ollama' (local), 'api' (OpenRouter fallback), 'ab' (A/B test)",
    )
    ollama_model: Optional[str] = Field(
        None,
        description="Specific Ollama model to use (default: from OLLAMA_MODEL env or best available)",
    )


class MMSDConversionVariantResponse(BaseModel):
    bedrock_manifest: str
    bedrock_script: str
    reasoning: str
    confidence: float
    source: str


class ModelConvertResponse(BaseModel):
    success: bool
    reasoning: str = ""
    bedrock_manifest: str = ""
    bedrock_script: str = ""
    confidence: float = 0.0
    variants: list[MMSDConversionVariantResponse] = []
    model_used: str = ""
    engine_mode: str = "ollama"
    latency_ms: int = 0
    ollama_available: bool = True
    error: str = ""


class ModelStatusResponse(BaseModel):
    ollama_available: bool
    ollama_model: str
    api_key_configured: bool
    available_models: list[str]


class ModelMetricsResponse(BaseModel):
    engine_mode: str
    ollama_available: bool
    ollama_model: str
    api_key_configured: bool
    timeout: float


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional authentication for model conversion."""
    if not credentials:
        return None

    token = credentials.credentials

    if token.startswith("mpk_"):
        return await verify_api_key(db, token)

    from security.auth import verify_token
    from uuid import UUID

    user_id = verify_token(token)
    if not user_id:
        return None

    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        return None

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_uuid))
    return result.scalar_one_or_none()


def require_feature_flag(flag_name: str):
    """Dependency that checks if a feature flag is enabled."""

    async def check_flag():
        if not is_feature_enabled(flag_name):
            raise FeatureFlagNotEnabledError(f"Feature '{flag_name}' is not enabled")
        return True

    return check_flag


@router.post("/convert", response_model=ModelConvertResponse)
async def model_convert(
    request: ModelConvertRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    _: bool = Depends(require_feature_flag("mmsd_model_conversion")),
):
    r"""
    Model-based conversion using trained GRPO models.

    Uses Ollama for local inference when available, with automatic fallback to
    OpenRouter API. Supports A/B testing mode to compare both engines.

    **Request Body:**
    ```json
    {
        "instruction": "Custom sword mod that adds glowing diamond swords",
        "java_source": "public class MySwordMod { ... }",
        "engine": "ollama",
        "ollama_model": "portkit-coder-grpo8"
    }
    ```

    **Response:**
    ```json
    {
        "success": true,
        "reasoning": "## Conversion Plan\n\n1. Item registration...",
        "bedrock_manifest": "{\"format_version\": 2, ...}",
        "bedrock_script": "import { world } from '@minecraft/server';\n...",
        "confidence": 0.85,
        "variants": [],
        "model_used": "portkit-coder-grpo8",
        "engine_mode": "ollama",
        "latency_ms": 2340,
        "ollama_available": true,
        "error": ""
    }
    ```
    """
    ensure_ai_engine_on_path()

    try:
        from converters.mmsd_converter import MMSDConverter, MMSDConversionResult

        converter = MMSDConverter(
            engine=request.engine,
            ollama_model=request.ollama_model,
        )

        result = converter.convert(
            java_code=request.java_source,
            instruction=request.instruction,
        )

        return ModelConvertResponse(
            success=result.success,
            reasoning=result.reasoning,
            bedrock_manifest=result.bedrock_manifest,
            bedrock_script=result.bedrock_script,
            confidence=result.confidence,
            variants=[
                MMSDConversionVariantResponse(
                    bedrock_manifest=v.bedrock_manifest,
                    bedrock_script=v.bedrock_script,
                    reasoning=v.reasoning,
                    confidence=v.confidence,
                    source=v.source,
                )
                for v in result.variants
            ],
            model_used=result.model_used,
            engine_mode=result.engine_mode,
            latency_ms=result.latency_ms,
            ollama_available=result.ollama_available,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"Model conversion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model conversion failed: {str(e)}",
        )


@router.get("/status", response_model=ModelStatusResponse)
async def model_status(
    current_user: Optional[User] = Depends(get_current_user_optional),
    _: bool = Depends(require_feature_flag("mmsd_model_conversion")),
):
    """
    Check Ollama and model status.

    **Response:**
    ```json
    {
        "ollama_available": true,
        "ollama_model": "portkit-coder-grpo8",
        "api_key_configured": true,
        "available_models": ["portkit-coder-grpo6", "portkit-coder-grpo8"]
    }
    ```
    """
    ensure_ai_engine_on_path()

    try:
        from converters.mmsd_converter import (
            MMSDConverter,
            _check_ollama_available,
            _list_ollama_models,
        )

        ollama_available = _check_ollama_available()
        available_models = _list_ollama_models() if ollama_available else []
        api_key_configured = bool(os.environ.get("OPENROUTER_API_KEY", ""))

        # Get default model
        default_model = os.environ.get("OLLAMA_MODEL", "portkit-coder-grpo8")

        return ModelStatusResponse(
            ollama_available=ollama_available,
            ollama_model=default_model,
            api_key_configured=api_key_configured,
            available_models=available_models,
        )

    except Exception as e:
        logger.error(f"Failed to get model status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model status: {str(e)}",
        )


@router.get("/metrics", response_model=ModelMetricsResponse)
async def model_metrics(
    current_user: Optional[User] = Depends(get_current_user_optional),
    _: bool = Depends(require_feature_flag("mmsd_model_conversion")),
):
    """
    Get converter metrics and configuration.

    **Response:**
    ```json
    {
        "engine_mode": "ollama",
        "ollama_available": true,
        "ollama_model": "portkit-coder-grpo8",
        "api_key_configured": true,
        "timeout": 30.0
    }
    ```
    """
    ensure_ai_engine_on_path()

    try:
        from converters.mmsd_converter import MMSDConverter

        converter = MMSDConverter()
        metrics = converter.get_metrics()

        return ModelMetricsResponse(**metrics)

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics: {str(e)}",
        )
