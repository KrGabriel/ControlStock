"""Rutas persistentes y configuracion general de la aplicacion."""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "ControlStock"


def app_data_dir() -> Path:
    override = os.environ.get("CONTROL_STOCK_DATA_DIR")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_dir() -> Path:
    path = app_data_dir() / "database"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return database_dir() / "control_stock.db"


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_backup_dir() -> Path:
    override = os.environ.get("CONTROL_STOCK_BACKUP_DIR")
    if override:
        path = Path(override)
    else:
        documents = Path.home() / "Documents"
        if not documents.exists():
            documents = app_data_dir()
        path = documents / APP_DIR_NAME / "Copias de seguridad"
    path.mkdir(parents=True, exist_ok=True)
    return path
