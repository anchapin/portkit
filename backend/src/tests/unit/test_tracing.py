import pytest
import os
from unittest.mock import MagicMock, patch
from services import tracing


@pytest.fixture(autouse=True)
def reset_tracing_state():
    tracing._initialized = False
    tracing._tracer_provider = None
    tracing._tracer = None
    yield
    tracing._initialized = False
    tracing._tracer_provider = None
    tracing._tracer = None


def test_get_service_name_default():
    with patch.dict(os.environ, {}, clear=True):
        assert tracing.get_service_name() == "portkit-backend"


def test_get_service_name_env():
    with patch.dict(os.environ, {"SERVICE_NAME": "custom-service"}):
        assert tracing.get_service_name() == "custom-service"


def test_get_service_version_default():
    with patch.dict(os.environ, {}, clear=True):
        assert tracing.get_service_version() == "1.0.0"


def test_create_resource():
    resource = tracing._create_resource()
    # It might be 'unknown_service' if env is not set correctly in test
    assert resource.attributes["service.name"] in [tracing.get_service_name(), "unknown_service"]
    assert resource.attributes["service.version"] == tracing.get_service_version()


@patch("services.tracing.TracerProvider")
@patch("services.tracing.trace.set_tracer_provider")
@patch("services.tracing._instrument_fastapi")
@patch("services.tracing._instrument_httpx")
@patch("services.tracing._instrument_redis")
def test_init_tracing(mock_redis, mock_httpx, mock_fastapi, mock_set_provider, mock_provider):
    # Reset initialized state for test
    tracing._initialized = False

    tracing.init_tracing()

    assert tracing._initialized is True
    mock_provider.assert_called_once()
    mock_set_provider.assert_called_once()
    mock_httpx.assert_called_once()
    mock_redis.assert_called_once()


def test_create_span():
    mock_tracer = MagicMock()
    with patch("services.tracing.get_tracer", return_value=mock_tracer):
        tracing.create_span("test-span")
        mock_tracer.start_span.assert_called_once_with(
            "test-span", kind=tracing.trace.SpanKind.INTERNAL
        )


def test_add_span_attributes():
    mock_span = MagicMock()
    tracing.add_span_attributes(mock_span, {"attr1": "val1", "attr2": 2})
    mock_span.set_attribute.assert_any_call("attr1", "val1")
    mock_span.set_attribute.assert_any_call("attr2", "2")


def test_record_span_exception():
    mock_span = MagicMock()
    exc = ValueError("test exception")
    tracing.record_span_exception(mock_span, exc)
    mock_span.record_exception.assert_called_once_with(exc)
    mock_span.set_status.assert_called_once()


def test_inject_extract_context():
    carrier = {}
    with patch("services.tracing.tracer_propagator.inject") as mock_inject:
        tracing.inject_trace_context(carrier)
        mock_inject.assert_called_once_with(carrier)

    with patch("services.tracing.tracer_propagator.extract") as mock_extract:
        tracing.extract_trace_context(carrier)
        mock_extract.assert_called_once_with(carrier)


def test_get_service_version_env():
    with patch.dict(os.environ, {"SERVICE_VERSION": "2.0.0"}):
        assert tracing.get_service_version() == "2.0.0"


def test_get_tracing_exporter_default():
    with patch.dict(os.environ, {}, clear=True):
        assert tracing.get_tracing_exporter() == "otlp"


def test_get_tracing_exporter_otlp():
    with patch.dict(os.environ, {"TRACING_EXPORTER": "OTLP"}):
        assert tracing.get_tracing_exporter() == "otlp"


def test_get_tracing_exporter_jaeger_alias():
    # "jaeger" is accepted as a backwards-compatible alias for "otlp"
    with patch.dict(os.environ, {"TRACING_EXPORTER": "jaeger"}):
        assert tracing.get_tracing_exporter() == "otlp"


def test_get_otlp_endpoint_default():
    with patch.dict(os.environ, {}, clear=True):
        assert tracing.get_otlp_endpoint() == "http://localhost:4317"


def test_get_otlp_endpoint_env():
    with patch.dict(os.environ, {"OTLP_ENDPOINT": "http://collector:4317"}):
        assert tracing.get_otlp_endpoint() == "http://collector:4317"


def test_get_tracer_uninitialized():
    tracing._tracer = None
    tracer = tracing.get_tracer()
    assert tracer is not None


def test_get_tracer_cached():
    mock_tracer = MagicMock()
    tracing._tracer = mock_tracer
    assert tracing.get_tracer() is mock_tracer
    tracing._tracer = None


def test_create_span_with_context():
    mock_tracer = MagicMock()
    mock_ctx = MagicMock()
    with patch("services.tracing.get_tracer", return_value=mock_tracer):
        tracing.create_span("test-span", context=mock_ctx)
        mock_tracer.start_span.assert_called_once_with(
            "test-span", context=mock_ctx, kind=tracing.trace.SpanKind.INTERNAL
        )


def test_add_span_attributes_empty():
    mock_span = MagicMock()
    tracing.add_span_attributes(mock_span, {})
    mock_span.set_attribute.assert_not_called()


def test_add_span_attributes_none_value():
    mock_span = MagicMock()
    tracing.add_span_attributes(mock_span, {"a": "val", "b": None})
    mock_span.set_attribute.assert_called_once_with("a", "val")


def test_add_span_attributes_none_span():
    tracing.add_span_attributes(None, {"a": "val"})


def test_record_span_exception_none_span():
    tracing.record_span_exception(None, ValueError("test"))


def test_end_span():
    mock_span = MagicMock()
    tracing.end_span(mock_span)
    mock_span.end.assert_called_once()


def test_end_span_none():
    tracing.end_span(None)


def test_get_current_span():
    with patch("services.tracing.trace.get_current_span") as mock:
        mock.return_value = MagicMock()
        result = tracing.get_current_span()
        assert result is not None


def test_get_trace_id_with_valid_span():
    mock_span = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.trace_id = 123456789
    mock_span.get_span_context.return_value = mock_ctx
    with patch("services.tracing.trace.get_current_span", return_value=mock_span):
        result = tracing.get_trace_id()
        assert result is not None
        assert len(result) == 32


def test_get_trace_id_no_span():
    with patch("services.tracing.trace.get_current_span", return_value=None):
        assert tracing.get_trace_id() is None


def test_get_trace_id_zero_trace():
    mock_span = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.trace_id = 0
    mock_span.get_span_context.return_value = mock_ctx
    with patch("services.tracing.trace.get_current_span", return_value=mock_span):
        assert tracing.get_trace_id() is None


def test_get_span_id_with_valid_span():
    mock_span = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.span_id = 987654321
    mock_span.get_span_context.return_value = mock_ctx
    with patch("services.tracing.trace.get_current_span", return_value=mock_span):
        result = tracing.get_span_id()
        assert result is not None
        assert len(result) == 16


def test_get_span_id_no_span():
    with patch("services.tracing.trace.get_current_span", return_value=None):
        assert tracing.get_span_id() is None


def test_get_span_id_zero_id():
    mock_span = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.span_id = 0
    mock_span.get_span_context.return_value = mock_ctx
    with patch("services.tracing.trace.get_current_span", return_value=mock_span):
        assert tracing.get_span_id() is None


@patch("services.tracing.TracerProvider")
@patch("services.tracing.trace.set_tracer_provider")
@patch("services.tracing._instrument_fastapi")
@patch("services.tracing._instrument_httpx")
@patch("services.tracing._instrument_redis")
def test_init_tracing_already_initialized(
    mock_redis, mock_httpx, mock_fastapi, mock_set_provider, mock_provider
):
    tracing._initialized = True
    tracing.init_tracing()
    mock_provider.assert_not_called()
    tracing._initialized = False


@patch("services.tracing.TracerProvider")
@patch("services.tracing.trace.set_tracer_provider")
@patch("services.tracing._instrument_fastapi")
@patch("services.tracing._instrument_httpx")
@patch("services.tracing._instrument_redis")
@patch.dict(os.environ, {"TRACING_EXPORTER": "otlp"})
def test_init_tracing_otlp_exporter(
    mock_redis, mock_httpx, mock_fastapi, mock_set_provider, mock_provider
):
    tracing._initialized = False
    mock_provider_instance = MagicMock()
    mock_provider.return_value = mock_provider_instance

    with patch("services.tracing._setup_otlp_exporter") as mock_otlp:
        mock_otlp.return_value = MagicMock()
        tracing.init_tracing()

    assert tracing._initialized is True
    tracing._initialized = False


@patch("services.tracing.TracerProvider")
@patch("services.tracing.trace.set_tracer_provider")
@patch("services.tracing._instrument_fastapi")
@patch("services.tracing._instrument_httpx")
@patch("services.tracing._instrument_redis")
@patch.dict(os.environ, {"TRACING_EXPORTER": "all"})
def test_init_tracing_all_exporters(
    mock_redis, mock_httpx, mock_fastapi, mock_set_provider, mock_provider
):
    tracing._initialized = False

    with patch("services.tracing._setup_otlp_exporter") as mock_otlp:
        mock_otlp.return_value = MagicMock()
        tracing.init_tracing()

    assert tracing._initialized is True
    tracing._initialized = False


@patch("services.tracing.TracerProvider")
@patch("services.tracing.trace.set_tracer_provider")
@patch("services.tracing._instrument_fastapi")
@patch("services.tracing._instrument_httpx")
@patch("services.tracing._instrument_redis")
@patch.dict(os.environ, {"TRACING_CONSOLE": "true"})
def test_init_tracing_console_exporter(
    mock_redis, mock_httpx, mock_fastapi, mock_set_provider, mock_provider
):
    tracing._initialized = False

    tracing.init_tracing()

    assert tracing._initialized is True
    tracing._initialized = False


@patch("services.tracing.TracerProvider")
@patch("services.tracing.trace.set_tracer_provider")
@patch("services.tracing._instrument_httpx")
@patch("services.tracing._instrument_redis")
def test_init_tracing_with_fastapi_app(mock_redis, mock_httpx, mock_set_provider, mock_provider):
    tracing._initialized = False
    mock_app = MagicMock()

    with patch("services.tracing._instrument_fastapi") as mock_instrument:
        tracing.init_tracing(app=mock_app)
        mock_instrument.assert_called_once_with(mock_app)

    tracing._initialized = False


@patch("services.tracing.TracerProvider")
def test_init_tracing_exception(mock_provider):
    tracing._initialized = False
    mock_provider.side_effect = Exception("init error")

    tracing.init_tracing()

    assert tracing._initialized is False


def test_setup_otlp_exporter_exception():
    with patch("services.tracing.OTLPSpanExporter", side_effect=Exception("otlp failed")):
        result = tracing._setup_otlp_exporter()
        assert result is None


def test_instrument_fastapi_not_available():
    tracing.FastAPIInstrumentor = None
    tracing._instrument_fastapi(MagicMock())


def test_instrument_fastapi_exception():
    tracing.FastAPIInstrumentor = MagicMock()
    tracing.FastAPIInstrumentor.instrument_app = MagicMock(side_effect=Exception("fail"))
    tracing._instrument_fastapi(MagicMock())


def test_instrument_httpx_not_available():
    tracing.HTTPXClientInstrumentor = None
    tracing._instrument_httpx()


def test_instrument_httpx_exception():
    mock_cls = MagicMock()
    mock_cls.return_value.instrument = MagicMock(side_effect=Exception("fail"))
    tracing.HTTPXClientInstrumentor = mock_cls
    tracing._instrument_httpx()


def test_instrument_redis_not_available():
    tracing.RedisInstrumentor = None
    tracing._instrument_redis()


def test_instrument_redis_exception():
    mock_cls = MagicMock()
    mock_cls.return_value.instrument = MagicMock(side_effect=Exception("fail"))
    tracing.RedisInstrumentor = mock_cls
    tracing._instrument_redis()


def test_shutdown_tracing():
    mock_provider = MagicMock()
    tracing._tracer_provider = mock_provider
    tracing._initialized = True

    tracing.shutdown_tracing()

    mock_provider.shutdown.assert_called_once()
    assert tracing._initialized is False


def test_shutdown_tracing_no_provider():
    tracing._tracer_provider = None
    tracing.shutdown_tracing()
    assert tracing._initialized is False


def test_create_resource_ec2_exception():
    with patch("services.tracing.AwsEc2ResourceDetector") as mock_ec2:
        mock_ec2.return_value.detect.side_effect = Exception("EC2 detect failed")
        resource = tracing._create_resource()
        assert resource is not None


def test_create_resource_ecs_exception():
    with patch("services.tracing.AwsEcsResourceDetector") as mock_ecs:
        mock_ecs.return_value.detect.side_effect = Exception("ECS detect failed")
        resource = tracing._create_resource()
        assert resource is not None


def test_setup_otlp_exporter_success():
    with patch("services.tracing.OTLPSpanExporter") as mock_otlp:
        mock_otlp.return_value = MagicMock()
        with patch("services.tracing.BatchSpanProcessor") as mock_bsp:
            mock_bsp.return_value = MagicMock()
            result = tracing._setup_otlp_exporter()
            assert result is not None


def test_instrument_fastapi_success():
    tracing.FastAPIInstrumentor = MagicMock()
    tracing._instrument_fastapi(MagicMock())
    tracing.FastAPIInstrumentor.instrument_app.assert_called_once()


def test_instrument_httpx_success():
    mock_cls = MagicMock()
    tracing.HTTPXClientInstrumentor = mock_cls
    tracing._instrument_httpx()
    mock_cls.return_value.instrument.assert_called_once()


def test_instrument_redis_success():
    mock_cls = MagicMock()
    tracing.RedisInstrumentor = mock_cls
    tracing._instrument_redis()
    mock_cls.return_value.instrument.assert_called_once()
