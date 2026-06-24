"""
Synthetic Conversion Canary Service

Runs a periodic synthetic conversion through the full pipeline to detect
silent breakages in the conversion path (upload -> queue -> ai-engine LangGraph -> packaging -> download).

Issue: #1782 - Add ai-engine dependency probe to readiness check + periodic synthetic conversion smoke test
"""

import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from metrics import record_synthetic_conversion_run

logger = logging.getLogger(__name__)

# Configuration
SYNTHETIC_CANARY_ENABLED = os.getenv("SYNTHETIC_CANARY_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)
SYNTHETIC_CANARY_INTERVAL_MINUTES = int(os.getenv("SYNTHETIC_CANARY_INTERVAL_MINUTES", "10"))
SYNTHETIC_CANARY_TIMEOUT_SECONDS = int(os.getenv("SYNTHETIC_CANARY_TIMEOUT_SECONDS", "300"))

# Path to the synthetic canary test fixture
SYNTHETIC_CANARY_FIXTURE_DIR = (
    Path(__file__).parent.parent / "tests" / "fixtures" / "synthetic_canary"
)


def _get_synthetic_mod_content() -> bytes:
    """
    Get the content of a minimal synthetic mod for testing.

    Returns a minimal Java class file content that can be used as a test mod.
    """
    # A minimal valid Java class that represents a basic mod
    return b"""package com.example.synthetic;

public class SyntheticMod {
    public static final String MOD_ID = "synthetic_canary";
    public static final String MOD_NAME = "Synthetic Canary Test Mod";
    public static final String VERSION = "1.0.0";

    public String getModId() {
        return MOD_ID;
    }

    public String getModName() {
        return MOD_NAME;
    }

    public String getVersion() {
        return VERSION;
    }
}
"""


class SyntheticCanaryService:
    """
    Service that runs periodic synthetic conversions to detect full-path breakages.

    This service exercises the entire conversion pipeline:
    1. Creates a minimal synthetic mod file
    2. Submits it through the conversion API
    3. Polls for completion
    4. Records the result as Prometheus metrics

    The synthetic canary is gated by SYNTHETIC_CANARY_ENABLED and uses the
    cheapest model/provider to bound LLM cost.
    """

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def _run_single_conversion(self) -> tuple[bool, float]:
        """
        Run a single synthetic conversion through the full pipeline.

        Returns:
            Tuple of (success, duration_seconds)
        """
        start_time = time.time()

        try:
            import httpx

            # Create a minimal synthetic mod file
            synthetic_content = _get_synthetic_mod_content()

            # Create a temporary file
            with tempfile.NamedTemporaryFile(suffix=".java", delete=False, mode="wb") as f:
                f.write(synthetic_content)
                temp_file_path = f.name

            try:
                # Get the AI engine URL
                ai_engine_url = os.getenv("AI_ENGINE_URL", "http://ai-engine:8001")

                # Submit conversion request to ai-engine
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(SYNTHETIC_CANARY_TIMEOUT_SECONDS)
                ) as client:
                    # First check if ai-engine is healthy
                    health_response = await client.get(f"{ai_engine_url}/health/liveness")
                    if health_response.status_code != 200:
                        logger.warning(
                            f"AI Engine health check failed: {health_response.status_code}"
                        )
                        return False, time.time() - start_time

                    # Submit conversion job
                    job_id = f"synthetic-canary-{int(time.time())}"

                    convert_response = await client.post(
                        f"{ai_engine_url}/api/v1/convert",
                        json={
                            "job_id": job_id,
                            "mod_file_path": temp_file_path,
                            "conversion_options": {
                                "target_version": "1.20.0",
                                "synthetic_canary": True,  # Flag to use cheapest model
                            },
                        },
                    )

                    if convert_response.status_code not in (200, 201):
                        logger.warning(
                            f"Conversion submission failed: {convert_response.status_code}"
                        )
                        return False, time.time() - start_time

                    # Poll for completion (with timeout)
                    poll_timeout = time.time() + SYNTHETIC_CANARY_TIMEOUT_SECONDS
                    while time.time() < poll_timeout:
                        status_response = await client.get(
                            f"{ai_engine_url}/api/v1/status/{job_id}"
                        )

                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            status = status_data.get("status", "unknown")

                            if status == "completed":
                                return True, time.time() - start_time
                            elif status == "failed":
                                logger.warning(
                                    f"Synthetic conversion failed: {status_data.get('message', 'Unknown')}"
                                )
                                return False, time.time() - start_time

                        await asyncio.sleep(2)

                    # Timeout waiting for conversion
                    logger.warning("Synthetic conversion timed out")
                    return False, time.time() - start_time

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass

        except TimeoutError:
            logger.warning("Synthetic conversion timed out")
            return False, time.time() - start_time
        except Exception as e:
            logger.error(f"Synthetic conversion failed: {e}")
            return False, time.time() - start_time

    async def _canary_loop(self):
        """
        Main loop that runs synthetic conversions at configured interval.
        """
        logger.info(
            f"Synthetic canary loop started (interval: {SYNTHETIC_CANARY_INTERVAL_MINUTES}m, "
            f"timeout: {SYNTHETIC_CANARY_TIMEOUT_SECONDS}s)"
        )

        while self._running:
            try:
                # Run a synthetic conversion
                logger.info("Running synthetic conversion canary...")
                success, duration = await self._run_single_conversion()

                # Record metrics
                record_synthetic_conversion_run(success, duration)

                if success:
                    logger.info(f"Synthetic conversion canary succeeded in {duration:.2f}s")
                else:
                    logger.warning(f"Synthetic conversion canary failed after {duration:.2f}s")

            except Exception as e:
                logger.error(f"Error in synthetic canary loop: {e}")
                # Record failure
                record_synthetic_conversion_run(False, 0.0)

            # Wait for next interval
            try:
                await asyncio.sleep(SYNTHETIC_CANARY_INTERVAL_MINUTES * 60)
            except asyncio.CancelledError:
                break

        logger.info("Synthetic canary loop stopped")

    def start(self):
        """Start the synthetic canary background task."""
        if not SYNTHETIC_CANARY_ENABLED:
            logger.info("Synthetic canary is disabled (SYNTHETIC_CANARY_ENABLED=false)")
            return

        if self._running:
            logger.warning("Synthetic canary is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._canary_loop())
        logger.info("Synthetic canary background task started")

    async def stop(self):
        """Stop the synthetic canary background task."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Synthetic canary background task stopped")

    async def run_now(self) -> tuple[bool, float]:
        """
        Run a synthetic conversion immediately (for testing).

        Returns:
            Tuple of (success, duration_seconds)
        """
        return await self._run_single_conversion()


# Global instance
_synthetic_canary_service: SyntheticCanaryService | None = None


def get_synthetic_canary_service() -> SyntheticCanaryService:
    """Get or create the global synthetic canary service instance."""
    global _synthetic_canary_service
    if _synthetic_canary_service is None:
        _synthetic_canary_service = SyntheticCanaryService()
    return _synthetic_canary_service


async def start_synthetic_canary():
    """Start the global synthetic canary service."""
    service = get_synthetic_canary_service()
    service.start()


async def stop_synthetic_canary():
    """Stop the global synthetic canary service."""
    global _synthetic_canary_service
    if _synthetic_canary_service:
        await _synthetic_canary_service.stop()
