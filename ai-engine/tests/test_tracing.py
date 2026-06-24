"""Tests for the distributed tracing module.

Covers the lazy/optional Jaeger import path (issue #1781): the
``opentelemetry-exporter-jaeger`` package is deprecated and frequently
unavailable, so ``_setup_jaeger_exporter`` must never raise and must return
``None`` when the package is missing or broken.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def test_get_tracing_exporter_default_and_override():
    """Exporter selection reads TRACING_EXPORTER (default 'jaeger')."""
    import tracing

    assert tracing.get_tracing_exporter() == "jaeger"
    with patch.dict("os.environ", {"TRACING_EXPORTER": "OTLP"}):
        assert tracing.get_tracing_exporter() == "otlp"


def test_jaeger_host_port_helpers():
    """Jaeger host/port helpers honor env overrides."""
    import tracing

    with patch.dict("os.environ", {"JAEGER_HOST": "myjaeger", "JAEGER_PORT": "12345"}):
        assert tracing.get_jaeger_host() == "myjaeger"
        assert tracing.get_jaeger_port() == 12345


def test_create_resource_carries_service_metadata():
    """Resource is built from SERVICE_NAME / SERVICE_VERSION env vars."""
    import tracing

    with patch.dict("os.environ", {"SERVICE_NAME": "svc-x", "SERVICE_VERSION": "9.9"}):
        resource = tracing._create_resource()
        assert resource.attributes.get("service.name") == "svc-x"
        assert resource.attributes.get("service.version") == "9.9"


def test_setup_jaeger_exporter_returns_none_when_import_fails(monkeypatch):
    """When the jaeger package is missing/broken, return None and do not raise."""
    import tracing

    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _block_jaeger(name, *args, **kwargs):
        if "jaeger.thrift" in name:
            raise ImportError("simulated missing jaeger package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _block_jaeger)
    # Ensure no stale cached module interferes.
    monkeypatch.delitem(sys.modules, "opentelemetry.exporter.jaeger.thrift", raising=False)

    result = tracing._setup_jaeger_exporter()
    assert result is None


def test_setup_jaeger_exporter_returns_processor_when_available(monkeypatch):
    """When the jaeger package imports cleanly, a BatchSpanProcessor is returned."""
    import tracing

    fake_exporter_cls = MagicMock(name="JaegerExporter")
    fake_module = types.ModuleType("opentelemetry.exporter.jaeger.thrift")
    fake_module.JaegerExporter = fake_exporter_cls

    parent_pkg = types.ModuleType("opentelemetry.exporter.jaeger")
    parent_pkg.thrift = fake_module

    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.jaeger", parent_pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.jaeger.thrift", fake_module)

    with patch.dict("os.environ", {"JAEGER_HOST": "jh", "JAEGER_PORT": "6831"}):
        result = tracing._setup_jaeger_exporter()

    assert result is not None
    fake_exporter_cls.assert_called_once_with(agent_host_name="jh", agent_port=6831)


def test_get_tracer_returns_noop_when_uninitialized():
    """Before init_tracing, get_tracer still returns a usable (no-op) tracer."""
    import tracing

    # Reset module globals to simulate fresh process state.
    tracing._tracer = None
    tracer = tracing.get_tracer()
    assert tracer is not None


def test_create_span_and_attributes_smoke():
    """create_span + add_span_attributes run without raising on a no-op tracer."""
    import tracing

    tracing._tracer = None
    span = tracing.create_span("test-span")
    assert span is not None
    tracing.add_span_attributes(span, {"k": "v", "empty": None})
    tracing.end_span(span)
