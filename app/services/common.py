"""Utilidades compartidas por los servicios."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.utils.dates import now


def generate_code(session: Session, prefix: str, model) -> str:
    """Genera un codigo secuencial diario: PREFIJO-AAAAMMDD-0001."""
    base = f"{prefix}-{now():%Y%m%d}"
    count = int(
        session.scalar(
            select(func.count()).select_from(model).where(model.code.like(f"{base}-%"))
        )
        or 0
    )
    candidate = count + 1
    while True:
        code = f"{base}-{candidate:04d}"
        exists = session.scalar(select(model.id).where(model.code == code))
        if not exists:
            return code
        candidate += 1
