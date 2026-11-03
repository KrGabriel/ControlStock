from __future__ import annotations

import pytest

from app.db.database import dispose_db, get_session_factory, init_db, session_scope
from app.services.auth import create_admin
from app.session import clear_current_user
from app.utils.dates import now


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROL_STOCK_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("CONTROL_STOCK_DATA_DIR", str(tmp_path / "data"))
    init_db()
    with session_scope() as setup:
        create_admin(setup, "admin", "ClaveSegura123", "Administrador de Prueba")
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
        clear_current_user()
        dispose_db()


def seed_context(session):
    from sqlalchemy import select

    from app.db.models import Category, Crew

    category = session.scalar(select(Category).where(Category.name == "Routers"))
    crew = session.scalar(select(Crew).where(Crew.name == "Cuadrilla 1"))
    return category, crew


def make_item(
    session,
    *,
    name="Router AX3000",
    category_id=None,
    item_type="REUSABLE",
    initial_stock=0,
    user_id=1,
    stock_min=0,
):
    from app.services.inventory import create_item

    if category_id is None:
        category_id = seed_context(session)[0].id
    return create_item(
        session,
        name=name,
        brand="Marca",
        category_id=category_id,
        item_type=item_type,
        stock_min=stock_min,
        initial_stock=initial_stock,
        user_id=user_id,
    )


def make_delivery(session, *, crew_id, lines, technician="Tecnico Uno", notes="", when=None, user_id=1):
    from app.services.deliveries import create_delivery

    return create_delivery(
        session,
        crew_id=crew_id,
        technician=technician,
        lines=lines,
        notes=notes,
        user_id=user_id,
        occurred_at=when or now(),
    )
