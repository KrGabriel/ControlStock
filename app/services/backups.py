"""Copias de seguridad y restauracion de la base SQLite."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import (
    current_database_path,
    init_db,
    is_memory_database,
    replace_database_file,
    session_scope,
)
from app.db.models import Backup
from app.domain import BACKUP_AUTOMATIC, BACKUP_KINDS, BACKUP_MANUAL, BACKUP_PRE_RESTORE
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.settings import (
    get_backup_folder,
    get_bool,
    get_int,
    get_setting,
    set_setting,
)
from app.utils.dates import now


def _unique_path(folder: Path, kind: str) -> Path:
    stamp = now().strftime("%Y%m%d_%H%M%S")
    candidate = folder / f"control_stock_{stamp}_{kind.lower()}.db"
    counter = 2
    while candidate.exists():
        candidate = folder / f"control_stock_{stamp}_{kind.lower()}_{counter}.db"
        counter += 1
    return candidate


def _copy_database(destination: Path) -> None:
    if is_memory_database():
        raise ConflictError("Las copias de seguridad requieren una base de datos en archivo.")
    source_path = Path(current_database_path())
    if not source_path.exists():
        raise NotFoundError("No se encontro el archivo de base de datos.")
    source = sqlite3.connect(str(source_path))
    try:
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def create_backup(
    session: Session,
    *,
    user_id: int | None,
    kind: str = BACKUP_MANUAL,
    destination: str | Path | None = None,
    notes: str = "",
) -> Backup:
    if kind not in BACKUP_KINDS:
        raise ValidationError("Tipo de copia de seguridad no valido.")
    folder = Path(destination) if destination else Path(get_backup_folder(session))
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique_path(folder, kind)
    _copy_database(target)
    record = Backup(
        filename=target.name,
        path=str(target),
        size_bytes=target.stat().st_size,
        kind=kind,
        notes=(notes or "").strip(),
        user_id=user_id,
        created_at=now(),
    )
    session.add(record)
    session.flush()
    if kind == BACKUP_AUTOMATIC:
        set_setting(session, "last_auto_backup", now().isoformat(timespec="minutes"))
    _apply_retention(session)
    return record


def _apply_retention(session: Session) -> int:
    retention = max(1, get_int(session, "backup_retention", 15))
    automatic = list(
        session.scalars(
            select(Backup)
            .where(Backup.kind == BACKUP_AUTOMATIC)
            .order_by(Backup.created_at.desc(), Backup.id.desc())
        ).all()
    )
    removed = 0
    for backup in automatic[retention:]:
        path = Path(backup.path)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            continue
        session.delete(backup)
        removed += 1
    return removed


def list_backups(session: Session, limit: int | None = None) -> list[Backup]:
    stmt = select(Backup).order_by(Backup.created_at.desc(), Backup.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def latest_backup(session: Session) -> Backup | None:
    return session.scalar(
        select(Backup).order_by(Backup.created_at.desc(), Backup.id.desc()).limit(1)
    )


def should_create_daily_backup(session: Session) -> bool:
    if not get_bool(session, "backup_daily", True):
        return False
    if is_memory_database():
        return False
    last = get_setting(session, "last_auto_backup", "")
    if not last:
        return True
    try:
        last_date = date.fromisoformat(last[:10])
    except ValueError:
        return True
    return last_date < date.today()


def create_daily_backup_if_needed(user_id: int | None) -> Backup | None:
    with session_scope() as session:
        if not should_create_daily_backup(session):
            return None
        return create_backup(
            session,
            user_id=user_id,
            kind=BACKUP_AUTOMATIC,
            notes="Copia automatica diaria",
        )


def create_automatic_on_close(user_id: int | None) -> Backup | None:
    with session_scope() as session:
        if not get_bool(session, "backup_auto_close", True):
            return None
        return create_backup(
            session,
            user_id=user_id,
            kind=BACKUP_AUTOMATIC,
            notes="Copia automatica al cerrar la aplicacion",
        )


def validate_backup_file(path: str | Path) -> dict:
    backup_path = Path(path)
    if not backup_path.exists():
        raise NotFoundError("El archivo de copia de seguridad no existe.")
    if backup_path.suffix.lower() != ".db":
        raise ValidationError("Seleccione un archivo de copia de seguridad .db valido.")
    try:
        connection = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise ValidationError("El archivo no supera la verificacion de integridad.")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {"users", "items", "categories", "crews", "deliveries", "stock_movements"}
            if not required.issubset(tables):
                raise ValidationError("El archivo no corresponde a una base de datos de ControlStock.")
            user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            item_count = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise ValidationError(f"No se pudo leer la copia de seguridad: {exc}") from exc
    return {
        "path": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "users": int(user_count),
        "items": int(item_count),
    }


def restore_backup(path: str | Path, user_id: int | None) -> dict:
    info = validate_backup_file(path)
    safety = None
    try:
        with session_scope() as session:
            safety = create_backup(
                session,
                user_id=user_id,
                kind=BACKUP_PRE_RESTORE,
                notes=f"Copia de seguridad previa a restaurar {Path(path).name}",
            )
            safety_info = {
                "path": safety.path,
                "filename": safety.filename,
                "size_bytes": safety.size_bytes,
                "created_at": safety.created_at,
            }
    except Exception:
        safety_info = None

    replace_database_file(path)
    init_db()
    if safety_info:
        try:
            with session_scope() as session:
                session.add(
                    Backup(
                        filename=safety_info["filename"],
                        path=safety_info["path"],
                        size_bytes=safety_info["size_bytes"],
                        kind=BACKUP_PRE_RESTORE,
                        notes=f"Copia previa a restaurar {Path(path).name}",
                        user_id=user_id,
                        created_at=safety_info["created_at"],
                    )
                )
                set_setting(session, "last_restore", now().isoformat(timespec="minutes"))
        except Exception:
            pass
    return info


def open_folder(path: str | Path) -> None:
    """Abre una carpeta en el explorador de Windows."""
    import os

    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    os.startfile(str(folder))  # type: ignore[attr-defined]
