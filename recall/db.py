import sqlite3
from datetime import datetime
from typing import Optional
from recall.config import DB_PATH, ensure_app_dir
from recall.models import SavedCommand


def get_conn() -> sqlite3.Connection:
    ensure_app_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                command     TEXT NOT NULL,
                description TEXT NOT NULL,
                tags        TEXT DEFAULT '',
                tool        TEXT DEFAULT 'general',
                created_at  TEXT NOT NULL,
                use_count   INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tool ON commands(tool)")
        conn.commit()


def save_command(cmd: SavedCommand) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO commands (command, description, tags, tool, created_at, use_count)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (
                cmd.command,
                cmd.description,
                ",".join(cmd.tags),
                cmd.tool,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def search_commands(query: str) -> list[SavedCommand]:
    like = f"%{query}%"
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, command, description, tags, tool, created_at, use_count
               FROM commands
               WHERE command LIKE ? OR description LIKE ? OR tags LIKE ? OR tool LIKE ?
               ORDER BY use_count DESC, created_at DESC""",
            (like, like, like, like),
        ).fetchall()
    return [SavedCommand.from_row(tuple(r)) for r in rows]


def list_commands(tool: Optional[str] = None) -> list[SavedCommand]:
    with get_conn() as conn:
        if tool:
            rows = conn.execute(
                """SELECT id, command, description, tags, tool, created_at, use_count
                   FROM commands WHERE tool = ? ORDER BY use_count DESC, created_at DESC""",
                (tool,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, command, description, tags, tool, created_at, use_count
                   FROM commands ORDER BY use_count DESC, created_at DESC"""
            ).fetchall()
    return [SavedCommand.from_row(tuple(r)) for r in rows]


def delete_command(id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM commands WHERE id = ?", (id,))
        conn.commit()
        return cursor.rowcount > 0


def increment_use(id: int):
    with get_conn() as conn:
        conn.execute("UPDATE commands SET use_count = use_count + 1 WHERE id = ?", (id,))
        conn.commit()
