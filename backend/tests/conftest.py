from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.main import app
from app.migrations import apply_sqlite_migrations
from app.models import User
from app.security import hash_password


@pytest.fixture()
def test_db_session_factory(tmp_path: Path):
    """每个测试使用独立 SQLite，避免污染开发库。"""
    db_path = tmp_path / "test_app.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    return TestingSessionLocal


@pytest.fixture()
def client(test_db_session_factory) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = test_db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_admin(test_db_session_factory) -> None:
    db = test_db_session_factory()
    try:
        db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
        db.commit()
    finally:
        db.close()

