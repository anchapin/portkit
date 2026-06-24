"""
Metrics Service for Portkit
Provides Prometheus metrics for monitoring conversion success rates, performance, and API costs.

Issue: #384 - Monitoring dashboards with Grafana/Prometheus (Phase 3)
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
)
from typing import Optional
import time
from collections import defaultdict
import threading

# Create a custom registry
registry = CollectorRegistry()

# ============================================
# API Metrics
# ============================================

# Request counter by endpoint and status
http_requests_total = Counter(
    "portkit_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry,
)

# Request duration histogram
http_request_duration_seconds = Histogram(
    "portkit_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry,
)

# ============================================
# Conversion Metrics
# ============================================

# Conversion job counter by status
conversion_jobs_total = Counter(
    "portkit_conversion_jobs_total",
    "Total conversion jobs",
    ["status", "target_version", "mod_type"],
    registry=registry,
)

# Conversion duration histogram
conversion_duration_seconds = Histogram(
    "portkit_conversion_duration_seconds",
    "Conversion duration in seconds",
    ["target_version", "mod_type"],
    buckets=[10, 30, 60, 120, 300, 600, 900, 1800],
    registry=registry,
)

# Current conversion queue size
conversion_queue_size = Gauge(
    "portkit_conversion_queue_size",
    "Current number of conversion jobs in queue",
    registry=registry,
)

# Active conversions gauge
active_conversions = Gauge(
    "portkit_active_conversions",
    "Number of currently active conversion jobs",
    registry=registry,
)

# ============================================
# Agent Metrics
# ============================================

# Agent execution counter
agent_executions_total = Counter(
    "portkit_agent_executions_total",
    "Total agent executions",
    ["agent_name", "status"],
    registry=registry,
)

# Agent execution duration
agent_duration_seconds = Histogram(
    "portkit_agent_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
    registry=registry,
)

# ============================================
# Token/ Cost Metrics
# ============================================

# LLM token usage
llm_tokens_total = Counter(
    "portkit_llm_tokens_total",
    "Total LLM tokens used",
    ["model", "prompt_completion"],
    registry=registry,
)

# LLM API cost in dollars
llm_cost_dollars = Counter(
    "portkit_llm_cost_dollars",
    "Total LLM API cost in dollars",
    ["model"],
    registry=registry,
)

# ============================================
# Asset Metrics
# ============================================

# Assets processed counter
assets_processed_total = Counter(
    "portkit_assets_processed_total",
    "Total assets processed",
    ["asset_type", "status"],
    registry=registry,
)

# Asset conversion duration
asset_conversion_duration_seconds = Histogram(
    "portkit_asset_conversion_duration_seconds",
    "Asset conversion duration in seconds",
    ["asset_type"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
    registry=registry,
)

# ============================================
# Database Metrics
# ============================================

# Database operation duration
db_operation_duration_seconds = Histogram(
    "portkit_db_operation_duration_seconds",
    "Database operation duration in seconds",
    ["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
    registry=registry,
)

# ============================================
# Cache Metrics
# ============================================

# Cache hit/miss counter
cache_operations_total = Counter(
    "portkit_cache_operations_total",
    "Total cache operations",
    ["operation", "cache_name"],
    registry=registry,
)

# ============================================
# Business Metrics
# ============================================

# Conversion success rate (gauge for dashboard)
conversion_success_rate = Gauge(
    "portkit_conversion_success_rate",
    "Current conversion success rate (percentage)",
    registry=registry,
)

# Average conversion time (gauge)
average_conversion_time_seconds = Gauge(
    "portkit_average_conversion_time_seconds",
    "Average conversion time in seconds",
    registry=registry,
)

# Average conversion time by mod type
average_conversion_time_by_mod_type = Gauge(
    "portkit_average_conversion_time_by_mod_type_seconds",
    "Average conversion time in seconds by mod type",
    ["target_version", "mod_type"],
    registry=registry,
)

# Total conversions completed
conversions_completed_total = Gauge(
    "portkit_conversions_completed_total",
    "Total number of successful conversions",
    registry=registry,
)

# Total conversions failed
conversions_failed_total = Gauge(
    "portkit_conversions_failed_total",
    "Total number of failed conversions",
    registry=registry,
)

# Conversion failure rate (percentage)
conversion_failure_rate = Gauge(
    "portkit_conversion_failure_rate_percent",
    "Current conversion failure rate as percentage",
    registry=registry,
)

# ============================================
# Error Metrics (for Issue #455)
# ============================================

# Error counter by category
error_total = Counter(
    "portkit_errors_total",
    "Total errors by category",
    ["error_category", "error_type", "source"],
    registry=registry,
)

# Error rate (errors per minute)
error_rate = Gauge(
    "portkit_error_rate_per_minute",
    "Current error rate per minute",
    registry=registry,
)

# Retry attempts counter
retry_attempts_total = Counter(
    "portkit_retry_attempts_total",
    "Total retry attempts",
    ["error_category", "function_name"],
    registry=registry,
)

# Successful retries counter
successful_retries_total = Counter(
    "portkit_successful_retries_total",
    "Total successful retries",
    ["error_category", "function_name"],
    registry=registry,
)

# ============================================
# Rate Limiting Metrics (Issue #643)
# ============================================

# Rate limit hits counter - incremented when requests are blocked due to rate limiting
rate_limit_hits_total = Counter(
    "portkit_rate_limit_hits_total",
    "Total number of requests blocked by rate limiting",
    ["endpoint", "client_type"],
    registry=registry,
)

# Rate limit requests counter - total requests processed by rate limiter
rate_limit_requests_total = Counter(
    "portkit_rate_limit_requests_total",
    "Total requests processed by rate limiter",
    ["endpoint", "client_type", "status"],
    registry=registry,
)

# Current rate limit usage gauge - shows current usage per client
rate_limit_current_usage = Gauge(
    "portkit_rate_limit_current_usage",
    "Current rate limit usage per client",
    ["client_key", "window"],
    registry=registry,
)

# Active rate limited clients gauge
rate_limit_active_clients = Gauge(
    "portkit_rate_limit_active_clients",
    "Number of unique clients currently tracked",
    registry=registry,
)

# ============================================
# Synthetic Canary Metrics (Issue #1782)
# ============================================

# Synthetic conversion success gauge (1 = success, 0 = failure)
synthetic_conversion_success = Gauge(
    "portkit_synthetic_conversion_success",
    "Synthetic conversion canary result (1=success, 0=failure)",
    registry=registry,
)

# Synthetic conversion duration gauge
synthetic_conversion_duration_seconds = Gauge(
    "portkit_synthetic_conversion_duration_seconds",
    "Duration of the synthetic conversion canary in seconds",
    registry=registry,
)

# Synthetic conversion last run timestamp
synthetic_conversion_last_run_timestamp = Gauge(
    "portkit_synthetic_conversion_last_run_timestamp",
    "Unix timestamp of the last synthetic conversion canary run",
    registry=registry,
)


# ============================================
# Authentication / Migration Metrics (Issue #1428)
# ============================================

# Counts API-key rows transparently rehashed from legacy SHA-256 / scrypt
# storage to bcrypt on first use after the #1414 / #1425 migration.
# Used to monitor migration drain — when this counter flatlines for several
# weeks, the legacy fallback in security.auth / core.auth can be removed
# (sunset target: 2026-08-13, see #1428).
legacy_api_key_rehashed_total = Counter(
    "portkit_legacy_api_key_rehashed_total",
    "API keys upgraded from legacy SHA-256/scrypt storage to bcrypt on use",
    ["old_format"],
    registry=registry,
)


# ============================================
# Internal Tracking (thread-safe)
# ============================================


class MetricsTracker:
    """Thread-safe metrics tracker for calculating rates."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._conversion_times = defaultdict(list)
        self._conversion_times_by_mod_type = defaultdict(list)
        self._success_count = 0
        self._failure_count = 0
        self._lock = threading.Lock()
        self._initialized = True

    def record_conversion(
        self,
        duration_seconds: float,
        success: bool,
        target_version: str,
        mod_type: str = "unknown",
    ):
        """Record a conversion for metrics tracking."""
        with self._lock:
            if success:
                self._success_count += 1
            else:
                self._failure_count += 1

            # Keep only last 1000 conversion times by target version
            self._conversion_times[target_version].append(duration_seconds)
            if len(self._conversion_times[target_version]) > 1000:
                self._conversion_times[target_version] = self._conversion_times[target_version][
                    -1000:
                ]

            # Keep conversion times by mod type for average by mod type tracking
            mod_type_key = f"{target_version}:{mod_type}"
            self._conversion_times_by_mod_type[mod_type_key].append(duration_seconds)
            if len(self._conversion_times_by_mod_type[mod_type_key]) > 1000:
                self._conversion_times_by_mod_type[mod_type_key] = (
                    self._conversion_times_by_mod_type[mod_type_key][-1000:]
                )

            # Update gauge metrics
            total = self._success_count + self._failure_count
            if total > 0:
                rate = (self._success_count / total) * 100
                conversion_success_rate.set(rate)

            # Calculate average conversion time
            all_times = []
            for times in self._conversion_times.values():
                all_times.extend(times)
            if all_times:
                avg_time = sum(all_times) / len(all_times)
                average_conversion_time_seconds.set(avg_time)

            # Calculate and update average conversion time by mod type
            for key, times in self._conversion_times_by_mod_type.items():
                if times:
                    parts = key.split(":", 1)
                    if len(parts) == 2:
                        tv, mt = parts
                        avg_time_mod = sum(times) / len(times)
                        average_conversion_time_by_mod_type.labels(
                            target_version=tv, mod_type=mt
                        ).set(avg_time_mod)

            # Update total counts
            conversions_completed_total.set(self._success_count)
            conversions_failed_total.set(self._failure_count)

            # Update failure rate gauge
            if total > 0:
                failure_rate = (self._failure_count / total) * 100
                conversion_failure_rate.set(failure_rate)

    def get_stats(self):
        """Get current statistics."""
        with self._lock:
            total = self._success_count + self._failure_count
            return {
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "total": total,
                "success_rate": (self._success_count / total * 100) if total > 0 else 0,
                "average_time": (
                    sum(sum(times) for times in self._conversion_times.values())
                    / sum(len(times) for times in self._conversion_times.values())
                    if sum(len(times) for times in self._conversion_times.values()) > 0
                    else 0
                ),
            }


# Global metrics tracker instance
metrics_tracker = MetricsTracker()


# ============================================
# Helper Functions
# ============================================


def record_http_request(method: str, endpoint: str, status: int, duration: float):
    """Record an HTTP request metric."""
    http_requests_total.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


def record_conversion_job(
    status: str,
    target_version: str = "1.20.0",
    mod_type: str = "unknown",
    duration: Optional[float] = None,
):
    """Record a conversion job metric.

    Args:
        status: Status of the conversion (completed, failed, pending)
        target_version: Target Minecraft version
        mod_type: Type of mod being converted (modpack, texture, schematic, etc.)
        duration: Duration of the conversion in seconds
    """
    conversion_jobs_total.labels(
        status=status, target_version=target_version, mod_type=mod_type
    ).inc()

    if duration is not None:
        conversion_duration_seconds.labels(
            target_version=target_version, mod_type=mod_type
        ).observe(duration)
        metrics_tracker.record_conversion(duration, status == "completed", target_version, mod_type)


def record_agent_execution(agent_name: str, status: str, duration: Optional[float] = None):
    """Record an agent execution metric."""
    agent_executions_total.labels(agent_name=agent_name, status=status).inc()

    if duration is not None:
        agent_duration_seconds.labels(agent_name=agent_name).observe(duration)


def record_llm_usage(model: str, prompt_tokens: int, completion_tokens: int, cost: float):
    """Record LLM token usage and cost."""
    llm_tokens_total.labels(model=model, prompt_completion="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(model=model, prompt_completion="completion").inc(completion_tokens)
    llm_cost_dollars.labels(model=model).inc(cost)


def record_asset_processed(asset_type: str, status: str, duration: Optional[float] = None):
    """Record an asset processed metric."""
    assets_processed_total.labels(asset_type=asset_type, status=status).inc()

    if duration is not None:
        asset_conversion_duration_seconds.labels(asset_type=asset_type).observe(duration)


def record_db_operation(operation: str, table: str, duration: float):
    """Record a database operation metric."""
    db_operation_duration_seconds.labels(operation=operation, table=table).observe(duration)


def record_cache_operation(operation: str, cache_name: str):
    """Record a cache operation metric."""
    cache_operations_total.labels(operation=operation, cache_name=cache_name).inc()


def update_queue_size(size: int):
    """Update the conversion queue size gauge."""
    conversion_queue_size.set(size)


def update_active_conversions(count: int):
    """Update the active conversions gauge."""
    active_conversions.set(count)


def record_error(error_category: str, error_type: str = "Exception", source: str = "unknown"):
    """
    Record an error metric.

    Args:
        error_category: Category of error (parse_error, asset_error, logic_error, etc.)
        error_type: Type of exception (ValueError, RuntimeError, etc.)
        source: Source of error (api, conversion, agent, etc.)
    """
    error_total.labels(error_category=error_category, error_type=error_type, source=source).inc()


def record_retry_attempt(error_category: str, function_name: str):
    """
    Record a retry attempt.

    Args:
        error_category: Category of error that triggered retry
        function_name: Name of function being retried
    """
    retry_attempts_total.labels(error_category=error_category, function_name=function_name).inc()


def record_successful_retry(error_category: str, function_name: str):
    """
    Record a successful retry (after initial failure).

    Args:
        error_category: Category of error that was retried
        function_name: Name of function that succeeded on retry
    """
    successful_retries_total.labels(
        error_category=error_category, function_name=function_name
    ).inc()


def record_rate_limit_hit(endpoint: str, client_type: str = "ip"):
    """
    Record a rate limit hit (request blocked).

    Args:
        endpoint: The API endpoint where rate limit was hit
        client_type: Type of client (ip, user, etc.)
    """
    rate_limit_hits_total.labels(endpoint=endpoint, client_type=client_type).inc()


def record_rate_limit_request(endpoint: str, client_type: str, allowed: bool):
    """
    Record a request processed by rate limiter.

    Args:
        endpoint: The API endpoint
        client_type: Type of client (ip, user, etc.)
        allowed: Whether the request was allowed
    """
    status = "allowed" if allowed else "blocked"
    rate_limit_requests_total.labels(
        endpoint=endpoint, client_type=client_type, status=status
    ).inc()


def update_rate_limit_usage(client_key: str, window: str, usage: int):
    """
    Update current rate limit usage for a client.

    Args:
        client_key: Unique client identifier
        window: Time window (minute, hour)
        usage: Current usage count
    """
    rate_limit_current_usage.labels(client_key=client_key, window=window).set(usage)


def update_active_rate_limit_clients(count: int):
    """
    Update the number of active rate limited clients.

    Args:
        count: Number of unique clients currently tracked
    """
    rate_limit_active_clients.set(count)


def record_legacy_api_key_rehashed(old_format: str) -> None:
    """
    Record a legacy API-key hash being upgraded to bcrypt (issue #1428).

    Args:
        old_format: The pre-migration hash format that matched — one of
            ``"sha256"`` or ``"scrypt"``. Used as the metric label so ops
            dashboards can split the migration drain by source format.
    """
    legacy_api_key_rehashed_total.labels(old_format=old_format).inc()


# ============================================
# Synthetic Canary Functions (Issue #1782)
# ============================================


def record_synthetic_conversion_run(success: bool, duration_seconds: float) -> None:
    """
    Record the result of a synthetic conversion canary run.

    Args:
        success: Whether the synthetic conversion succeeded
        duration_seconds: Duration of the conversion attempt in seconds
    """
    import time

    synthetic_conversion_success.set(1 if success else 0)
    synthetic_conversion_duration_seconds.set(duration_seconds)
    synthetic_conversion_last_run_timestamp.set(int(time.time()))


def get_metrics() -> bytes:
    """Get Prometheus metrics in text format."""
    return generate_latest(registry)


# ============================================
# Metrics Middleware for FastAPI
# ============================================


class MetricsMiddleware:
    """FastAPI middleware for recording HTTP metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract path and method
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")

        # Start timer
        start_time = time.time()

        # Custom send to capture status code
        status_code = 200

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # Calculate duration
        duration = time.time() - start_time

        # Normalize endpoint for grouping
        endpoint = self._normalize_endpoint(path)

        # Record metrics
        record_http_request(method, endpoint, status_code, duration)

    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for grouping."""
        # Convert UUIDs and IDs to placeholder
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
        )
        # Replace numeric IDs
        path = re.sub(r"/\d+", "/{id}", path)
        return path
