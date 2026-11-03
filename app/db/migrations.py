"""Control de version del esquema.

La version 1 crea el esquema inicial. Las versiones futuras deben agregarse a
MIGRATIONS como una lista de sentencias SQL o funciones que reciban una
conexion. El numero se guarda en PRAGMA user_version de SQLite.
"""
from __future__ import annotations

from sqlalchemy import Engine

from app.db.models import Base

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    # Ejemplo futuro:
    # 2: ["ALTER TABLE items ADD COLUMN location VARCHAR(100) NOT NULL DEFAULT ''"],
}


def run_migrations(engine: Engine) -> int:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        current = int(conn.exec_driver_sql("PRAGMA user_version").scalar() or 0)
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                "La base de datos fue creada por una version mas nueva de ControlStock."
            )
        for version in range(current + 1, SCHEMA_VERSION + 1):
            for statement in MIGRATIONS.get(version, []):
                conn.exec_driver_sql(statement)
            conn.exec_driver_sql(f"PRAGMA user_version = {version}")
        return SCHEMA_VERSION
