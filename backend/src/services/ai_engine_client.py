"""
AI Engine Client Service

Provides HTTP client for communicating with the AI Engine API.
Handles file transfers, conversion requests, and progress polling.
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, AsyncIterator

import httpx

from services.tracing import inject_trace_context

logger = logging.getLogger(__name__)

# AI Engine configuration
AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://ai-engine:8001")
AI_ENGINE_TIMEOUT = httpx.Timeout(1800.0)  # 30 minutes timeout for long-running conversions

# Default poll interval for checking conversion status
DEFAULT_POLL_INTERVAL = 2.0  # seconds


class AIEngineError(Exception):
    """Base exception for AI Engine errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AIEngineClient:
    """
    HTTP client for AI Engine communication.

    Provides methods for:
    - Starting conversions
    - Checking conversion status
    - Downloading converted files
    - Polling for progress updates
    """

    def __init__(
        self,
        base_url: str = AI_ENGINE_URL,
        timeout: httpx.Timeout = AI_ENGINE_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """
        Check if the AI Engine is healthy.

        Returns:
            True if AI Engine is healthy, False otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/v1/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"AI Engine health check failed: {e}")
            return False

    async def start_conversion(
        self,
        job_id: str,
        mod_file_path: str,
        conversion_options: Optional[Dict[str, Any]] = None,
        experiment_variant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Start a conversion job on the AI Engine.

        Args:
            job_id: Unique job identifier
            mod_file_path: Path to the mod file
            conversion_options: Optional conversion settings
            experiment_variant: Optional experiment variant for A/B testing

        Returns:
            Conversion response with job details

        Raises:
            AIEngineError: If the conversion fails to start
        """
        try:
            client = await self._get_client()

            request_data = {
                "job_id": job_id,
                "mod_file_path": mod_file_path,
                "conversion_options": conversion_options or {},
            }

            if experiment_variant:
                request_data["experiment_variant"] = experiment_variant

            trace_headers: Dict[str, str] = {}
            inject_trace_context(trace_headers)

            response = await client.post(
                "/api/v1/convert",
                json=request_data,
                headers=trace_headers,
            )

            if response.status_code != 200:
                error_msg = f"AI Engine returned status {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("detail", error_msg)
                except Exception:
                    pass
                raise AIEngineError(error_msg, status_code=response.status_code)

            return response.json()

        except httpx.TimeoutException as e:
            logger.error(f"Timeout starting conversion: {e}")
            raise AIEngineError("Conversion request timed out")
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to AI Engine: {e}")
            raise AIEngineError("Failed to connect to AI Engine")
        except AIEngineError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting conversion: {e}")
            raise AIEngineError(f"Failed to start conversion: {str(e)}")

    async def get_conversion_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of a conversion job.

        Args:
            job_id: The job identifier

        Returns:
            Conversion status from AI Engine

        Raises:
            AIEngineError: If the job is not found or request fails
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/v1/status/{job_id}")

            if response.status_code == 404:
                raise AIEngineError("Job not found", status_code=404)

            if response.status_code != 200:
                raise AIEngineError(
                    f"Failed to get status: {response.status_code}",
                    status_code=response.status_code,
                )

            return response.json()

        except AIEngineError:
            raise
        except httpx.TimeoutException:
            raise AIEngineError("Status check timed out")
        except Exception as e:
            logger.error(f"Error getting conversion status: {e}")
            raise AIEngineError(f"Failed to get conversion status: {str(e)}")

    async def download_converted_file(
        self,
        output_path: str,
        job_id: str,
        mod_file_path: str,
        conversion_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Download a converted file from the AI Engine.

        Args:
            output_path: Local path to save the converted file
            job_id: The job identifier
            mod_file_path: Path to the original mod file
            conversion_options: Optional conversion settings

        Returns:
            Path to the downloaded file

        Raises:
            AIEngineError: If the download fails
        """
        try:
            client = await self._get_client()

            # For file download, we need to start conversion and then poll for completion
            await self.start_conversion(
                job_id=job_id,
                mod_file_path=mod_file_path,
                conversion_options=conversion_options,
            )

            # Poll until conversion completes
            async for status in self.poll_conversion_status(job_id):
                if status.get("status") == "completed":
                    break
                elif status.get("status") == "failed":
                    raise AIEngineError(
                        f"Conversion failed: {status.get('message', 'Unknown error')}"
                    )

            # Download the converted file
            response = await client.get(
                "/api/v1/download",
                params={"job_id": job_id},
                timeout=httpx.Timeout(300.0),  # 5 min timeout for download
            )

            if response.status_code != 200:
                raise AIEngineError(
                    f"Download failed with status {response.status_code}",
                    status_code=response.status_code,
                )

            # Save the file
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

            return output_path

        except AIEngineError:
            raise
        except Exception as e:
            logger.error(f"Error downloading converted file: {e}")
            raise AIEngineError(f"Failed to download converted file: {str(e)}")

    async def poll_conversion_status(
        self,
        job_id: str,
        poll_interval: Optional[float] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Poll for conversion status updates.

        Args:
            job_id: The job identifier
            poll_interval: Optional poll interval (uses default if not specified)

        Yields:
            Conversion status dict on each poll
        """
        interval = poll_interval or self.poll_interval

        while True:
            try:
                status = await self.get_conversion_status(job_id)
                yield status

                # Stop polling if terminal state
                if status.get("status") in ("completed", "failed", "cancelled"):
                    break

            except AIEngineError as e:
                if e.status_code == 404:
                    # Job not found - treat as terminal
                    yield {
                        "status": "failed",
                        "message": "Job not found",
                        "progress": 0,
                    }
                    break
                raise

            await asyncio.sleep(interval)


# Global client instance
_ai_engine_client: Optional[AIEngineClient] = None


def get_ai_engine_client() -> AIEngineClient:
    """Get or create the global AI Engine client instance."""
    global _ai_engine_client
    if _ai_engine_client is None:
        _ai_engine_client = AIEngineClient()
    return _ai_engine_client


async def close_ai_engine_client():
    """Close the global AI Engine client."""
    global _ai_engine_client
    if _ai_engine_client:
        await _ai_engine_client.close()
        _ai_engine_client = None
