"""
Unit tests for WorkerPool and WorkerStats.
"""

import pytest
import time
from unittest.mock import MagicMock, patch, Mock
from orchestration.worker_pool import WorkerPool, WorkerStats, WorkerType, create_agent_executor, setup_signal_handlers
from orchestration.task_graph import TaskNode

class TestWorkerStats:
    def test_update_stats(self):
        stats = WorkerStats()
        stats.update_completion(1.0)
        assert stats.tasks_completed == 1
        assert stats.total_execution_time == 1.0
        assert stats.average_task_time == 1.0
        assert stats.last_activity is not None
        
        stats.update_failure()
        assert stats.tasks_failed == 1

class TestWorkerPool:
    @pytest.fixture
    def pool(self):
        return WorkerPool(max_workers=2)

    def test_initialization_auto_workers(self):
        with patch('multiprocessing.cpu_count', return_value=4):
            pool = WorkerPool(worker_type=WorkerType.PROCESS)
            assert pool.max_workers == 4
            
            thread_pool = WorkerPool(worker_type=WorkerType.THREAD)
            assert thread_pool.max_workers == 8 # 4 + 4

    def test_start_stop(self):
        pool = WorkerPool(max_workers=2)
        pool.start()
        assert pool.executor is not None
        pool.stop()
        assert pool.executor is None

    def test_start_already_started(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        with patch('logging.Logger.warning') as mock_log:
            pool.start()
            assert mock_log.called
        pool.stop()

    def test_submit_task(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        task = TaskNode("t1", "a", "t", {})
        executor = MagicMock(return_value="ok")
        
        future = pool.submit_task(task, executor)
        assert "t1" in pool.active_futures
        assert future.result() == "ok"
        pool.stop()

    def test_submit_task_duplicate(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        task = TaskNode("t1", "a", "t", {})
        pool.submit_task(task, lambda x: "ok")
        with patch('logging.Logger.warning') as mock_log:
            pool.submit_task(task, lambda x: "ok")
            assert mock_log.called
        pool.stop()

    def test_submit_task_not_started(self):
        pool = WorkerPool()
        with pytest.raises(RuntimeError, match="not started"):
            pool.submit_task(TaskNode("t", "a", "t", {}), lambda x: "ok")

    def test_wait_for_completion(self):
        pool = WorkerPool(max_workers=2)
        pool.start()
        t1 = TaskNode("t1", "a", "t", {})
        pool.submit_task(t1, lambda x: "res1")
        
        results = pool.wait_for_completion([t1])
        assert len(results["completed"]) == 1
        assert results["completed"][0]["task_id"] == "t1"
        pool.stop()

    def test_wait_for_completion_empty(self):
        pool = WorkerPool()
        assert pool.wait_for_completion([]) == {"completed": [], "failed": [], "timeout": []}

    def test_wait_for_completion_timeout(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        t1 = TaskNode("t1", "a", "t", {})
        
        def slow_task(x):
            time.sleep(0.2)
            return "ok"
            
        pool.submit_task(t1, slow_task)
        results = pool.wait_for_completion([t1], timeout=0.01)
        assert "t1" in results["timeout"]
        pool.stop()

    def test_get_worker_stats(self):
        pool = WorkerPool(max_workers=1)
        pool.worker_stats[123] = WorkerStats(tasks_completed=1, total_execution_time=5.0)
        stats = pool.get_worker_stats()
        assert stats["total_completed"] == 1
        assert stats["average_task_time"] == 5.0

    def test_monitor_thread(self):
        pool = WorkerPool(max_workers=1, enable_monitoring=True)
        # Mock shutdown_event.wait to return True immediately to exit loop
        pool.shutdown_event.wait = MagicMock(return_value=True)
        pool._monitor_workers() # Should run once and exit
        assert pool.shutdown_event.wait.called

    def test_start_process_pool(self):
        with patch('multiprocessing.cpu_count', return_value=2), \
             patch('orchestration.pool.worker_pool.ProcessPoolExecutor') as mock_exec:
            pool = WorkerPool(max_workers=2, worker_type=WorkerType.PROCESS)
            pool.start()
            assert mock_exec.called
            pool.stop()

    def test_stop_no_wait(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        task = TaskNode("t1", "a", "t", {})
        # Mock a future that is not done
        mock_future = MagicMock()
        mock_future.done.return_value = False
        pool.active_futures["t1"] = mock_future
        
        pool.stop(wait=False)
        assert mock_future.cancel.called

    def test_stop_fallback_shutdown(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        # Simulate old python where shutdown doesn't take timeout
        pool.executor.shutdown = MagicMock(side_effect=[TypeError("unexpected arg"), None])
        pool.stop(timeout=10.0)
        assert pool.executor is None

    def test_submit_task_execution_failure(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        task = TaskNode("t1", "a", "t", {})
        executor = MagicMock(side_effect=Exception("Execution crash"))
        
        future = pool.submit_task(task, executor)
        with pytest.raises(Exception, match="Execution crash"):
            future.result()
        
        # Verify stats updated for failure
        stats = pool.get_worker_stats()
        assert stats["total_failed"] == 1
        pool.stop()

    def test_wait_for_completion_task_failure(self):
        pool = WorkerPool(max_workers=1)
        pool.start()
        t1 = TaskNode("t1", "a", "t", {})
        pool.submit_task(t1, MagicMock(side_effect=Exception("Fail")))
        
        results = pool.wait_for_completion([t1])
        assert len(results["failed"]) == 1
        assert "Fail" in results["failed"][0]["error"]
        pool.stop()

    def test_monitor_thread_logging(self):
        pool = WorkerPool(max_workers=1, enable_monitoring=True)
        pool.worker_stats[1] = WorkerStats(tasks_completed=1)
        pool.shutdown_event.wait = MagicMock(side_effect=[False, True]) # Run once then exit
        
        with patch('logging.Logger.info') as mock_log:
            pool._monitor_workers()
            assert any("WorkerPool stats" in call[0][0] for call in mock_log.call_args_list)

    def test_wait_for_completion_multiple(self, pool):
        pool.start()
        t1 = TaskNode("t1", "a", "t", {})
        t2 = TaskNode("t2", "a", "t", {})
        pool.submit_task(t1, lambda x: "r1")
        pool.submit_task(t2, lambda x: "r2")
        
        results = pool.wait_for_completion([t1, t2])
        assert len(results["completed"]) == 2
        pool.stop()

    def test_initialization_cpu_count_none(self):
        with patch('multiprocessing.cpu_count', return_value=None):
            pool = WorkerPool(worker_type=WorkerType.PROCESS)
            # Default fallback should handle None (though code might crash if not careful)
            # Let's check how it handles it
            assert pool.max_workers is not None

    def test_wait_for_completion_unknown_future(self, pool):
        pool.start()
        t1 = TaskNode("t1", "a", "t", {})
        pool.submit_task(t1, lambda x: "ok")
        
        # Mock as_completed to return a future not in our list
        mock_future = MagicMock()
        with patch('orchestration.pool.worker_pool.as_completed', return_value=[mock_future]):
            results = pool.wait_for_completion([t1], timeout=0.1)
            # Should continue loop and handle it
            assert len(results["completed"]) == 0
        pool.stop()

    def test_monitor_thread_exception(self):
        pool = WorkerPool(enable_monitoring=True)
        # Force exception in get_worker_stats
        pool.get_worker_stats = MagicMock(side_effect=Exception("Stats fail"))
        pool.shutdown_event.wait = MagicMock(side_effect=[False, True])
        
        with patch('logging.Logger.error') as mock_log:
            pool._monitor_workers()
            assert mock_log.called
            assert "Error in worker monitoring" in mock_log.call_args[0][0]

    def test_setup_signal_handlers_trigger(self, pool):
        with patch('signal.signal') as mock_signal, \
             patch('sys.exit') as mock_exit, \
             patch.object(pool, 'stop') as mock_stop:
            setup_signal_handlers(pool)
            
            # Get the handler function for SIGINT
            handler = mock_signal.call_args_list[0][0][1]
            handler(None, None)
            
            assert mock_stop.called
            assert mock_exit.called

class TestAgentExecutor:
    def test_create_agent_executor_set_input(self):
        agent = MagicMock()
        executor = create_agent_executor(agent)
        executor(TaskNode("t", "a", "t", {"data": 1}))
        assert agent.set_input_data.called

    def test_create_agent_executor_run(self):
        agent = MagicMock()
        agent.run.return_value = "run_ok"
        executor = create_agent_executor(agent)
        assert executor(TaskNode("t", "a", "t", {"data": 1})) == "run_ok"
        agent.run.assert_called_with({"data": 1})

    def test_create_agent_executor_execute(self):
        agent = MagicMock(spec=["execute"])
        agent.execute.return_value = "exec_ok"
        executor = create_agent_executor(agent)
        assert executor(TaskNode("t", "a", "t", {})) == "exec_ok"

    def test_create_agent_executor_callable(self):
        agent = lambda x: "call_ok"
        executor = create_agent_executor(agent)
        assert executor(TaskNode("t", "a", "t", {})) == "call_ok"

    def test_create_agent_executor_invalid(self):
        executor = create_agent_executor("not_an_agent")
        with pytest.raises(ValueError, match="Don't know how to execute"):
            executor(TaskNode("t", "a", "t", {}))

def test_setup_signal_handlers():
    pool = MagicMock()
    with patch('signal.signal') as mock_signal:
        setup_signal_handlers(pool)
        assert mock_signal.call_count == 2
