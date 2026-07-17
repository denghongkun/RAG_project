"""SQLite 轻量迁移：模型演进后旧库缺列时自动补列。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).fetchone()
    return row is not None


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def apply_sqlite_migrations(engine: Engine) -> None:
    """在 create_all 之后调用，为已存在的表补充新增列。"""
    with engine.begin() as conn:
        if _table_exists(conn, "documents"):
            cols = _column_names(conn, "documents")
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE documents ADD COLUMN user_id INTEGER"))
                conn.execute(text("DELETE FROM documents WHERE user_id IS NULL"))

        if _table_exists(conn, "chat_messages"):
            cols = _column_names(conn, "chat_messages")
            if "session_id" not in cols:
                conn.execute(text("ALTER TABLE chat_messages ADD COLUMN session_id INTEGER"))
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE chat_messages ADD COLUMN user_id INTEGER"))
            # 旧版无会话维度的消息无法对齐新模型，清理以免查询报错
            conn.execute(
                text(
                    "DELETE FROM chat_messages WHERE session_id IS NULL OR user_id IS NULL"
                )
            )
