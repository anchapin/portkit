"""
Workflow execution for :class:`ParallelOrchestrator`.

Extracted from ``orchestration/orchestrator.py`` as part of issue #1767.
Exposed as the :class:`WorkflowExecutorMixin`; the orchestrator class combines
this with :class:`WorkflowBuilderMixin` (see :mod:`core.workflows`).
"""

import asyncio
import logging
import time
from typing import Any, Dict

from ..pool import WorkerPool, WorkerType
from ..strategy_selector import OrchestrationStrategy
from ..task_graph import TaskGraph

logger = logging.getLogger(__name__)


class WorkflowExecutorMixin:
    """
    Mixin providing workflow execution strategies (sequential/parallel).

    These methods operate on ``self``, which must supply the strategy/config
    and ``agent_executors`` attributes managed by :class:`ParallelOrchestrator`.
    """

    async def execute_workflow(self, task_graph: TaskGraph) -> Dict[str, Any]:
        """
        Execute the conversion workflow

        Args:
            task_graph: TaskGraph to execute

        Returns:
            Execution results dictionary
        """
        self.task_graph = task_graph
        self.execution_start_time = time.time()

        logger.info(f"Starting workflow execution with {len(task_graph.nodes)} tasks")

        # Initialize worker pool based on strategy
        worker_type = (
            WorkerType.PROCESS if self.current_config.use_process_pool else WorkerType.THREAD
        )

        with WorkerPool(
            max_workers=self.current_config.max_parallel_tasks,
            worker_type=worker_type,
            task_timeout=self.current_config.task_timeout,
            enable_monitoring=self.enable_monitoring,
        ) as worker_pool:
            self.worker_pool = worker_pool

            try:
                # Execute workflow based on strategy
                if self.current_strategy == OrchestrationStrategy.SEQUENTIAL:
                    results = await self._execute_sequential(task_graph, worker_pool)
                else:
                    results = await self._execute_parallel(task_graph, worker_pool)

                self.execution_end_time = time.time()
                self.execution_results = results

                # Record performance metrics
                self._record_performance_metrics(task_graph, results)

                return results

            except asyncio.CancelledError:
                raise  # Always re-raise CancelledError — never swallow it
            except TimeoutError:
                raise  # Re-raise timeouts too
            except Exception as e:
                logger.error(f"Workflow execution failed: {e}")
                self.execution_end_time = time.time()
                raise
            finally:
                self.worker_pool = None

    async def _execute_sequential(
        self, task_graph: TaskGraph, worker_pool: WorkerPool
    ) -> Dict[str, Any]:
        """Execute tasks sequentially (baseline single-threaded execution)"""

        task_order = ["analyze", "plan", "translate", "convert_assets", "package", "validate"]
        results = {}

        for task_id in task_order:
            if task_id not in task_graph.nodes:
                logger.warning(f"Task {task_id} not found in graph")
                continue

            task = task_graph.nodes[task_id]

            if task.agent_name not in self.agent_executors:
                error_msg = f"No executor found for agent {task.agent_name}"
                logger.error(error_msg)
                task_graph.mark_task_failed(task_id, error_msg)
                continue

            try:
                logger.info(f"Executing task {task_id} sequentially")

                # Submit task and wait for completion (non-blocking via async)
                future = await worker_pool.submit_task_async(
                    task, self.agent_executors[task.agent_name]
                )
                result = await asyncio.wait_for(future, timeout=self.current_config.task_timeout)

                # Mark as completed and handle spawning
                spawned_tasks = task_graph.mark_task_completed(task_id, result)

                # In sequential mode, execute spawned tasks immediately
                for spawned_task in spawned_tasks:
                    if spawned_task.agent_name in self.agent_executors:
                        try:
                            spawned_future = await worker_pool.submit_task_async(
                                spawned_task, self.agent_executors[spawned_task.agent_name]
                            )
                            spawned_result = await asyncio.wait_for(
                                spawned_future, timeout=self.current_config.task_timeout
                            )
                            task_graph.mark_task_completed(spawned_task.task_id, spawned_result)
                        except asyncio.CancelledError:
                            raise
                        except TimeoutError:
                            raise
                        except Exception as e:
                            logger.error(f"Spawned task {spawned_task.task_id} failed: {e}")
                            task_graph.mark_task_failed(spawned_task.task_id, str(e))

                results[task_id] = result

            except asyncio.CancelledError:
                raise
            except TimeoutError:
                raise
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                if self.current_config.retry_failed_tasks and task_graph.retry_task(task_id):
                    logger.info(f"Retrying task {task_id}")
                    # Re-execute the task
                    try:
                        retry_future = worker_pool.submit_task(
                            task, self.agent_executors[task.agent_name]
                        )
                        retry_result = retry_future.result(timeout=self.current_config.task_timeout)
                        spawned_tasks = task_graph.mark_task_completed(task_id, retry_result)
                        results[task_id] = retry_result
                        logger.info(f"Task {task_id} succeeded on retry")
                        # Execute any spawned tasks
                        for spawned_task in spawned_tasks:
                            if spawned_task.agent_name in self.agent_executors:
                                try:
                                    spawned_future = worker_pool.submit_task(
                                        spawned_task, self.agent_executors[spawned_task.agent_name]
                                    )
                                    spawned_result = spawned_future.result(
                                        timeout=self.current_config.task_timeout
                                    )
                                    task_graph.mark_task_completed(
                                        spawned_task.task_id, spawned_result
                                    )
                                except asyncio.CancelledError:
                                    raise
                                except TimeoutError:
                                    raise
                                except Exception as spawn_e:
                                    logger.error(
                                        f"Spawned task {spawned_task.task_id} failed: {spawn_e}"
                                    )
                                    task_graph.mark_task_failed(spawned_task.task_id, str(spawn_e))
                        continue  # Continue to next task in sequence
                    except asyncio.CancelledError:
                        raise
                    except TimeoutError:
                        raise
                    except Exception as retry_e:
                        logger.error(f"Task {task_id} failed on retry: {retry_e}")
                        # Fall through to permanent failure

                task_graph.mark_task_failed(task_id, str(e))
                break  # Stop sequential execution on failure

        return results

    async def _execute_parallel(
        self, task_graph: TaskGraph, worker_pool: WorkerPool
    ) -> Dict[str, Any]:
        """Execute tasks in parallel"""

        results = {}
        active_futures: Dict[str, asyncio.Future] = {}

        while not task_graph.is_complete() and not task_graph.has_permanently_failed_tasks():
            # Get ready tasks
            ready_tasks = task_graph.get_ready_tasks()

            # Submit ready tasks that aren't already running
            for task in ready_tasks:
                if task.task_id not in active_futures and task.agent_name in self.agent_executors:
                    logger.info(f"Submitting task {task.task_id} for parallel execution")
                    future = await worker_pool.submit_task_async(
                        task, self.agent_executors[task.agent_name]
                    )
                    active_futures[task.task_id] = future

            if not active_futures:
                logger.warning("No active tasks and no ready tasks - workflow may be stuck")
                break

            # Wait for at least one task to complete (non-blocking)
            completed_futures = []
            try:
                done, _ = await asyncio.wait(
                    active_futures.values(), timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                )
                for future in done:
                    task_id = None
                    for t_id, fut in active_futures.items():
                        if fut == future:
                            task_id = t_id
                            break
                    if task_id is not None:
                        completed_futures.append((task_id, future))
            except TimeoutError:
                # No tasks completed in timeout period, continue to check for new ready tasks
                continue

            if not completed_futures:
                continue

            # Process completed tasks
            for task_id, future in completed_futures:
                del active_futures[task_id]

                try:
                    result = future.result()
                    results[task_id] = result

                    # Mark task completed and handle dynamic spawning
                    spawned_tasks = task_graph.mark_task_completed(task_id, result)

                    # Submit spawned tasks if dynamic spawning is enabled
                    if self.current_config.enable_dynamic_spawning:
                        for spawned_task in spawned_tasks:
                            if spawned_task.agent_name in self.agent_executors:
                                logger.info(
                                    f"Submitting dynamically spawned task {spawned_task.task_id}"
                                )
                                spawned_future = await worker_pool.submit_task_async(
                                    spawned_task, self.agent_executors[spawned_task.agent_name]
                                )
                                active_futures[spawned_task.task_id] = spawned_future

                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    raise
                except Exception as e:
                    logger.error(f"Task {task_id} failed: {e}")
                    if self.current_config.retry_failed_tasks and task_graph.retry_task(task_id):
                        logger.info(f"Retrying task {task_id}")
                    else:
                        task_graph.mark_task_failed(task_id, str(e))

        # Wait for any remaining active tasks
        if active_futures:
            done, _ = await asyncio.wait(active_futures.values(), timeout=10.0)
            for future in done:
                task_id = None
                for t_id, fut in active_futures.items():
                    if fut == future:
                        task_id = t_id
                        break
                if task_id is not None:
                    try:
                        result = future.result()
                        results[task_id] = result
                        task_graph.mark_task_completed(task_id, result)
                    except asyncio.CancelledError:
                        raise
                    except TimeoutError:
                        raise
                    except Exception as e:
                        logger.error(f"Final task {task_id} failed: {e}")
                        task_graph.mark_task_failed(task_id, str(e))

        return results
