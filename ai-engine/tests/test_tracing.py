"""Tests for the distributed tracing module.

Covers the OTLP exporter migration (issue #1821): the deprecated
``opentelemetry-exporter-jaeger`` package has been removed in favor of
``opentelemetry-exporter-otlp`` (Jaeger natively ingests OTLP since v1.35).
The ``TRACING_EXPORTER=jaeger`` value is accepted as a backwards-compatible
alias for ``otlp``.
"""

from unittest.mock import MagicMock, patch


def test_get_tracing_exporter_default_is_otlp():
    """Exporter selection defaults to 'otlp'."""
    import tracing

    with patch.dict("os.environ", {}, clear=True):
        assert tracing.get_tracing_exporter() == "otlp"


def test_get_tracing_exporter_jaeger_alias():
    """'jaeger' is accepted as a backwards-compatible alias for 'otlp'."""
    import tracing

    with patch.dict("os.environ", {"TRACING_EXPORTER": "jaeger"}):
        assert tracing.get_tracing_exporter() == "otlp"


def test_get_otlp_endpoint_default_and_override():
    """OTLP endpoint honors OTLP_ENDPOINT env var."""
    import tracing

    with patch.dict("os.environ", {}, clear=True):
        assert tracing.get_otlp_endpoint() == "http://localhost:4317"
    with patch.dict("os.environ", {"OTLP_ENDPOINT": "http://collector:4317"}):
        assert tracing.get_otlp_endpoint() == "http://collector:4317"


def test_create_resource_carries_service_metadata():
    """Resource is built from SERVICE_NAME / SERVICE_VERSION env vars."""
    import tracing

    with patch.dict("os.environ", {"SERVICE_NAME": "svc-x", "SERVICE_VERSION": "9.9"}):
        resource = tracing._create_resource()
        assert resource.attributes.get("service.name") == "svc-x"
        assert resource.attributes.get("service.version") == "9.9"


def test_setup_otlp_exporter_returns_processor():
    """_setup_otlp_exporter returns a BatchSpanProcessor wrapping OTLPSpanExporter."""
    import tracing

    with patch("tracing.OTLPSpanExporter") as mock_otlp, patch(
        "tracing.BatchSpanProcessor"
    ) as mock_bsp:
        mock_otlp.return_value = MagicMock(name="exporter")
        mock_bsp.return_value = MagicMock(name="processor")
        result = tracing._setup_otlp_exporter()

    assert result is not None
    mock_otlp.assert_called_once()
    mock_bsp.assert_called_once()


def test_setup_otlp_exporter_returns_none_on_failure():
    """When OTLPSpanExporter raises, _setup_otlp_exporter returns None and does not propagate."""
    import tracing

    with patch("tracing.OTLPSpanExporter", side_effect=Exception("otlp failed")):
        result = tracing._setup_otlp_exporter()

    assert result is None


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

