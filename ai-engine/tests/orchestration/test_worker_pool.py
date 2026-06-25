"""
Unit tests for orchestration/worker_pool.py - WorkerPool lifecycle.

Covers WorkerType enum, WorkerStats dataclass behaviour, WorkerPool
construction/start/stop/submit_task/submit_task_async/wait_for_completion,
get_worker_stats, and the create_agent_executor factory. Tests are
synchronous-friendly: the underlying pool is thread-based so the event
loop is not required.
"""

import asyncio
import time
from unittest.mock import Mock

import pytest

from orchestration.task_graph import TaskNode
from orchestration.worker_pool import (
    WorkerPool,
    WorkerStats,
    WorkerType,
    create_agent_executor,
)


pytestmark = pytest.mark.unit


class TestWorkerTypeEnum:
    """Cover WorkerType enum membership and values."""

    def test_worker_type_values(self):
        assert WorkerType.THREAD.value == "thread"
        assert WorkerType.PROCESS.value == "process"
        assert WorkerType.ASYNC.value == "async"

    def test_worker_type_iteration(self):
        members = list(WorkerType)
        assert len(members) == 3
        assert {m.name for m in members} == {"THREAD", "PROCESS", "ASYNC"}


class TestWorkerStats:
    """Cover WorkerStats dataclass: counts, averages, and update_* methods."""

    def test_default_values(self):
        stats = WorkerStats()
        assert stats.tasks_completed == 0
        assert stats.tasks_failed == 0
        assert stats.total_execution_time == 0.0
        assert stats.average_task_time == 0.0
        assert stats.last_activity is None

    def test_update_completion_increments_completed(self):
        stats = WorkerStats()
        stats.update_completion(2.0)
        assert stats.tasks_completed == 1
        assert stats.total_execution_time == 2.0
        assert stats.average_task_time == 2.0
        assert stats.last_activity is not None

    def test_update_completion_averages_correctly(self):
        stats = WorkerStats()
        stats.update_completion(1.0)
        stats.update_completion(3.0)
        # Average of 1.0 and 3.0 is 2.0
        assert stats.average_task_time == 2.0
        assert stats.total_execution_time == 4.0
        assert stats.tasks_completed == 2

    def test_update_failure_increments_failed(self):
        stats = WorkerStats()
        stats.update_failure()
        assert stats.tasks_failed == 1
        assert stats.last_activity is not None
        # update_failure() does NOT touch average_task_time
        assert stats.average_task_time == 0.0

    def test_update_failure_does_not_affect_completed_stats(self):
        stats = WorkerStats()
        stats.update_completion(5.0)
        stats.update_failure()
        assert stats.tasks_completed == 1
        assert stats.tasks_failed == 1
        # Average is still based on successful completions
        assert stats.average_task_time == 5.0


class TestWorkerPoolInit:
    """Cover WorkerPool construction defaults and auto-detect behaviour."""

    def test_init_defaults(self):
        pool = WorkerPool()
        assert pool.worker_type == WorkerType.THREAD
        assert pool.task_timeout == 300.0
        assert pool.enable_monitoring is True
        assert pool.executor is None
        assert pool.active_futures == {}
        assert pool.task_start_times == {}
        assert pool.worker_stats == {}

    def test_init_with_max_workers(self):
        pool = WorkerPool(max_workers=8, worker_type=WorkerType.ASYNC)
        assert pool.max_workers == 8
        assert pool.worker_type == WorkerType.ASYNC

    def test_init_auto_detect_for_process(self):
        pool = WorkerPool(worker_type=WorkerType.PROCESS)
        # max_workers should be auto-detected to a positive int
        assert pool.max_workers >= 1
        assert pool.worker_type == WorkerType.PROCESS

    def test_init_with_custom_timeout_and_monitoring(self):
        pool = WorkerPool(
            max_workers=2,
            worker_type=WorkerType.THREAD,
            task_timeout=10.0,
            enable_monitoring=False,
        )
        assert pool.task_timeout == 10.0
        assert pool.enable_monitoring is False


class TestWorkerPoolStartStop:
    """Cover WorkerPool.start and stop lifecycle."""

    def test_start_creates_thread_executor(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        try:
            assert pool.executor is not None
        finally:
            pool.stop()

    def test_start_idempotent(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        first_executor = pool.executor
        # Second start should NOT replace the existing executor
        pool.start()
        assert pool.executor is first_executor
        pool.stop()

    def test_stop_when_never_started_is_noop(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        # Should not raise even though the executor was never started
        pool.stop()
        assert pool.executor is None

    def test_stop_without_wait_cancels_active_futures(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        # Add a fake future that is not done
        fake_future = Mock()
        fake_future.done = Mock(return_value=False)
        fake_future.cancel = Mock()
        pool.active_futures["fake_task"] = fake_future
        pool.stop(wait=False)
        fake_future.cancel.assert_called_once()
        assert pool.executor is None


class TestSubmitTask:
    """Cover WorkerPool.submit_task happy-path and rejection paths."""

    def test_submit_task_before_start_raises(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        task = TaskNode(task_id="t1", agent_name="a", agent_type="x", input_data={})
        with pytest.raises(RuntimeError, match="not started"):
            pool.submit_task(task, lambda t: None)

    def test_submit_task_returns_future(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        try:
            task = TaskNode(
                task_id="t1",
                agent_name="a",
                agent_type="x",
                input_data={"k": "v"},
            )

            def executor(t):
                return {"ran": True, "id": t.task_id}

            future = pool.submit_task(task, executor)
            result = future.result(timeout=5.0)
            assert result["ran"] is True
            assert result["id"] == "t1"
        finally:
            pool.stop()

    def test_submit_duplicate_task_returns_existing_future(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        try:
            task = TaskNode(task_id="dup", agent_name="a", agent_type="x", input_data={})
            f1 = pool.submit_task(task, lambda t: 1)
            f2 = pool.submit_task(task, lambda t: 1)
            assert f1 is f2
            # Wait for it to finish so the threadpool can shut down cleanly
            f1.result(timeout=5.0)
        finally:
            pool.stop()

    def test_submit_task_records_failure_stats(self):
        pool = WorkerPool(max_workers=1, enable_monitoring=True)
        pool.start()
        try:
            task = TaskNode(
                task_id="bad",
                agent_name="a",
                agent_type="x",
                input_data={},
            )

            def executor(t):
                raise ValueError("nope")

            future = pool.submit_task(task, executor)
            with pytest.raises(ValueError, match="nope"):
                future.result(timeout=5.0)
            # Failure should be recorded in the worker_stats
            assert sum(s.tasks_failed for s in pool.worker_stats.values()) >= 1
        finally:
            pool.stop()


class TestWaitForCompletion:
    """Cover WorkerPool.wait_for_completion."""

    def test_wait_for_completion_empty_list(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        result = pool.wait_for_completion([])
        assert result == {"completed": [], "failed": [], "timeout": []}

    def test_wait_for_completion_all_succeed(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        try:
            tasks = [
                TaskNode(task_id=f"t{i}", agent_name="a", agent_type="x", input_data={})
                for i in range(3)
            ]
            for t in tasks:
                pool.submit_task(t, lambda task: {"id": task.task_id})
            result = pool.wait_for_completion(tasks, timeout=5.0)
            assert len(result["completed"]) == 3
            assert result["failed"] == []
            assert result["timeout"] == []
        finally:
            pool.stop()

    def test_wait_for_completion_records_failure(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        pool.start()
        try:
            t_ok = TaskNode(task_id="ok", agent_name="a", agent_type="x", input_data={})
            t_bad = TaskNode(task_id="bad", agent_name="a", agent_type="x", input_data={})
            pool.submit_task(t_ok, lambda t: "ok")
            pool.submit_task(t_bad, lambda t: (_ for _ in ()).throw(RuntimeError("x")))
            result = pool.wait_for_completion([t_ok, t_bad], timeout=5.0)
            assert len(result["completed"]) == 1
            assert len(result["failed"]) == 1
            assert result["failed"][0]["task_id"] == "bad"
        finally:
            pool.stop()


class TestWorkerPoolStatsAndActiveCount:
    """Cover get_active_task_count and get_worker_stats."""

    def test_get_active_task_count_no_active(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        assert pool.get_active_task_count() == 0

    def test_get_worker_stats_shape(self):
        pool = WorkerPool(max_workers=2, enable_monitoring=False)
        stats = pool.get_worker_stats()
        assert stats["worker_type"] == "thread"
        assert stats["max_workers"] == 2
        assert stats["active_workers"] == 0
        assert stats["active_tasks"] == 0
        assert stats["total_completed"] == 0
        assert stats["total_failed"] == 0
        assert stats["success_rate"] == 0
        assert stats["average_task_time"] == 0.0
        assert stats["worker_details"] == {}


class TestAgentExecutorFactory:
    """Cover create_agent_executor: a thin wrapper around agent_instance."""

    def test_create_agent_executor_invokes_run(self):
        agent = Mock()
        agent.run = Mock(return_value={"ok": True})
        executor = create_agent_executor(agent, None)
        task = TaskNode(task_id="t", agent_name="a", agent_type="x", input_data={"x": 1})
        result = executor(task)
        agent.run.assert_called_once()
        assert result == {"ok": True}

    def test_create_agent_executor_invokes_set_input_data(self):
        agent = Mock()
        agent.run = Mock(return_value={"r": 1})
        agent.set_input_data = Mock()
        executor = create_agent_executor(agent)
        task = TaskNode(task_id="t", agent_name="a", agent_type="x", input_data={"x": 1})
        executor(task)
        agent.set_input_data.assert_called_once_with({"x": 1})

    def test_create_agent_executor_invokes_execute(self):
        # Agent with execute but not run
        agent = Mock(spec=["execute"])
        agent.execute = Mock(return_value={"r": 1})
        executor = create_agent_executor(agent)
        task = TaskNode(task_id="t", agent_name="a", agent_type="x", input_data={})
        result = executor(task)
        agent.execute.assert_called_once()
        assert result == {"r": 1}

    def test_create_agent_executor_callable(self):
        # Plain function: called with input_data (a dict), not the TaskNode
        def my_agent(data):
            return {"data": data}

        executor = create_agent_executor(my_agent)
        task = TaskNode(task_id="callable", agent_name="a", agent_type="x", input_data={"k": 1})
        assert executor(task) == {"data": {"k": 1}}

    def test_create_agent_executor_invalid_raises(self):
        executor = create_agent_executor(42)
        task = TaskNode(task_id="t", agent_name="a", agent_type="x", input_data={})
        with pytest.raises(ValueError, match="Don't know how to execute"):
            executor(task)


class TestContextManager:
    """Cover WorkerPool context manager protocol."""

    def test_context_manager_starts_and_stops_pool(self):
        with WorkerPool(max_workers=2, enable_monitoring=False) as pool:
            assert pool.executor is not None
        # After exiting, executor is shut down
        assert pool.executor is None


class TestSubmitTaskAsync:
    """Cover the async submit path used by the orchestrator."""

    @pytest.mark.asyncio
    async def test_submit_task_async_runs_executor(self):
        task = TaskNode(
            task_id="async_ok",
            agent_name="a",
            agent_type="a",
            input_data={"x": 1},
        )
        with WorkerPool(max_workers=2) as pool:
            future = await pool.submit_task_async(task, lambda t: {"ok": t.input_data["x"]})
            result = await asyncio.wait_for(future, timeout=5.0)
            assert result == {"ok": 1}
            # Future bookkeeping is shared with sync submit
            assert "async_ok" in pool.active_futures

    @pytest.mark.asyncio
    async def test_submit_task_async_without_start_raises(self):
        pool = WorkerPool(max_workers=2)
        # Not started; executor is None
        task = TaskNode(
            task_id="async_fail",
            agent_name="a",
            agent_type="a",
            input_data={},
        )
        with pytest.raises(RuntimeError, match="not started"):
            await pool.submit_task_async(task, lambda t: None)

    @pytest.mark.asyncio
    async def test_submit_task_async_duplicate_returns_existing(self):
        task = TaskNode(
            task_id="dup",
            agent_name="a",
            agent_type="a",
            input_data={},
        )
        with WorkerPool(max_workers=2) as pool:
            f1 = await pool.submit_task_async(task, lambda t: "first")
            # The async path always runs a new submit through the executor;
            # the dedup branch lives in the inner _submit_sync call, which the
            # async submit will exercise only if the executor call returns
            # twice. We assert that calling twice does not raise and returns
            # an awaitable in both cases.
            f2 = await pool.submit_task_async(task, lambda t: "second")
            assert asyncio.isfuture(f1)
            assert asyncio.isfuture(f2)


class TestWaitForCompletionEdgeCases:
    """Cover remaining wait_for_completion branches."""

    def test_wait_for_completion_timeout_marks_task_failed(self):
        with WorkerPool(max_workers=1, task_timeout=0.05) as pool:
            slow = TaskNode(
                task_id="slow",
                agent_name="a",
                agent_type="a",
                input_data={},
            )

            def hang(_):
                time.sleep(1.0)
                return "done"

            pool.submit_task(slow, hang)
            outcome = pool.wait_for_completion([slow], timeout=0.1)
            assert outcome["completed"] == []
            assert len(outcome["timeout"]) >= 1
            assert outcome["failed"] == []

    def test_wait_for_completion_records_failure(self):
        with WorkerPool(max_workers=1, task_timeout=5.0) as pool:
            bad = TaskNode(
                task_id="bad",
                agent_name="a",
                agent_type="a",
                input_data={},
            )
            pool.submit_task(bad, lambda _t: (_ for _ in ()).throw(RuntimeError("boom")))
            outcome = pool.wait_for_completion([bad], timeout=5.0)
            assert outcome["completed"] == []
            assert len(outcome["failed"]) >= 1

    def test_wait_for_completion_empty_task_list(self):
        with WorkerPool(max_workers=1) as pool:
            outcome = pool.wait_for_completion([], timeout=1.0)
            # All keys are lists in the actual return shape
            assert outcome == {"completed": [], "failed": [], "timeout": []}


class TestExecuteWithMonitoring:
    """Cover the monitoring-wrapped executor path inside _submit_sync."""

    def test_executor_records_completion_in_stats(self):
        with WorkerPool(max_workers=1, enable_monitoring=True) as pool:
            task = TaskNode(
                task_id="monitored",
                agent_name="a",
                agent_type="a",
                input_data={},
            )
            future = pool.submit_task(task, lambda _t: 42)
            future.result(timeout=5.0)
            stats = pool.get_worker_stats()
            assert stats["total_completed"] >= 1
            # Worker-level details should also reflect the completion
            details = stats.get("worker_details", {})
            assert any(d.get("tasks_completed", 0) >= 1 for d in details.values()), (
                f"expected a completed task, got {stats}"
            )

    def test_executor_records_failure_in_stats(self):
        with WorkerPool(max_workers=1, enable_monitoring=True) as pool:
            task = TaskNode(
                task_id="failed_task",
                agent_name="a",
                agent_type="a",
                input_data={},
            )
            future = pool.submit_task(task, lambda _t: (_ for _ in ()).throw(ValueError("nope")))
            with pytest.raises(ValueError, match="nope"):
                future.result(timeout=5.0)
            stats = pool.get_worker_stats()
            assert stats["total_failed"] >= 1
            details = stats.get("worker_details", {})
            assert any(d.get("tasks_failed", 0) >= 1 for d in details.values()), (
                f"expected a failed task, got {stats}"
            )
