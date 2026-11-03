"""Registro de entregas de materiales a cuadrillas."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Crew, Delivery, DeliveryDetail, Item, StockMovement
from app.domain import (
    DELIVERY_ACTIVE,
    DELIVERY_VOIDED,
    ICLASS_ACTION_CREATED,
    ICLASS_LOADED,
    ICLASS_PENDING,
    MOVE_DELIVERY,
    MOVE_VOID_DELIVERY,
    STATE_ASSIGNED,
    STATE_AVAILABLE,
)
from app.db.models import IClassRegistration
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.common import generate_code
from app.services.stock import _mark_voided, add_stock_movement
from app.utils.dates import end_of_day, now as current_time, start_of_day


def _get_crew(session: Session, crew_id: int) -> Crew:
    crew = session.get(Crew, crew_id)
    if crew is None:
        raise NotFoundError("La cuadrilla no existe.")
    if not crew.is_active:
        raise ConflictError("La cuadrilla esta desactivada.")
    return crew


def create_delivery(
    session: Session,
    *,
    crew_id: int,
    technician: str,
    lines: list[tuple[int, int]],
    notes: str = "",
    user_id: int | None = None,
    occurred_at: datetime | None = None,
) -> Delivery:
    crew = _get_crew(session, crew_id)
    technician = (technician or "").strip()
    if len(technician) < 2:
        raise ValidationError("Ingrese el nombre del tecnico responsable.")
    if not lines:
        raise ValidationError("Agregue al menos un articulo a la entrega.")

    consolidated: dict[int, int] = {}
    for item_id, quantity in lines:
        try:
            item_id = int(item_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError("Los articulos y cantidades deben ser validos.")
        if quantity <= 0:
            raise ValidationError("Las cantidades deben ser mayores que cero.")
        consolidated[item_id] = consolidated.get(item_id, 0) + quantity

    items: dict[int, Item] = {}
    for item_id, quantity in consolidated.items():
        item = session.get(Item, item_id)
        if item is None:
            raise NotFoundError("Uno de los articulos seleccionados no existe.")
        if not item.is_active:
            raise ConflictError(f"El articulo '{item.name}' esta desactivado.")
        if quantity > item.qty_available:
            raise ValidationError(
                f"Stock insuficiente de '{item.name}'. Disponible: {item.qty_available}, "
                f"solicitado: {quantity}."
            )
        items[item_id] = item

    when = occurred_at or current_time()
    delivery = Delivery(
        code=generate_code(session, "ENT", Delivery),
        crew_id=crew.id,
        technician=technician,
        notes=(notes or "").strip(),
        status=DELIVERY_ACTIVE,
        iclass_status=ICLASS_PENDING,
        created_at=when,
        created_by_id=user_id,
    )
    session.add(delivery)
    session.flush()

    for item_id, quantity in consolidated.items():
        item = items[item_id]
        detail = DeliveryDetail(
            delivery_id=delivery.id,
            item_id=item.id,
            quantity=quantity,
            qty_returned=0,
            is_reusable=item.item_type == "REUSABLE",
            item_name_snapshot=item.name,
            item_brand_snapshot=item.brand,
        )
        session.add(detail)

        before = item.qty_available
        item.qty_available = before - quantity
        if detail.is_reusable:
            item.qty_assigned += quantity
        item.updated_at = when
        session.flush()

        add_stock_movement(
            session,
            movement_type=MOVE_DELIVERY,
            item=item,
            quantity=quantity,
            stock_delta=-quantity,
            stock_before=before,
            stock_after=item.qty_available,
            user_id=user_id,
            crew_id=crew.id,
            technician=technician,
            delivery_id=delivery.id,
            observations=(notes or "").strip(),
            from_state=STATE_AVAILABLE,
            to_state=STATE_ASSIGNED if detail.is_reusable else None,
            occurred_at=when,
        )

    session.add(
        IClassRegistration(
            delivery_id=delivery.id,
            action=ICLASS_ACTION_CREATED,
            previous_status="",
            new_status=ICLASS_PENDING,
            reference="",
            notes="Entrega registrada en el sistema.",
            user_id=user_id,
            created_at=when,
        )
    )
    session.flush()
    return delivery


def get_delivery(session: Session, delivery_id: int) -> Delivery:
    delivery = session.scalar(
        select(Delivery)
        .options(
            joinedload(Delivery.crew),
            joinedload(Delivery.details).joinedload(DeliveryDetail.item),
            joinedload(Delivery.iclass_history).joinedload(IClassRegistration.user),
        )
        .where(Delivery.id == delivery_id)
    )
    if delivery is None:
        raise NotFoundError("La entrega no existe.")
    return delivery


def list_deliveries(
    session: Session,
    *,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
    crew_id: int | None = None,
    iclass_status: str | None = None,
    status: str | None = DELIVERY_ACTIVE,
    search: str = "",
    limit: int | None = None,
) -> list[Delivery]:
    stmt = (
        select(Delivery)
        .options(joinedload(Delivery.crew), joinedload(Delivery.details))
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
    )
    if date_from:
        stmt = stmt.where(Delivery.created_at >= start_of_day(date_from))
    if date_to:
        stmt = stmt.where(Delivery.created_at <= end_of_day(date_to))
    if crew_id:
        stmt = stmt.where(Delivery.crew_id == crew_id)
    if iclass_status:
        stmt = stmt.where(Delivery.iclass_status == iclass_status)
    if status:
        stmt = stmt.where(Delivery.status == status)
    if search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            (Delivery.code.ilike(pattern)) | (Delivery.technician.ilike(pattern))
        )
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique().all())


def void_delivery(
    session: Session, delivery_id: int, user_id: int | None, reason: str
) -> Delivery:
    delivery = session.scalar(
        select(Delivery)
        .options(joinedload(Delivery.details).joinedload(DeliveryDetail.item))
        .where(Delivery.id == delivery_id)
    )
    if delivery is None:
        raise NotFoundError("La entrega no existe.")
    if delivery.status == DELIVERY_VOIDED:
        raise ConflictError("La entrega ya fue anulada.")
    if delivery.iclass_status == ICLASS_LOADED:
        raise ConflictError(
            "La entrega esta marcada como cargada en IClass. Revierta esa marca antes de anularla."
        )
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Debe indicar el motivo de la anulacion.")
    returned = [d for d in delivery.details if d.qty_returned > 0]
    if returned:
        raise ConflictError(
            "No se puede anular la entrega porque tiene devoluciones asociadas. "
            "Anule primero las devoluciones."
        )

    when = current_time()
    for detail in delivery.details:
        item = detail.item
        if detail.is_reusable:
            if item.qty_assigned < detail.quantity:
                raise ConflictError(
                    f"El saldo asignado de '{item.name}' es inconsistente. "
                    "No se puede anular la entrega."
                )
            item.qty_assigned -= detail.quantity
            item.qty_available += detail.quantity
        else:
            item.qty_available += detail.quantity
        item.updated_at = when
        session.flush()

        orig_movements = list(
            session.scalars(
                select(StockMovement).where(
                    StockMovement.delivery_id == delivery.id,
                    StockMovement.item_id == item.id,
                    StockMovement.movement_type == MOVE_DELIVERY,
                )
            ).all()
        )
        for movement in orig_movements:
            if not movement.is_voided:
                _mark_voided(movement, user_id, reason, when)
                add_stock_movement(
                    session,
                    movement_type=MOVE_VOID_DELIVERY,
                    item=item,
                    quantity=movement.quantity,
                    stock_delta=movement.quantity,
                    stock_before=item.qty_available - movement.quantity,
                    stock_after=item.qty_available,
                    user_id=user_id,
                    crew_id=delivery.crew_id,
                    technician=delivery.technician,
                    delivery_id=delivery.id,
                    observations=f"Anulacion de entrega {delivery.code}. Motivo: {reason}",
                    from_state=STATE_ASSIGNED if detail.is_reusable else None,
                    to_state=STATE_AVAILABLE,
                    occurred_at=when,
                    related_movement_id=movement.id,
                )

    delivery.status = DELIVERY_VOIDED
    delivery.voided_at = when
    delivery.void_reason = reason
    session.flush()
    return delivery


def deliveries_today_count(session: Session) -> int:
    from sqlalchemy import func

    return int(
        session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(
                Delivery.created_at >= start_of_day(current_time()),
                Delivery.status == DELIVERY_ACTIVE,
            )
        )
        or 0
    )
