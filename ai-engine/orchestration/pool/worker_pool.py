"""
Worker Pool implementation for parallel agent execution.
Part of Phase 2: Core Orchestration Engine Implementation

Extracted from ``orchestration/worker_pool.py`` as part of issue #1767.
The :class:`WorkerPool` lives here; models are in :mod:`pool.models` and the
agent-executor helpers are in :mod:`pool.executor`.
"""

import asyncio
import logging
import multiprocessing
import queue
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Union

from ..task_graph import TaskNode
from .models import WorkerStats, WorkerType

logger = logging.getLogger(__name__)


class WorkerPool:
    """
    Manages a pool of workers for parallel task execution.
    Supports both thread-based (for I/O-bound LLM calls) and process-based (for CPU-bound work) execution.
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        worker_type: WorkerType = WorkerType.THREAD,
        task_timeout: float = 300.0,  # 5 minutes default
        enable_monitoring: bool = True,
    ):
        """
        Initialize the worker pool

        Args:
            max_workers: Maximum number of concurrent workers (None for auto-detect)
            worker_type: Type of workers to use
            task_timeout: Timeout for individual tasks in seconds
            enable_monitoring: Enable performance monitoring
        """
        self.worker_type = worker_type
        self.task_timeout = task_timeout
        self.enable_monitoring = enable_monitoring

        # Auto-detect max workers based on type
        if max_workers is None:
            cpu_count = multiprocessing.cpu_count() or 1
            if worker_type == WorkerType.PROCESS:
                max_workers = cpu_count
            else:
                max_workers = min(32, cpu_count + 4)

        self.max_workers = max_workers
        self.executor: Optional[Union[ThreadPoolExecutor, ProcessPoolExecutor]] = None
        self.active_futures: Dict[str, Future] = {}
        self.task_start_times: Dict[str, float] = {}  # Track task start times for stuck detection
        self.worker_stats: Dict[int, WorkerStats] = {}
        self.task_queue = queue.PriorityQueue()
        self.shutdown_event = threading.Event()
        self.monitor_thread: Optional[threading.Thread] = None

        logger.info(f"Initialized WorkerPool with {max_workers} {worker_type.value} workers")

    def start(self):
        """Start the worker pool"""
        if self.executor is not None:
            logger.warning("WorkerPool already started")
            return

        try:
            if self.worker_type == WorkerType.PROCESS:
                self.executor = ProcessPoolExecutor(
                    max_workers=self.max_workers,
                    mp_context=multiprocessing.get_context("spawn"),  # More reliable than fork
                )
            else:  # THREAD or ASYNC
                self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

            if self.enable_monitoring:
                self.monitor_thread = threading.Thread(target=self._monitor_workers, daemon=True)
                self.monitor_thread.start()

            logger.info(
                f"WorkerPool started with {self.max_workers} {self.worker_type.value} workers"
            )

        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Failed to start WorkerPool: {e}")
            raise

    def stop(self, wait: bool = True, timeout: float = 30.0):
        """
        Stop the worker pool

        Args:
            wait: Whether to wait for active tasks to complete
            timeout: Maximum time to wait for shutdown
        """
        if self.executor is None:
            return

        logger.info("Stopping WorkerPool...")
        self.shutdown_event.set()

        # Cancel active futures if not waiting
        if not wait:
            for task_id, future in self.active_futures.items():
                if not future.done():
                    future.cancel()
                    logger.debug(f"Cancelled task {task_id}")

        # Shutdown executor (timeout parameter not available in all Python versions)
        try:
            self.executor.shutdown(wait=wait, timeout=timeout)
        except TypeError:
            # Fallback for Python versions that don't support timeout parameter
            self.executor.shutdown(wait=wait)
        self.executor = None

        # Stop monitoring thread
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)

        logger.info("WorkerPool stopped")

    def submit_task(self, task: TaskNode, agent_executor: Callable) -> Future:
        """
        Submit a task for execution

        Args:
            task: TaskNode to execute
            agent_executor: Callable that executes the agent

        Returns:
            Future representing the task execution
        """
        if self.executor is None:
            raise RuntimeError("WorkerPool not started")

        if task.task_id in self.active_futures:
            logger.warning(f"Task {task.task_id} already submitted")
            return self.active_futures[task.task_id]

        # Create wrapper function for execution
        def execute_with_monitoring():
            start_time = time.time()
            worker_id = threading.get_ident()

            try:
                logger.debug(f"Worker {worker_id} starting task {task.task_id}")
                task.mark_started()

                # Execute the agent
                result = agent_executor(task)

                # Record stats
                execution_time = time.time() - start_time
                if self.enable_monitoring:
                    if worker_id not in self.worker_stats:
                        self.worker_stats[worker_id] = WorkerStats()
                    self.worker_stats[worker_id].update_completion(execution_time)

                logger.debug(
                    f"Worker {worker_id} completed task {task.task_id} in {execution_time:.2f}s"
                )
                return result

            except asyncio.CancelledError:
                raise
            except TimeoutError:
                raise
            except Exception as e:
                # Record failure stats
                if self.enable_monitoring:
                    if worker_id not in self.worker_stats:
                        self.worker_stats[worker_id] = WorkerStats()
                    self.worker_stats[worker_id].update_failure()

                logger.error(f"Worker {worker_id} failed task {task.task_id}: {e}")
                raise

        # Submit task with timeout
        future = self.executor.submit(execute_with_monitoring)
        self.active_futures[task.task_id] = future
        self.task_start_times[task.task_id] = time.time()  # Record start time for stuck detection

        logger.debug(f"Submitted task {task.task_id} to worker pool")
        return future

    async def submit_task_async(self, task: TaskNode, agent_executor: Callable) -> asyncio.Future:
        """
        Async version of submit_task — submits to thread/process pool and returns
        an awaitable so the event loop is not blocked during wait.

        Args:
            task: TaskNode to execute
            agent_executor: Callable that executes the agent

        Returns:
            asyncio.Future representing the task execution (awaitable)
        """
        # Run synchronous submit in a thread pool to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        future = await loop.run_in_executor(
            self.executor, lambda: self._submit_sync(task, agent_executor)
        )
        # wrap the concurrent.futures.Future in an asyncio.Future for await
        return asyncio.wrap_future(future)

    def _submit_sync(self, task: TaskNode, agent_executor: Callable) -> Future:
        """Synchronous submit for use inside run_in_executor."""
        if self.executor is None:
            raise RuntimeError("WorkerPool not started")

        if task.task_id in self.active_futures:
            logger.warning(f"Task {task.task_id} already submitted")
            return self.active_futures[task.task_id]

        def execute_with_monitoring():
            start_time = time.time()
            worker_id = threading.get_ident()

            try:
                logger.debug(f"Worker {worker_id} starting task {task.task_id}")
                task.mark_started()
                result = agent_executor(task)
                execution_time = time.time() - start_time
                if self.enable_monitoring:
                    if worker_id not in self.worker_stats:
                        self.worker_stats[worker_id] = WorkerStats()
                    self.worker_stats[worker_id].update_completion(execution_time)
                logger.debug(
                    f"Worker {worker_id} completed task {task.task_id} in {execution_time:.2f}s"
                )
                return result

            except asyncio.CancelledError:
                raise
            except TimeoutError:
                raise
            except Exception as e:
                if self.enable_monitoring:
                    if worker_id not in self.worker_stats:
                        self.worker_stats[worker_id] = WorkerStats()
                    self.worker_stats[worker_id].update_failure()
                logger.error(f"Worker {worker_id} failed task {task.task_id}: {e}")
                raise

        future = self.executor.submit(execute_with_monitoring)
        self.active_futures[task.task_id] = future
        self.task_start_times[task.task_id] = time.time()
        logger.debug(f"Submitted task {task.task_id} to worker pool (async)")
        return future

    def wait_for_completion(
        self, tasks: List[TaskNode], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Wait for a set of tasks to complete

        Args:
            tasks: List of TaskNode objects to wait for
            timeout: Maximum time to wait (None for no timeout)

        Returns:
            Dictionary with completion results
        """
        if not tasks:
            return {"completed": [], "failed": [], "timeout": []}

        # Get futures for the tasks
        task_futures = {}
        for task in tasks:
            if task.task_id in self.active_futures:
                task_futures[task.task_id] = self.active_futures[task.task_id]

        completed_tasks = []
        failed_tasks = []
        timeout_tasks = []

        start_time = time.time()

        try:
            # Wait for completion with timeout
            for future in as_completed(task_futures.values(), timeout=timeout):
                elapsed_time = time.time() - start_time
                remaining_timeout = timeout - elapsed_time if timeout else None

                # Find which task this future belongs to
                task_id = None
                for tid, fut in task_futures.items():
                    if fut == future:
                        task_id = tid
                        break

                if task_id is None:
                    continue

                try:
                    result = future.result(timeout=remaining_timeout)
                    completed_tasks.append({"task_id": task_id, "result": result})
                    logger.debug(f"Task {task_id} completed successfully")

                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    raise
                except Exception as e:
                    failed_tasks.append({"task_id": task_id, "error": str(e)})
                    logger.error(f"Task {task_id} failed: {e}")

                # Clean up future and start time references
                if task_id in self.active_futures:
                    del self.active_futures[task_id]
                if task_id in self.task_start_times:
                    del self.task_start_times[task_id]

        except TimeoutError:
            # Handle timeout - identify which tasks didn't complete
            for task_id, future in task_futures.items():
                if not future.done():
                    timeout_tasks.append(task_id)
                    future.cancel()
                    logger.warning(f"Task {task_id} timed out after {timeout}s")

        return {
            "completed": completed_tasks,
            "failed": failed_tasks,
            "timeout": timeout_tasks,
            "total_time": time.time() - start_time,
        }

    def get_active_task_count(self) -> int:
        """Get the number of currently active tasks"""
        return len([f for f in self.active_futures.values() if not f.done()])

    def get_worker_stats(self) -> Dict[str, Any]:
        """Get worker pool statistics"""
        active_workers = len([f for f in self.active_futures.values() if not f.done()])
        total_completed = sum(stats.tasks_completed for stats in self.worker_stats.values())
        total_failed = sum(stats.tasks_failed for stats in self.worker_stats.values())

        avg_task_time = 0.0
        if self.worker_stats:
            total_time = sum(stats.total_execution_time for stats in self.worker_stats.values())
            if total_completed > 0:
                avg_task_time = total_time / total_completed

        return {
            "worker_type": self.worker_type.value,
            "max_workers": self.max_workers,
            "active_workers": active_workers,
            "active_tasks": len(self.active_futures),
            "total_completed": total_completed,
            "total_failed": total_failed,
            "success_rate": total_completed / (total_completed + total_failed)
            if (total_completed + total_failed) > 0
            else 0,
            "average_task_time": avg_task_time,
            "worker_details": {
                worker_id: {
                    "tasks_completed": stats.tasks_completed,
                    "tasks_failed": stats.tasks_failed,
                    "average_time": stats.average_task_time,
                    "last_activity": stats.last_activity,
                }
                for worker_id, stats in self.worker_stats.items()
            },
        }

    def _monitor_workers(self):
        """Background thread for monitoring worker health"""
        logger.debug("Worker monitoring thread started")

        while not self.shutdown_event.wait(timeout=30.0):  # Check every 30 seconds
            try:
                stats = self.get_worker_stats()

                # Log periodic stats
                logger.info(
                    f"WorkerPool stats: {stats['active_workers']}/{stats['max_workers']} workers active, "
                    f"{stats['total_completed']} completed, {stats['total_failed']} failed, "
                    f"{stats['success_rate']:.2%} success rate"
                )

                # Check for stuck tasks (running longer than 2x timeout)
                stuck_tasks = []
                stuck_threshold = self.task_timeout * 2
                current_time = time.time()

                for task_id, future in list(self.active_futures.items()):
                    if not future.done():
                        start_time = self.task_start_times.get(task_id, current_time)
                        elapsed = current_time - start_time
                        if elapsed > stuck_threshold:
                            stuck_tasks.append(task_id)
                            logger.warning(
                                f"Task {task_id} has been running for {elapsed:.1f}s "
                                f"(exceeds {stuck_threshold:.1f}s threshold)"
                            )

                if stuck_tasks:
                    logger.warning(f"Found {len(stuck_tasks)} stuck tasks: {stuck_tasks}")
                    # Actually cancel confirmed stuck tasks so the workflow can progress
                    for task_id in stuck_tasks:
                        if task_id in self.active_futures:
                            stuck_future = self.active_futures[task_id]
                            if not stuck_future.done():
                                stuck_future.cancel()
                                logger.info(f"Cancelled stuck task {task_id}")

            except asyncio.CancelledError:
                raise
            except TimeoutError:
                raise
            except Exception as e:
                logger.error(f"Error in worker monitoring: {e}")

        logger.debug("Worker monitoring thread stopped")

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()
