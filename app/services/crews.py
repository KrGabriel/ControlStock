"""Gestion de cuadrillas y sus fichas operativas."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Crew, Delivery, DeliveryDetail, Item, ReturnRecord, StockMovement
from app.domain import DELIVERY_ACTIVE
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.balances import crew_assigned_units, crew_balances
from app.services.deliveries import list_deliveries
from app.services.returns import list_returns
from app.utils.dates import end_of_day, start_of_day


def list_crews(session: Session, include_inactive: bool = False) -> list[Crew]:
    stmt = select(Crew).order_by(Crew.name)
    if not include_inactive:
        stmt = stmt.where(Crew.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_crew(session: Session, crew_id: int) -> Crew:
    crew = session.get(Crew, crew_id)
    if crew is None:
        raise NotFoundError("La cuadrilla no existe.")
    return crew


def create_crew(session: Session, name: str, notes: str = "") -> Crew:
    name = (name or "").strip()
    if len(name) < 2:
        raise ValidationError("El nombre de la cuadrilla es demasiado corto.")
    exists = session.scalar(select(Crew).where(func.lower(Crew.name) == name.lower()))
    if exists:
        raise ValidationError("Ya existe una cuadrilla con ese nombre.")
    crew = Crew(name=name, notes=(notes or "").strip())
    session.add(crew)
    session.flush()
    return crew


def update_crew(session: Session, crew_id: int, name: str, notes: str = "") -> Crew:
    crew = get_crew(session, crew_id)
    name = (name or "").strip()
    if len(name) < 2:
        raise ValidationError("El nombre de la cuadrilla es demasiado corto.")
    exists = session.scalar(
        select(Crew).where(func.lower(Crew.name) == name.lower(), Crew.id != crew_id)
    )
    if exists:
        raise ValidationError("Ya existe una cuadrilla con ese nombre.")
    crew.name = name
    crew.notes = (notes or "").strip()
    session.flush()
    return crew


def set_crew_active(session: Session, crew_id: int, active: bool) -> Crew:
    crew = get_crew(session, crew_id)
    if not active and crew_assigned_units(session, crew_id) > 0:
        raise ConflictError(
            "La cuadrilla tiene materiales pendientes de devolucion. No puede desactivarse."
        )
    crew.is_active = bool(active)
    session.flush()
    return crew


def crew_summary(session: Session, crew_id: int) -> dict:
    crew = get_crew(session, crew_id)
    balances = crew_balances(session, crew_id)
    deliveries = list_deliveries(session, crew_id=crew_id, status=None)
    returns = list_returns(session, crew_id=crew_id, status=None)
    return {
        "crew": crew,
        "assigned_units": crew_assigned_units(session, crew_id),
        "assigned_articles": len(balances),
        "balances": balances,
        "deliveries": deliveries,
        "returns": returns,
        "delivery_count": len([d for d in deliveries if d.status == DELIVERY_ACTIVE]),
        "return_count": len([r for r in returns if r.status == DELIVERY_ACTIVE]),
    }


def crew_deliveries(session: Session, crew_id: int) -> list[Delivery]:
    return list_deliveries(session, crew_id=crew_id, status=None)


def crew_returns(session: Session, crew_id: int) -> list[ReturnRecord]:
    return list_returns(session, crew_id=crew_id, status=None)


def crew_movements(
    session: Session,
    crew_id: int,
    *,
    day: date | None = None,
    limit: int | None = None,
) -> list[StockMovement]:
    stmt = (
        select(StockMovement)
        .options(joinedload(StockMovement.item), joinedload(StockMovement.user))
        .where(StockMovement.crew_id == crew_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    )
    if day:
        stmt = stmt.where(
            StockMovement.created_at >= start_of_day(day),
            StockMovement.created_at <= end_of_day(day),
        )
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def consumed_by_crew(
    session: Session,
    crew_id: int,
    *,
    date_from=None,
    date_to=None,
) -> list[dict]:
    stmt = (
        select(
            Item,
            func.sum(DeliveryDetail.quantity).label("total"),
        )
        .join(DeliveryDetail, DeliveryDetail.item_id == Item.id)
        .join(Delivery, DeliveryDetail.delivery_id == Delivery.id)
        .where(
            Delivery.crew_id == crew_id,
            Delivery.status == DELIVERY_ACTIVE,
            DeliveryDetail.is_reusable.is_(False),
        )
        .group_by(Item.id)
        .order_by(func.sum(DeliveryDetail.quantity).desc())
    )
    if date_from:
        stmt = stmt.where(Delivery.created_at >= start_of_day(date_from))
    if date_to:
        stmt = stmt.where(Delivery.created_at <= end_of_day(date_to))
    rows = session.execute(stmt).all()
    return [{"item": item, "quantity": int(total or 0)} for item, total in rows]


def crew_options(session: Session) -> list[tuple[int, str]]:
    return [(crew.id, crew.name) for crew in list_crews(session)]
