"""Estado administrativo de cargas en IClass (no modifica stock)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Delivery, IClassRegistration
from app.domain import (
    DELIVERY_ACTIVE,
    DELIVERY_VOIDED,
    ICLASS_ACTION_LOADED,
    ICLASS_ACTION_REVERTED,
    ICLASS_LOADED,
    ICLASS_PENDING,
)
from app.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import now as current_time


def _get_delivery(session: Session, delivery_id: int) -> Delivery:
    delivery = session.get(Delivery, delivery_id)
    if delivery is None:
        raise NotFoundError("La entrega no existe.")
    if delivery.status == DELIVERY_VOIDED:
        raise ConflictError("No se puede operar sobre una entrega anulada.")
    return delivery


def mark_loaded(
    session: Session,
    delivery_id: int,
    *,
    user_id: int | None,
    reference: str = "",
    notes: str = "",
    occurred_at: datetime | None = None,
) -> Delivery:
    delivery = _get_delivery(session, delivery_id)
    if delivery.iclass_status == ICLASS_LOADED:
        raise ConflictError(f"La entrega {delivery.code} ya esta cargada en IClass.")
    when = occurred_at or current_time()
    previous = delivery.iclass_status
    delivery.iclass_status = ICLASS_LOADED
    delivery.iclass_loaded_at = when
    delivery.iclass_loaded_by_id = user_id
    delivery.iclass_reference = (reference or "").strip()
    delivery.iclass_notes = (notes or "").strip()
    session.add(
        IClassRegistration(
            delivery_id=delivery.id,
            action=ICLASS_ACTION_LOADED,
            previous_status=previous,
            new_status=ICLASS_LOADED,
            reference=delivery.iclass_reference,
            notes=delivery.iclass_notes,
            user_id=user_id,
            created_at=when,
        )
    )
    session.flush()
    return delivery


def mark_many_loaded(
    session: Session,
    delivery_ids: list[int],
    *,
    user_id: int | None,
    reference: str = "",
    notes: str = "",
) -> int:
    if not delivery_ids:
        raise ValidationError("Seleccione al menos una entrega.")
    count = 0
    for delivery_id in delivery_ids:
        mark_loaded(
            session,
            delivery_id,
            user_id=user_id,
            reference=reference,
            notes=notes,
        )
        count += 1
    return count


def revert_loaded(
    session: Session,
    delivery_id: int,
    *,
    user_id: int | None,
    reason: str,
    occurred_at: datetime | None = None,
) -> Delivery:
    delivery = _get_delivery(session, delivery_id)
    if delivery.iclass_status != ICLASS_LOADED:
        raise ConflictError(f"La entrega {delivery.code} no esta marcada como cargada.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Indique el motivo de la reversion.")
    when = occurred_at or current_time()
    previous_reference = delivery.iclass_reference
    delivery.iclass_status = ICLASS_PENDING
    delivery.iclass_loaded_at = None
    delivery.iclass_loaded_by_id = None
    delivery.iclass_reference = ""
    delivery.iclass_notes = ""
    session.add(
        IClassRegistration(
            delivery_id=delivery.id,
            action=ICLASS_ACTION_REVERTED,
            previous_status=ICLASS_LOADED,
            new_status=ICLASS_PENDING,
            reference=previous_reference,
            notes=reason,
            user_id=user_id,
            created_at=when,
        )
    )
    session.flush()
    return delivery


def registrations_for_delivery(session: Session, delivery_id: int) -> list[IClassRegistration]:
    return list(
        session.scalars(
            select(IClassRegistration)
            .options(joinedload(IClassRegistration.user))
            .where(IClassRegistration.delivery_id == delivery_id)
            .order_by(IClassRegistration.created_at.desc(), IClassRegistration.id.desc())
        ).all()
    )


def pending_deliveries(session: Session, limit: int | None = None) -> list[Delivery]:
    stmt = (
        select(Delivery)
        .options(joinedload(Delivery.crew), joinedload(Delivery.details))
        .where(
            Delivery.status == DELIVERY_ACTIVE,
            Delivery.iclass_status == ICLASS_PENDING,
        )
        .order_by(Delivery.created_at, Delivery.id)
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique().all())
