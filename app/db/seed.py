"""Datos iniciales imprescindibles (categorias y cuadrillas)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, Crew
from app.domain import DEFAULT_CATEGORIES, DEFAULT_CREWS


def seed_reference_data(session: Session) -> None:
    existing_categories = set(session.scalars(select(Category.name)).all())
    for name in DEFAULT_CATEGORIES:
        if name not in existing_categories:
            session.add(Category(name=name))

    existing_crews = set(session.scalars(select(Crew.name)).all())
    for name in DEFAULT_CREWS:
        if name not in existing_crews:
            session.add(Crew(name=name))

    session.commit()
