"""Saldos de materiales asignados a cada cuadrilla."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Crew, Delivery, DeliveryDetail, Item
from app.domain import DELIVERY_ACTIVE


def crew_balances(session: Session, crew_id: int) -> list[dict]:
    """Materiales reutilizables pendientes de devolucion, agrupados por articulo."""
    rows = session.execute(
        select(
            Item,
            func.sum(DeliveryDetail.quantity - DeliveryDetail.qty_returned).label("pending"),
        )
        .join(DeliveryDetail, DeliveryDetail.item_id == Item.id)
        .join(Delivery, DeliveryDetail.delivery_id == Delivery.id)
        .where(
            Delivery.crew_id == crew_id,
            Delivery.status == DELIVERY_ACTIVE,
            DeliveryDetail.is_reusable.is_(True),
        )
        .group_by(Item.id)
        .having(func.sum(DeliveryDetail.quantity - DeliveryDetail.qty_returned) > 0)
        .order_by(Item.name)
    ).all()
    return [
        {"item": item, "quantity": int(pending or 0), "item_id": item.id, "name": item.name}
        for item, pending in rows
        if (pending or 0) > 0
    ]


def crew_balance_map(session: Session, crew_id: int) -> dict[int, int]:
    return {row["item_id"]: row["quantity"] for row in crew_balances(session, crew_id)}


def crew_assigned_units(session: Session, crew_id: int | None = None) -> int:
    stmt = (
        select(func.coalesce(func.sum(DeliveryDetail.quantity - DeliveryDetail.qty_returned), 0))
        .join(Delivery, DeliveryDetail.delivery_id == Delivery.id)
        .where(Delivery.status == DELIVERY_ACTIVE, DeliveryDetail.is_reusable.is_(True))
    )
    if crew_id is not None:
        stmt = stmt.where(Delivery.crew_id == crew_id)
    return int(session.scalar(stmt) or 0)


def assigned_by_crew(session: Session) -> list[tuple[Crew, int]]:
    rows = session.execute(
        select(
            Crew,
            func.coalesce(
                func.sum(DeliveryDetail.quantity - DeliveryDetail.qty_returned), 0
            ).label("pending"),
        )
        .join(Delivery, Delivery.crew_id == Crew.id)
        .join(DeliveryDetail, DeliveryDetail.delivery_id == Delivery.id)
        .where(Delivery.status == DELIVERY_ACTIVE, DeliveryDetail.is_reusable.is_(True))
        .group_by(Crew.id)
        .order_by(Crew.name)
    ).all()
    return [(crew, int(pending or 0)) for crew, pending in rows if (pending or 0) > 0]


def pending_returns_for_crew(session: Session, crew_id: int) -> list[DeliveryDetail]:
    return list(
        session.scalars(
            select(DeliveryDetail)
            .join(Delivery, DeliveryDetail.delivery_id == Delivery.id)
            .options(joinedload(DeliveryDetail.item), joinedload(DeliveryDetail.delivery))
            .where(
                Delivery.crew_id == crew_id,
                Delivery.status == DELIVERY_ACTIVE,
                DeliveryDetail.is_reusable.is_(True),
                DeliveryDetail.qty_returned < DeliveryDetail.quantity,
            )
            .order_by(Delivery.created_at, DeliveryDetail.id)
        ).all()
    )
