"""LangGraph checkpoint + memory integration.

``create_checkpointer`` selects between an in-memory ``MemorySaver`` and a
persistent ``SqliteSaver`` so a conversion run can be resumed after a
crash or a Human-In-The-Loop (HITL) interruption.
"""

import logging
import os
from typing import Optional, Union

from langgraph.checkpoint.memory import MemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    SqliteSaver = None

logger = logging.getLogger(__name__)


def create_checkpointer(
    enable_checkpointing: bool = True,
    checkpoint_db_path: Optional[str] = None,
) -> Optional[Union[MemorySaver, "SqliteSaver"]]:
    """
    Create appropriate checkpointer based on configuration.

    Args:
        enable_checkpointing: Whether to enable checkpointing.
        checkpoint_db_path: Path for SQLite checkpointer db (defaults to /tmp).

    Returns:
        MemorySaver for in-memory, SqliteSaver for persistence, or None.

    Note:
        ``SqliteSaver.from_conn_string()`` is a ``@contextmanager`` in
        ``langgraph-checkpoint-sqlite >= 3.0`` (returns an
        ``Iterator[SqliteSaver]``). We must hold a long-lived saver beyond
        any ``with`` block here, so we instantiate ``SqliteSaver`` directly
        with a ``sqlite3.Connection``.
    """
    if not enable_checkpointing:
        return None

    if SqliteSaver is None:
        logger.warning(
            "SqliteSaver not available, using MemorySaver. "
            "Install langgraph-checkpoint-sqlite for persistent checkpoints."
        )
        return MemorySaver()

    import sqlite3

    if checkpoint_db_path:
        db_path = checkpoint_db_path
    else:
        temp_dir = os.getenv("LANGGRAPH_CHECKPOINT_DIR", "/tmp")
        os.makedirs(temp_dir, exist_ok=True)
        db_path = os.path.join(temp_dir, "portkit_checkpoints.db")

    # `check_same_thread=False` is safe here because the Saver's writes are
    # serialised through LangGraph's executor; the connection is owned for
    # the lifetime of the pipeline.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)
