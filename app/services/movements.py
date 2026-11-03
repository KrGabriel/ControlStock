"""Consulta del historial general de movimientos."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Crew, Item, StockMovement
from app.errors import NotFoundError
from app.utils.dates import end_of_day, start_of_day


def get_movement(session: Session, movement_id: int) -> StockMovement:
    movement = session.scalar(
        select(StockMovement)
        .options(
            joinedload(StockMovement.item),
            joinedload(StockMovement.crew),
            joinedload(StockMovement.user),
            joinedload(StockMovement.delivery),
            joinedload(StockMovement.return_record),
        )
        .where(StockMovement.id == movement_id)
    )
    if movement is None:
        raise NotFoundError("El movimiento no existe.")
    return movement


def list_movements(
    session: Session,
    *,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
    item_id: int | None = None,
    crew_id: int | None = None,
    movement_types: list[str] | None = None,
    search: str = "",
    limit: int | None = None,
) -> list[StockMovement]:
    stmt = (
        select(StockMovement)
        .join(Item, StockMovement.item_id == Item.id)
        .options(
            joinedload(StockMovement.item),
            joinedload(StockMovement.crew),
            joinedload(StockMovement.user),
        )
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    )
    if date_from:
        stmt = stmt.where(StockMovement.created_at >= start_of_day(date_from))
    if date_to:
        stmt = stmt.where(StockMovement.created_at <= end_of_day(date_to))
    if item_id:
        stmt = stmt.where(StockMovement.item_id == item_id)
    if crew_id:
        stmt = stmt.where(StockMovement.crew_id == crew_id)
    if movement_types:
        stmt = stmt.where(StockMovement.movement_type.in_(movement_types))
    if search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Item.name.ilike(pattern),
                Item.brand.ilike(pattern),
                StockMovement.observations.ilike(pattern),
                StockMovement.technician.ilike(pattern),
                StockMovement.item_name_snapshot.ilike(pattern),
            )
        )
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique().all())


def movement_counts_by_type(
    session: Session,
    *,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
) -> list[tuple[str, int, int]]:
    from sqlalchemy import func

    stmt = select(
        StockMovement.movement_type,
        func.count(StockMovement.id),
        func.coalesce(func.sum(StockMovement.stock_delta), 0),
    ).group_by(StockMovement.movement_type)
    if date_from:
        stmt = stmt.where(StockMovement.created_at >= start_of_day(date_from))
    if date_to:
        stmt = stmt.where(StockMovement.created_at <= end_of_day(date_to))
    return [
        (movement_type, int(count), int(delta))
        for movement_type, count, delta in session.execute(stmt).all()
    ]
