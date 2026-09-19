"""
Health check endpoints for Kubernetes readiness and liveness probes.

This module provides:
- /health/readiness: Checks if the application can serve traffic (dependencies available)
- /health/liveness: Checks if the application is running and doesn't need to be restarted

Issue #699: Add health check endpoints
Readiness Pillar: Debugging & Observability
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter
from pydantic import BaseModel, Field
import logging

from db.base import async_engine
from services.cache import CacheService

# AI Engine configuration for health checks
AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://ai-engine:8001")
AI_ENGINE_HEALTH_TIMEOUT = 5.0  # 5 second timeout for health checks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Health check response model"""

    status: str = Field(..., description="Overall health status: healthy, degraded, or unhealthy")
    timestamp: str = Field(..., description="ISO timestamp of the health check")
    checks: Dict[str, Any] = Field(..., description="Individual check results")


class DependencyHealth(BaseModel):
    """Individual dependency health status"""

    name: str
    status: str
    latency_ms: float = 0.0
    message: str = ""


# Cache service instance (same as in main.py)
cache = CacheService()


async def check_database_health() -> DependencyHealth:
    """
    Check database connectivity and return health status.
    """
    start_time = time.time()

    try:
        from sqlalchemy import text

        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()

        latency_ms = (time.time() - start_time) * 1000

        return DependencyHealth(
            name="database",
            status="healthy",
            latency_ms=latency_ms,
            message="Database connection successful",
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"Database health check failed: {e}")

        return DependencyHealth(
            name="database",
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"Database connection failed: {str(e)}",
        )


async def check_redis_health() -> DependencyHealth:
    """
    Check Redis connectivity and return health status.
    """
    start_time = time.time()

    try:
        # Check if Redis is available through cache service
        if not cache._redis_available or cache._redis_disabled:
            return DependencyHealth(
                name="redis",
                status="unhealthy",
                latency_ms=0.0,
                message="Redis is not available or disabled",
            )

        # Try a simple Redis operation
        await cache._client.ping()

        latency_ms = (time.time() - start_time) * 1000

        return DependencyHealth(
            name="redis",
            status="healthy",
            latency_ms=latency_ms,
            message="Redis connection successful",
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"Redis health check failed: {e}")

        return DependencyHealth(
            name="redis",
            status="unhealthy",
            latency_ms=latency_ms,
            message=f"Redis connection failed: {str(e)}",
        )


async def check_ai_engine_health() -> DependencyHealth:
    """
    Check AI Engine connectivity and return health status.

    The AI Engine is an optional dependency for conversions - if it's unavailable,
    the backend reports degraded status rather than unhealthy to avoid restart loops.
    """
    start_time = time.time()

    try:
        import httpx

        async with asyncio.timeout(AI_ENGINE_HEALTH_TIMEOUT):
            async with httpx.AsyncClient(timeout=AI_ENGINE_HEALTH_TIMEOUT) as client:
                response = await client.get(f"{AI_ENGINE_URL}/health/liveness")

        latency_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            return DependencyHealth(
                name="ai_engine",
                status="healthy",
                latency_ms=latency_ms,
                message="AI Engine connection successful",
            )
        else:
            return DependencyHealth(
                name="ai_engine",
                status="degraded",
                latency_ms=latency_ms,
                message=f"AI Engine returned status {response.status_code}",
            )
    except TimeoutError:
        latency_ms = (time.time() - start_time) * 1000
        logger.warning(f"AI Engine health check timed out after {AI_ENGINE_HEALTH_TIMEOUT}s")
        return DependencyHealth(
            name="ai_engine",
            status="degraded",
            latency_ms=latency_ms,
            message=f"AI Engine health check timed out after {AI_ENGINE_HEALTH_TIMEOUT}s",
        )
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.warning(f"AI Engine health check failed: {e}")
        return DependencyHealth(
            name="ai_engine",
            status="degraded",
            latency_ms=latency_ms,
            message=f"AI Engine is unreachable: {str(e)}",
        )


@router.get("/health/readiness", response_model=HealthStatus)
async def readiness_check():
    """
    Readiness probe - checks if the application can serve traffic.

    This endpoint verifies that all required dependencies (database, Redis)
    are available. The application should only receive traffic when this
    endpoint returns healthy.

    Returns:
        HealthStatus with detailed dependency information
    """
    checks: List[DependencyHealth] = []

    # Check database
    db_health = await check_database_health()
    checks.append(db_health)

    # Check Redis (optional dependency - can be degraded)
    redis_health = await check_redis_health()
    checks.append(redis_health)

    # Check AI Engine (optional dependency - reports degraded if unavailable)
    ai_engine_health = await check_ai_engine_health()
    checks.append(ai_engine_health)

    # Determine overall status
    unhealthy_checks = [c for c in checks if c.status == "unhealthy"]
    degraded_checks = [c for c in checks if c.status == "degraded"]

    if unhealthy_checks:
        # If database is unhealthy, the app cannot serve traffic
        if any(c.name == "database" and c.status == "unhealthy" for c in checks):
            status = "unhealthy"
        else:
            status = "degraded"
    elif degraded_checks:
        # AI Engine or Redis degraded - conversions may fail but basic ops work
        status = "degraded"
    else:
        status = "healthy"

    return HealthStatus(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks={
            "dependencies": {
                c.name: {
                    "status": c.status,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                }
                for c in checks
            }
        },
    )


@router.get("/health/liveness", response_model=HealthStatus)
async def liveness_check():
    """
    Liveness probe - checks if the application is running and doesn't need restart.

    This endpoint verifies that the application process is running and can
    handle requests. A failing liveness probe indicates the container should
    be restarted.

    Returns:
        HealthStatus indicating the application is running
    """
    # Liveness only checks if the process is running
    # No dependency checks - we don't want restart loops
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks={
            "application": {
                "status": "running",
                "message": "Application process is running",
            }
        },
    )


@router.get("/health", response_model=HealthStatus)
async def basic_health_check():
    """
    Basic health check endpoint (alias for liveness).

    Returns:
        HealthStatus with basic health information
    """
    return await liveness_check()
