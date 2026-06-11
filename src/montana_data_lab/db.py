from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from montana_data_lab.config import ensure_data_directories, settings
from montana_data_lab.models import Base

_engine: Engine | None = None
_database_url = settings.database_url


def configure_database(database_url: str) -> None:
    """Point future sessions at another database, primarily for tests."""
    global _database_url, _engine
    if _engine is not None:
        _engine.dispose()
    _database_url = database_url
    _engine = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        ensure_data_directories()
        connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}
        _engine = create_engine(_database_url, connect_args=connect_args)
        if _database_url.startswith("sqlite"):
            event.listen(_engine, "connect", _enable_sqlite_features)
    return _engine


def _enable_sqlite_features(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def init_database() -> None:
    Base.metadata.create_all(get_engine())


def session_scope() -> Session:
    return Session(get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
