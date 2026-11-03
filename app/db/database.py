"""Motor SQLite y sesiones transaccionales."""
from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import database_path
from app.db.migrations import run_migrations
from app.db.seed import seed_reference_data

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_current_path: str | None = None


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - depends on sqlite
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 5000")
        try:
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
        cursor.close()


def init_db(path: str | Path | None = None, seed: bool = True) -> Engine:
    global _engine, _session_factory, _current_path

    if _engine is not None:
        _engine.dispose()

    if path is None:
        path = database_path()
    text_path = str(path)

    if text_path == ":memory:":
        url = "sqlite:///:memory:"
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{file_path.as_posix()}"
        engine = create_engine(url, future=True, connect_args={"check_same_thread": False})

    _configure_sqlite(engine)
    run_migrations(engine)

    _engine = engine
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _current_path = text_path

    if seed:
        with session_scope() as session:
            seed_reference_data(session)

    return engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("La base de datos no fue inicializada.")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        raise RuntimeError("La base de datos no fue inicializada.")
    return _session_factory


def current_database_path() -> str:
    if _current_path is None:
        raise RuntimeError("La base de datos no fue inicializada.")
    return _current_path


def is_memory_database() -> bool:
    return _current_path == ":memory:"


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sesion con commit/rollback automatico. Toda operacion de stock debe usarla."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_db() -> None:
    global _engine, _session_factory, _current_path
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _current_path = None


def replace_database_file(source: str | Path) -> None:
    """Reemplaza el archivo SQLite en caliente. El llamador debe reiniciar la app."""
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(str(source_path))
    if is_memory_database():
        raise RuntimeError("No se puede restaurar sobre una base de datos en memoria.")
    target = Path(current_database_path())
    if _engine is not None:
        _engine.dispose()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    shutil.copy2(source_path, target)
