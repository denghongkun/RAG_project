"""本地会话历史持久化（SQLite + JSON 快照）。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from src.config import settings


class ChatHistoryStore:
    """管理会话消息持久化，支持刷新页面后恢复。"""

    def __init__(self, db_path: Path | None = None, json_path: Path | None = None) -> None:
        self.db_path = db_path or settings.history_db_path
        self.json_path = json_path or settings.history_json_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);"
            )
            # 向后兼容旧表结构：按需补充字段
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(sessions);").fetchall()
            }
            if "is_pinned" not in columns:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0;"
                )
            if "last_accessed_at" not in columns:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN last_accessed_at TEXT NOT NULL DEFAULT '';"
                )
                now = datetime.utcnow().isoformat()
                conn.execute(
                    "UPDATE sessions SET last_accessed_at = CASE WHEN updated_at != '' THEN updated_at ELSE ? END;",
                    (now,),
                )
            conn.commit()

    def create_session(self, title: str | None = None) -> str:
        session_id = uuid.uuid4().hex
        now = datetime.utcnow().isoformat()
        session_title = (title or "新会话").strip() or "新会话"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(session_id, title, created_at, updated_at, last_accessed_at)
                VALUES(?, ?, ?, ?, ?);
                """,
                (session_id, session_title, now, now, now),
            )
            conn.commit()
        return session_id

    def list_sessions(self, query: str = "") -> list[dict]:
        like_q = f"%{query.strip()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.title,
                    s.is_pinned,
                    s.updated_at,
                    s.last_accessed_at,
                    COUNT(m.id) AS msg_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                WHERE (? = '' OR s.title LIKE ?)
                GROUP BY s.session_id, s.title, s.is_pinned, s.updated_at, s.last_accessed_at
                ORDER BY s.is_pinned DESC, s.last_accessed_at DESC;
                """
                ,
                (query.strip(), like_q),
            ).fetchall()
        return [
            {
                "session_id": row[0],
                "title": row[1],
                "is_pinned": bool(row[2]),
                "updated_at": row[3],
                "last_accessed_at": row[4],
                "msg_count": row[5],
            }
            for row in rows
        ]

    def ensure_session(self, session_id: str, title: str | None = None) -> None:
        now = datetime.utcnow().isoformat()
        session_title = (title or "新会话").strip() or "新会话"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions(
                    session_id, title, created_at, updated_at, last_accessed_at
                )
                VALUES(?, ?, ?, ?, ?);
                """,
                (session_id, session_title, now, now, now),
            )
            conn.commit()

    def rename_session(self, session_id: str, new_title: str) -> None:
        title = new_title.strip() or "未命名会话"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET title = ?, updated_at = ?
                WHERE session_id = ?;
                """,
                (title, datetime.utcnow().isoformat(), session_id),
            )
            conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))
            conn.commit()
        self.dump_json_snapshot(session_id)

    def set_session_pinned(self, session_id: str, is_pinned: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET is_pinned = ?, updated_at = ?
                WHERE session_id = ?;
                """,
                (1 if is_pinned else 0, datetime.utcnow().isoformat(), session_id),
            )
            conn.commit()

    def touch_session_access(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET last_accessed_at = ? WHERE session_id = ?;",
                (datetime.utcnow().isoformat(), session_id),
            )
            conn.commit()

    def load_history(self, session_id: str) -> list[dict]:
        self.ensure_session(session_id)
        self.touch_session_access(session_id)
        return self._fetch_history(session_id)

    def _fetch_history(self, session_id: str) -> list[dict]:
        """只读取消息，不触发会话创建或访问时间更新。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, sources_json
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC;
                """,
                (session_id,),
            ).fetchall()

        history: list[dict] = []
        for role, content, sources_json in rows:
            record = {"role": role, "content": content}
            if sources_json:
                record["sources"] = json.loads(sources_json)
            history.append(record)
        return history

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(session_id, role, content, sources_json, created_at)
                VALUES(?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    role,
                    content,
                    json.dumps(sources, ensure_ascii=False) if sources else None,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?;",
                (datetime.utcnow().isoformat(), session_id),
            )
            conn.commit()
        self.dump_json_snapshot(session_id)

    def clear_history(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?;",
                (datetime.utcnow().isoformat(), session_id),
            )
            conn.commit()
        self.dump_json_snapshot(session_id)

    def dump_json_snapshot(self, session_id: str) -> None:
        payload = {
            "session_id": session_id,
            "messages": self._fetch_history(session_id),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
