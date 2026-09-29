"""
Utility functions for agent execution within the worker pool.

Extracted from ``orchestration/worker_pool.py`` as part of issue #1767.
"""

import asyncio
import logging
import signal
import sys
from typing import Any, Dict, Optional

from ..task_graph import TaskNode
from .worker_pool import WorkerPool

logger = logging.getLogger(__name__)


def create_agent_executor(agent_instance, tools_mapping: Optional[Dict[str, Any]] = None):
    """
    Create an executor function for running an agent in the worker pool

    Args:
        agent_instance: The agent instance to execute
        tools_mapping: Optional mapping of tools for the agent

    Returns:
        Callable that can be used with WorkerPool.submit_task
    """

    def executor(task: TaskNode) -> Any:
        """Execute the agent with the given task"""
        try:
            # Set up the agent context
            if hasattr(agent_instance, "set_input_data"):
                agent_instance.set_input_data(task.input_data)

            # Execute based on agent type
            if hasattr(agent_instance, "run"):
                result = agent_instance.run(task.input_data)
            elif hasattr(agent_instance, "execute"):
                result = agent_instance.execute(task.input_data)
            elif callable(agent_instance):
                result = agent_instance(task.input_data)
            else:
                raise ValueError(f"Don't know how to execute agent {agent_instance}")

            return result

        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Agent execution failed for task {task.task_id}: {e}")
            raise

    return executor


def setup_signal_handlers(worker_pool: WorkerPool):
    """Set up signal handlers for graceful shutdown"""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down worker pool...")
        worker_pool.stop(wait=True, timeout=30.0)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
