from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "caseops.db"
DATA_PATH = BASE_DIR / "data" / "matters.json"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(seed_path: Path = DATA_PATH) -> None:
    """Create the local case database and seed fake matters if empty."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matters (
                matter_id TEXT PRIMARY KEY,
                matter_name TEXT NOT NULL,
                matter_type TEXT NOT NULL,
                client TEXT NOT NULL,
                phase TEXT NOT NULL,
                lead_attorney TEXT NOT NULL,
                paralegal TEXT NOT NULL,
                status TEXT NOT NULL,
                open_date TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id TEXT NOT NULL,
                title TEXT NOT NULL,
                assigned_to TEXT,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (matter_id) REFERENCES matters(matter_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id TEXT NOT NULL,
                note_text TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT 'Mini LOIS',
                created_at TEXT NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES matters(matter_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id TEXT NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                owner TEXT,
                created_at TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (matter_id) REFERENCES matters(matter_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_payload TEXT NOT NULL,
                source_refs TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        count = conn.execute("SELECT COUNT(*) AS c FROM matters").fetchone()["c"]
        if count == 0:
            matters = json.loads(seed_path.read_text(encoding="utf-8"))
            for matter in matters:
                conn.execute(
                    """
                    INSERT INTO matters (
                        matter_id, matter_name, matter_type, client, phase,
                        lead_attorney, paralegal, status, open_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        matter["matter_id"],
                        matter["matter_name"],
                        matter["matter_type"],
                        matter["client"],
                        matter["phase"],
                        matter["lead_attorney"],
                        matter["paralegal"],
                        matter["status"],
                        matter["open_date"],
                    ),
                )


def _rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with _connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_matters() -> list[dict[str, Any]]:
    return _rows("SELECT * FROM matters ORDER BY matter_id")


def get_matter(matter_id: str) -> dict[str, Any] | None:
    rows = _rows("SELECT * FROM matters WHERE matter_id = ?", (matter_id,))
    return rows[0] if rows else None


def get_tasks(matter_id: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM tasks WHERE matter_id = ? ORDER BY id DESC", (matter_id,))


def get_notes(matter_id: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM notes WHERE matter_id = ? ORDER BY id DESC", (matter_id,))


def get_calendar_events(matter_id: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM calendar_events WHERE matter_id = ? ORDER BY event_date", (matter_id,))


def get_audit_log(matter_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if matter_id:
        return _rows(
            "SELECT * FROM audit_log WHERE matter_id = ? ORDER BY id DESC LIMIT ?",
            (matter_id, limit),
        )
    return _rows("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


def execute_action(action: dict[str, Any], source_refs: list[str] | None = None) -> str:
    """Execute a model-proposed action after the user approves it."""
    action_type = action.get("action_type")
    matter_id = action.get("matter_id")
    now = datetime.now(timezone.utc).isoformat()

    if not matter_id:
        raise ValueError("Action payload is missing matter_id.")

    with _connect() as conn:
        if action_type == "create_task":
            conn.execute(
                """
                INSERT INTO tasks (matter_id, title, assigned_to, due_date, created_at, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    matter_id,
                    action.get("title", "Untitled task"),
                    action.get("assigned_to"),
                    action.get("due_date"),
                    now,
                    action.get("reason"),
                ),
            )
            result = "Task created."
        elif action_type == "add_note":
            conn.execute(
                """
                INSERT INTO notes (matter_id, note_text, author, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    matter_id,
                    action.get("note_text", ""),
                    action.get("author", "Mini LOIS"),
                    now,
                ),
            )
            result = "Note added."
        elif action_type == "create_calendar_event":
            conn.execute(
                """
                INSERT INTO calendar_events (matter_id, title, event_date, owner, created_at, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    matter_id,
                    action.get("title", "Untitled calendar event"),
                    action.get("event_date"),
                    action.get("owner"),
                    now,
                    action.get("reason"),
                ),
            )
            result = "Calendar event created."
        else:
            raise ValueError(f"Unsupported action_type: {action_type}")

        conn.execute(
            """
            INSERT INTO audit_log (matter_id, action_type, action_payload, source_refs, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                matter_id,
                action_type,
                json.dumps(action, indent=2),
                json.dumps(source_refs or []),
                now,
            ),
        )
        return result
