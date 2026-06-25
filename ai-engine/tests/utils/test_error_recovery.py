"""
Unit tests for utils/error_recovery.py - retry, circuit breaker, recovery system.

Covers RecoveryStrategy.delay math, CircuitBreaker state transitions
(CLOSED -> OPEN -> HALF_OPEN -> CLOSED), the with_retry decorator,
and the ErrorRecoverySystem.
"""

import threading
import time

import pytest

from utils.error_recovery import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    ErrorRecoverySystem,
    ErrorSeverity,
    RecoveryError,
    RecoveryStrategy,
    STANDARD_RETRY,
    get_recovery_system,
    with_circuit_breaker,
    with_retry,
)


pytestmark = pytest.mark.unit


class TestErrorSeverity:
    """Cover the ErrorSeverity enum members."""

    def test_values(self):
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"


class TestRecoveryStrategy:
    """Cover the RecoveryStrategy dataclass and its delay calculation."""

    def test_get_delay_grows_with_attempts(self):
        strat = RecoveryStrategy(
            name="t",
            max_retries=5,
            base_delay=1.0,
            max_delay=100.0,
            backoff_factor=2.0,
            jitter=False,
        )
        d0 = strat.get_delay(0)
        d1 = strat.get_delay(1)
        d2 = strat.get_delay(2)
        assert d0 < d1 < d2
        assert d0 == 1.0
        assert d1 == 2.0
        assert d2 == 4.0

    def test_get_delay_caps_at_max_delay(self):
        strat = RecoveryStrategy(
            name="t",
            max_retries=10,
            base_delay=10.0,
            max_delay=50.0,
            backoff_factor=2.0,
            jitter=False,
        )
        # 10 * 2**10 = 10240, capped at 50
        assert strat.get_delay(10) == 50.0

    def test_get_delay_jitter_within_ten_percent(self):
        strat = RecoveryStrategy(
            name="t",
            max_retries=1,
            base_delay=10.0,
            max_delay=100.0,
            backoff_factor=1.0,
            jitter=True,
        )
        for _ in range(20):
            d = strat.get_delay(0)
            assert 9.0 <= d <= 11.0


class TestCircuitBreaker:
    """Cover the CircuitBreaker state machine."""

    def test_starts_closed(self):
        cb = CircuitBreaker(name="t", fail_max=3)
        assert cb.state == CircuitState.CLOSED

    def test_successful_call_returns_result(self):
        cb = CircuitBreaker(name="t", fail_max=2)
        assert cb.call(lambda: 42) == 42
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_fail_max_failures(self):
        cb = CircuitBreaker(name="t", fail_max=2)
        for _ in range(2):
            with pytest.raises(RuntimeError, match="boom"):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_rejects_calls(self):
        cb = CircuitBreaker(name="t", fail_max=1, reset_timeout=60.0)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "never")

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="t", fail_max=1, reset_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert cb.state == CircuitState.OPEN
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(name="t", fail_max=1, reset_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        time.sleep(0.1)
        assert cb.call(lambda: "ok") == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(name="t", fail_max=1, reset_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        time.sleep(0.1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("still bad")))
        assert cb.state == CircuitState.OPEN

    def test_half_open_max_calls_rejects_extras(self):
        cb = CircuitBreaker(name="t", fail_max=1, reset_timeout=0.05, half_open_max_calls=1)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        time.sleep(0.1)
        # First call in HALF_OPEN is allowed (but slow)
        # Use a thread to keep the call pending
        started = threading.Event()

        def slow():
            started.set()
            time.sleep(0.5)
            return "ok"

        # Submit the slow call on a thread; while it is running, the next
        # call must be rejected because half_open_max_calls == 1.
        import threading as _t

        fut_holder = {}

        def runner():
            fut_holder["fut"] = cb.call(slow)

        th = _t.Thread(target=runner, daemon=True)
        th.start()
        started.wait(1.0)
        # Give the breaker a moment to increment _half_open_calls
        time.sleep(0.05)
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "rejected")
        # Let the original call finish
        th.join(timeout=2.0)

    def test_get_stats(self):
        cb = CircuitBreaker(name="mycb", fail_max=5)
        cb.call(lambda: 1)
        stats = cb.get_stats()
        assert stats["name"] == "mycb"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["success_count"] >= 1


class TestWithRetryDecorator:
    """Cover the with_retry decorator."""

    def test_succeeds_on_first_try(self):
        @with_retry(STANDARD_RETRY)
        def good():
            return "ok"

        assert good() == "ok"

    def test_retries_on_retryable_exception_then_succeeds(self):
        attempts = {"n": 0}

        @with_retry(
            RecoveryStrategy(
                name="t",
                max_retries=3,
                base_delay=0.001,
                max_delay=0.01,
                backoff_factor=1.0,
                jitter=False,
                retryable_exceptions=[ValueError],
            )
        )
        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("not yet")
            return "ok"

        assert flaky() == "ok"
        assert attempts["n"] == 3

    def test_non_retryable_exception_reraises(self):
        attempts = {"n": 0}

        @with_retry(
            RecoveryStrategy(
                name="t",
                max_retries=3,
                base_delay=0.001,
                max_delay=0.01,
                backoff_factor=1.0,
                jitter=False,
                retryable_exceptions=[ValueError],
            )
        )
        def bad():
            attempts["n"] += 1
            raise KeyError("nope")

        with pytest.raises(KeyError, match="nope"):
            bad()
        assert attempts["n"] == 1

    def test_exhausts_retries_raises_recovery_error(self):
        @with_retry(
            RecoveryStrategy(
                name="t",
                max_retries=2,
                base_delay=0.001,
                max_delay=0.01,
                backoff_factor=1.0,
                jitter=False,
                retryable_exceptions=[ValueError],
            )
        )
        def always_bad():
            raise ValueError("nope")

        with pytest.raises(RecoveryError, match="Failed after 2 retries"):
            always_bad()


class TestWithCircuitBreakerDecorator:
    """Cover the with_circuit_breaker decorator."""

    def test_creates_circuit_breaker_attribute(self):
        @with_circuit_breaker("api_call", fail_max=2)
        def call_api():
            return "ok"

        assert isinstance(call_api.circuit_breaker, CircuitBreaker)
        assert call_api.circuit_breaker.name == "api_call"
        assert call_api() == "ok"

    def test_uses_function_name_when_no_name(self):
        @with_circuit_breaker(fail_max=2)
        def my_endpoint():
            return "ok"

        assert my_endpoint.circuit_breaker.name == "my_endpoint"


class TestErrorRecoverySystem:
    """Cover the centralized error recovery system."""

    def test_initializes_default_strategies(self):
        sys = ErrorRecoverySystem()
        assert "network" in sys.recovery_strategies
        assert "llm_api" in sys.recovery_strategies
        assert "file_io" in sys.recovery_strategies

    def test_register_and_get_circuit_breaker(self):
        sys = ErrorRecoverySystem()
        cb = sys.register_circuit_breaker("api1", fail_max=2)
        assert cb is sys.get_circuit_breaker("api1")
        assert sys.get_circuit_breaker("missing") is None

    def test_execute_with_recovery_succeeds(self):
        sys = ErrorRecoverySystem()
        assert sys.execute_with_recovery("op", lambda: 42) == 42

    def test_execute_with_recovery_eventually_raises(self):
        sys = ErrorRecoverySystem()
        # Patch the LLM strategy to use no retries / no backoff so the
        # test runs fast.
        sys.recovery_strategies["llm_api"] = RecoveryStrategy(
            name="t",
            max_retries=0,
            base_delay=0.0,
            max_delay=0.0,
            backoff_factor=1.0,
            jitter=False,
        )
        with pytest.raises(RecoveryError, match="op failed"):
            sys.execute_with_recovery("op", lambda: (_ for _ in ()).throw(RuntimeError("bad")))

    def test_get_all_stats_with_no_breakers(self):
        sys = ErrorRecoverySystem()
        stats = sys.get_all_stats()
        assert "circuit_breakers" in stats
        assert "recovery_strategies" in stats
        assert stats["circuit_breakers"] == {}

    def test_get_all_stats_with_breakers(self):
        sys = ErrorRecoverySystem()
        sys.register_circuit_breaker("api1", fail_max=3)
        sys.register_circuit_breaker("api2", fail_max=5)
        stats = sys.get_all_stats()
        assert "api1" in stats["circuit_breakers"]
        assert "api2" in stats["circuit_breakers"]


class TestGetRecoverySystem:
    """Cover the global recovery system singleton accessor."""

    def test_returns_singleton(self):
        a = get_recovery_system()
        b = get_recovery_system()
        assert a is b
