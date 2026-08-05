"""
Portal -> Agent command channel (closes the Category B restore/purge gap
documented in self-healing/category-b-restore.ps1 and STATUS.md).

Design choice: a lightweight poll queue, not Wazuh active-response. The
agent already talks to the portal over plain HTTPS for scan-report submission
(app/routers/cleanup.py POST /cleanup/scan-reports), so reusing that same
channel for commands avoids a second integration path and doesn't require
custom active-response scripts on the Wazuh manager. Cost: latency is bounded
by the agent's poll interval, not instant — acceptable here because restore
and purge are already human/ILM-timed operations, not real-time actions.

PERSISTENCE (changed this session, same as cleanup_store.py): previously an
in-memory dict that did not survive a portal-backend restart. Now backed by
SQLite (stdlib `sqlite3`) via a write-through cache — in-memory by default
(`AADITECH_DB_PATH` unset), file-backed when set. Function signatures are
unchanged.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class CommandType(StrEnum):
    QUARANTINE = "quarantine"   # move an approved item into the quarantine volume
    RESTORE = "restore"   # move an item back from quarantine to its original path
    PURGE = "purge"        # permanently delete an item whose hold window expired


class CommandStatus(StrEnum):
    PENDING = "pending"
    ACKED = "acked"        # agent picked it up and is executing it
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentCommand:
    command_id: str
    endpoint_id: str
    command_type: CommandType
    payload: dict           # e.g. {"item_id", "quarantine_path", "original_path"}
    created_at: str
    status: CommandStatus = CommandStatus.PENDING
    result: str | None = None
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# Persistence (sqlite3)
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("AADITECH_DB_PATH", "")  # "" => in-memory
_conn: sqlite3.Connection | None = None
_cache: dict[str, AgentCommand] | None = None
_conn_lock = threading.RLock()  # FastAPI runs sync handlers on a threadpool; sqlite needs serialized access


def init_db(path: str = "") -> None:
    """Point the command store at a persistent DB file (or "" for in-memory).
    Resets the write-through cache."""
    global _conn, _cache, _DB_PATH
    if _conn is not None:
        _conn.close()
    _conn = None
    _cache = None
    _DB_PATH = path
    _get_conn()


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(
                _DB_PATH or ":memory:",
                check_same_thread=False,  # applets run on FastAPI's threadpool
            )
            _conn.execute(
                "CREATE TABLE IF NOT EXISTS agent_commands "
                "(command_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            _conn.commit()
        return _conn


def _ensure_cache() -> dict[str, AgentCommand]:
    global _cache
    with _conn_lock:
        if _cache is None:
            _cache = {}
            conn = _get_conn()
            rows = conn.execute("SELECT data FROM agent_commands").fetchall()
            for (data,) in rows:
                cmd = _deserialize_command(json.loads(data))
                _cache[cmd.command_id] = cmd
        return _cache


def _save_command(command: AgentCommand) -> None:
    conn = _get_conn()
    with _conn_lock:
        conn.execute(
            "INSERT OR REPLACE INTO agent_commands (command_id, data) VALUES (?, ?)",
            (command.command_id, json.dumps(_serialize_command(command))),
        )
        conn.commit()


def _serialize_command(cmd: AgentCommand) -> dict:
    return {
        "command_id": cmd.command_id,
        "endpoint_id": cmd.endpoint_id,
        "command_type": cmd.command_type.value,
        "payload": cmd.payload,
        "created_at": cmd.created_at,
        "status": cmd.status.value,
        "result": cmd.result,
        "completed_at": cmd.completed_at,
    }


def _deserialize_command(data: dict) -> AgentCommand:
    return AgentCommand(
        command_id=data["command_id"],
        endpoint_id=data["endpoint_id"],
        command_type=CommandType(data["command_type"]),
        payload=data["payload"],
        created_at=data["created_at"],
        status=CommandStatus(data["status"]),
        result=data["result"],
        completed_at=data["completed_at"],
    )


# ---------------------------------------------------------------------------
# Public API (signatures unchanged)
# ---------------------------------------------------------------------------

def enqueue_command(endpoint_id: str, command_type: CommandType, payload: dict) -> AgentCommand:
    command = AgentCommand(
        command_id=str(uuid.uuid4()),
        endpoint_id=endpoint_id,
        command_type=command_type,
        payload=payload,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _ensure_cache()[command.command_id] = command
    _save_command(command)
    return command


def list_pending_commands(endpoint_id: str) -> list[AgentCommand]:
    """Called by the agent's poll loop (self-healing/agent-command-poller.ps1)."""
    return [
        c for c in _ensure_cache().values()
        if c.endpoint_id == endpoint_id and c.status == CommandStatus.PENDING
    ]


def ack_command(command_id: str) -> AgentCommand:
    """Agent marks a command as picked up and in progress."""
    command = _ensure_cache().get(command_id)
    if not command:
        raise KeyError(f"No such command: {command_id}")
    command.status = CommandStatus.ACKED
    _save_command(command)
    return command


def complete_command(command_id: str, success: bool, result: str) -> AgentCommand:
    """Agent reports the outcome after actually running the script on the endpoint."""
    command = _ensure_cache().get(command_id)
    if not command:
        raise KeyError(f"No such command: {command_id}")
    command.status = CommandStatus.DONE if success else CommandStatus.FAILED
    command.result = result
    command.completed_at = datetime.now(timezone.utc).isoformat()
    _save_command(command)
    return command


def get_command(command_id: str) -> AgentCommand | None:
    return _ensure_cache().get(command_id)