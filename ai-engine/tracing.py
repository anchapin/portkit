"""
Distributed Tracing Service for AI Engine using OpenTelemetry.

This module provides tracing capabilities for the Portkit Engine,
including trace context propagation between services.
"""

import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

# Trace context propagator (W3C Trace Context)
tracer_propagator = TraceContextTextMapPropagator()

# Global tracer provider and tracer
_tracer_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None
_initialized: bool = False


def get_service_name() -> str:
    """Get the service name from environment or default."""
    return os.getenv("SERVICE_NAME", "portkit-ai-engine")


def get_service_version() -> str:
    """Get the service version from environment or default."""
    return os.getenv("SERVICE_VERSION", "1.0.0")


def get_tracing_exporter() -> str:
    """Get the tracing exporter type from environment.

    Defaults to ``otlp``. The deprecated ``jaeger`` value is accepted as an
    alias for ``otlp`` (Jaeger natively ingests OTLP since v1.35) so existing
    deployments keep working without configuration changes.
    """
    exporter = os.getenv("TRACING_EXPORTER", "otlp").lower()
    if exporter == "jaeger":
        logger.warning(
            "TRACING_EXPORTER=jaeger is deprecated; the Jaeger exporter has been "
            "removed in favor of OTLP (Jaeger natively accepts OTLP). "
            "Falling back to the OTLP exporter. Set TRACING_EXPORTER=otlp to silence."
        )
        return "otlp"
    return exporter


def get_otlp_endpoint() -> str:
    """Get OTLP endpoint from environment."""
    return os.getenv("OTLP_ENDPOINT", "http://localhost:4317")


def _create_resource() -> Resource:
    """Create OpenTelemetry resource with service metadata."""
    return Resource.create(
        {
            SERVICE_NAME: get_service_name(),
            SERVICE_VERSION: get_service_version(),
        }
    )


def _setup_otlp_exporter() -> Optional[BatchSpanProcessor]:
    """Setup OTLP (gRPC) exporter."""
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=get_otlp_endpoint(),
            insecure=True,
        )
        return BatchSpanProcessor(otlp_exporter)
    except Exception as e:
        logger.warning(f"Failed to setup OTLP exporter: {e}")
        return None


def init_tracing(app=None) -> None:
    """
    Initialize OpenTelemetry tracing.

    Args:
        app: Optional FastAPI app to instrument
    """
    global _tracer_provider, _tracer, _initialized

    if _initialized:
        logger.warning("Tracing already initialized")
        return

    try:
        # Create resource with service info
        resource = _create_resource()

        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)

        # Get exporter type from environment
        exporter_type = get_tracing_exporter()

        # Add exporters based on configuration
        if exporter_type in ("otlp", "all"):
            processor = _setup_otlp_exporter()
            if processor:
                _tracer_provider.add_span_processor(processor)
                logger.info(f"OTLP exporter configured: {get_otlp_endpoint()}")

        # Always add console exporter for development
        if os.getenv("TRACING_CONSOLE", "false").lower() == "true":
            _tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("Console exporter enabled")

        # Set global tracer provider
        trace.set_tracer_provider(_tracer_provider)

        # Get tracer
        _tracer = trace.get_tracer(__name__)

        # Instrument FastAPI if app provided
        if app is not None:
            _instrument_fastapi(app)

        # Instrument HTTPX client
        _instrument_httpx()

        # Instrument Redis
        _instrument_redis()

        _initialized = True
        logger.info("OpenTelemetry tracing initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")
        # Don't raise - tracing is optional


def _instrument_fastapi(app) -> None:
    """Instrument FastAPI application."""
    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument FastAPI: {e}")


def _instrument_httpx() -> None:
    """Instrument HTTPX client."""
    try:
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX client instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument HTTPX: {e}")


def _instrument_redis() -> None:
    """Instrument Redis client."""
    try:
        RedisInstrumentor().instrument()
        logger.info("Redis instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument Redis: {e}")


def get_tracer() -> trace.Tracer:
    """
    Get the configured tracer.

    Returns:
        Configured tracer instance
    """
    global _tracer

    if _tracer is None:
        # Return a no-op tracer if not initialized
        _tracer = trace.get_tracer(__name__)

    return _tracer


def create_span(
    name: str,
    context: Optional[Context] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> trace.Span:
    """
    Create a new span with the given name and context.

    Args:
        name: Name of the span
        context: Parent context (optional)
        kind: Span kind

    Returns:
        New span (not yet ended). Caller is responsible for ending the span.
    """
    tracer = get_tracer()

    if context:
        span = tracer.start_span(name, context=context, kind=kind)
    else:
        span = tracer.start_span(name, kind=kind)

    return span


def add_span_attributes(span: trace.Span, attributes: dict) -> None:
    """
    Add attributes to a span.

    Args:
        span: Span to add attributes to
        attributes: Dictionary of attributes
    """
    if span and attributes:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, str(value))


def record_span_exception(span: trace.Span, exception: Exception) -> None:
    """
    Record an exception on a span.

    Args:
        span: Span to record exception on
        exception: Exception to record
    """
    if span:
        span.set_status(Status(StatusCode.ERROR, str(exception)))
        span.record_exception(exception)


def end_span(span: trace.Span) -> None:
    """
    End a span.

    Args:
        span: Span to end
    """
    if span:
        span.end()


def inject_trace_context(carrier: dict) -> dict:
    """
    Inject trace context into a carrier for propagation.

    Args:
        carrier: Dictionary to inject trace context into

    Returns:
        Carrier with trace context
    """
    tracer_propagator.inject(carrier)
    return carrier


def extract_trace_context(carrier: dict) -> Context:
    """
    Extract trace context from a carrier.

    Args:
        carrier: Dictionary containing trace context

    Returns:
        Extracted context
    """
    return tracer_propagator.extract(carrier)


def get_current_span() -> Optional[trace.Span]:
    """
    Get the current active span if any.

    Returns:
        Current span or None
    """
    return trace.get_current_span()


def get_trace_id() -> Optional[str]:
    """
    Get the current trace ID as a hex string.

    Returns:
        Trace ID or None if no valid span
    """
    span = get_current_span()
    if span:
        span_context = span.get_span_context()
        if span_context.trace_id != 0:
            return format(span_context.trace_id, "032x")
    return None


def get_span_id() -> Optional[str]:
    """
    Get the current span ID as a hex string.

    Returns:
        Span ID or None if no valid span
    """
    span = get_current_span()
    if span:
        span_context = span.get_span_context()
        if span_context.span_id != 0:
            return format(span_context.span_id, "016x")
    return None


def shutdown_tracing() -> None:
    """Shutdown the tracing provider."""
    global _tracer_provider, _initialized

    if _tracer_provider:
        _tracer_provider.shutdown()
        _initialized = False
        logger.info("Tracing provider shutdown")
