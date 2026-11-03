"""Preferencias persistentes de la aplicacion."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import default_backup_dir
from app.db.models import AppSetting
from app.utils.dates import now

DEFAULTS = {
    "backup_folder": "",
    "backup_auto_close": "1",
    "backup_daily": "1",
    "backup_retention": "15",
    "last_auto_backup": "",
    "last_restore": "",
}


def get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(AppSetting, key)
    if row is None:
        return DEFAULTS.get(key, default)
    return row.value


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
        row.updated_at = now()


def get_bool(session: Session, key: str, default: bool = False) -> bool:
    value = get_setting(session, key, "1" if default else "0")
    return str(value).strip().lower() in {"1", "true", "si", "yes", "on"}


def set_bool(session: Session, key: str, value: bool) -> None:
    set_setting(session, key, "1" if value else "0")


def get_int(session: Session, key: str, default: int = 0) -> int:
    try:
        return int(get_setting(session, key, str(default)))
    except (TypeError, ValueError):
        return default


def get_backup_folder(session: Session) -> str:
    configured = get_setting(session, "backup_folder", "").strip()
    if configured:
        return configured
    return str(default_backup_dir())
