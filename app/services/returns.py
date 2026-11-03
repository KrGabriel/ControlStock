"""Devoluciones de materiales reutilizables desde cuadrillas."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Crew, Delivery, DeliveryDetail, Item, ReturnDetail, ReturnRecord, StockMovement
from app.domain import (
    CONDITION_GOOD,
    CONDITION_TO_STATE,
    CONDITIONS,
    DELIVERY_ACTIVE,
    DELIVERY_VOIDED,
    MOVE_RETURN,
    MOVE_VOID_RETURN,
    STATE_ASSIGNED,
    STATE_AVAILABLE,
    STATE_FIELDS,
    STATE_LABELS,
)
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.common import generate_code
from app.services.stock import _mark_voided, add_stock_movement
from app.utils.dates import now as current_time


def _get_crew(session: Session, crew_id: int) -> Crew:
    crew = session.get(Crew, crew_id)
    if crew is None:
        raise NotFoundError("La cuadrilla no existe.")
    if not crew.is_active:
        raise ConflictError("La cuadrilla esta desactivada.")
    return crew


def _open_details(session: Session, crew_id: int, item_id: int) -> list[DeliveryDetail]:
    return list(
        session.scalars(
            select(DeliveryDetail)
            .join(Delivery, DeliveryDetail.delivery_id == Delivery.id)
            .where(
                Delivery.crew_id == crew_id,
                Delivery.status == DELIVERY_ACTIVE,
                DeliveryDetail.item_id == item_id,
                DeliveryDetail.is_reusable.is_(True),
                DeliveryDetail.qty_returned < DeliveryDetail.quantity,
            )
            .order_by(Delivery.created_at, DeliveryDetail.id)
        ).all()
    )


def create_return(
    session: Session,
    *,
    crew_id: int,
    lines: list[tuple[int, int, str, str]],
    notes: str = "",
    user_id: int | None = None,
    occurred_at: datetime | None = None,
) -> ReturnRecord:
    """lines: (item_id, quantity, condition, line_notes)."""
    crew = _get_crew(session, crew_id)
    if not lines:
        raise ValidationError("Agregue al menos un articulo a la devolucion.")

    normalized = []
    for item_id, quantity, condition, line_notes in lines:
        try:
            item_id = int(item_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError("Los articulos y cantidades deben ser validos.")
        if quantity <= 0:
            raise ValidationError("Las cantidades deben ser mayores que cero.")
        if condition not in CONDITIONS:
            raise ValidationError("El estado de devolucion no es valido.")
        normalized.append((item_id, quantity, condition, (line_notes or "").strip()))

    when = occurred_at or current_time()
    record = ReturnRecord(
        code=generate_code(session, "DEV", ReturnRecord),
        crew_id=crew.id,
        notes=(notes or "").strip(),
        status=DELIVERY_ACTIVE,
        created_at=when,
        created_by_id=user_id,
    )
    session.add(record)
    session.flush()

    for item_id, quantity, condition, line_notes in normalized:
        item = session.get(Item, item_id)
        if item is None:
            raise NotFoundError("El articulo no existe.")
        if item.item_type != "REUSABLE":
            raise ValidationError(
                f"'{item.name}' es consumible: no genera devoluciones pendientes."
            )
        open_details = _open_details(session, crew.id, item.id)
        outstanding = sum(d.pending_qty for d in open_details)
        if quantity > outstanding:
            raise ValidationError(
                f"No puede devolver {quantity} unidades de '{item.name}'. "
                f"La cuadrilla tiene {outstanding} asignadas."
            )
        if item.qty_assigned < quantity:
            raise ConflictError(
                f"El saldo asignado de '{item.name}' es inconsistente. "
                "Verifique los movimientos antes de continuar."
            )

        remaining = quantity
        for detail in open_details:
            if remaining <= 0:
                break
            take = min(remaining, detail.pending_qty)
            if take <= 0:
                continue
            detail.qty_returned += take
            session.add(
                ReturnDetail(
                    return_id=record.id,
                    item_id=item.id,
                    delivery_detail_id=detail.id,
                    quantity=take,
                    condition=condition,
                    notes=line_notes,
                )
            )
            remaining -= take
        if remaining > 0:
            raise ConflictError(
                "No fue posible distribuir la devolucion entre las entregas de la cuadrilla."
            )

        before = item.qty_available
        item.qty_assigned -= quantity
        target_state = CONDITION_TO_STATE[condition]
        target_attr = STATE_FIELDS[target_state]
        setattr(item, target_attr, int(getattr(item, target_attr)) + quantity)
        if condition == CONDITION_GOOD:
            item.qty_available = before + quantity
        item.updated_at = when
        session.flush()

        add_stock_movement(
            session,
            movement_type=MOVE_RETURN,
            item=item,
            quantity=quantity,
            stock_delta=item.qty_available - before,
            stock_before=before,
            stock_after=item.qty_available,
            user_id=user_id,
            crew_id=crew.id,
            return_id=record.id,
            observations=(
                f"{line_notes} | " if line_notes else ""
            )
            + f"Devuelto en {CONDITIONS[condition].lower()}",
            from_state=STATE_ASSIGNED,
            to_state=target_state,
            occurred_at=when,
        )

    session.flush()
    return record


def get_return(session: Session, return_id: int) -> ReturnRecord:
    record = session.scalar(
        select(ReturnRecord)
        .options(
            joinedload(ReturnRecord.crew),
            joinedload(ReturnRecord.details).joinedload(ReturnDetail.item),
            joinedload(ReturnRecord.details).joinedload(ReturnDetail.delivery_detail),
        )
        .where(ReturnRecord.id == return_id)
    )
    if record is None:
        raise NotFoundError("La devolucion no existe.")
    return record


def list_returns(
    session: Session,
    *,
    crew_id: int | None = None,
    date_from=None,
    date_to=None,
    status: str | None = DELIVERY_ACTIVE,
    limit: int | None = None,
) -> list[ReturnRecord]:
    from app.utils.dates import end_of_day, start_of_day

    stmt = (
        select(ReturnRecord)
        .options(joinedload(ReturnRecord.crew), joinedload(ReturnRecord.details))
        .order_by(ReturnRecord.created_at.desc(), ReturnRecord.id.desc())
    )
    if crew_id:
        stmt = stmt.where(ReturnRecord.crew_id == crew_id)
    if date_from:
        stmt = stmt.where(ReturnRecord.created_at >= start_of_day(date_from))
    if date_to:
        stmt = stmt.where(ReturnRecord.created_at <= end_of_day(date_to))
    if status:
        stmt = stmt.where(ReturnRecord.status == status)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique().all())


def void_return(
    session: Session, return_id: int, user_id: int | None, reason: str
) -> ReturnRecord:
    record = session.scalar(
        select(ReturnRecord)
        .options(
            joinedload(ReturnRecord.details).joinedload(ReturnDetail.item),
            joinedload(ReturnRecord.details).joinedload(ReturnDetail.delivery_detail),
        )
        .where(ReturnRecord.id == return_id)
    )
    if record is None:
        raise NotFoundError("La devolucion no existe.")
    if record.status == DELIVERY_VOIDED:
        raise ConflictError("La devolucion ya fue anulada.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Debe indicar el motivo de la anulacion.")

    groups: dict[tuple[int, str], list[ReturnDetail]] = {}
    for detail in record.details:
        groups.setdefault((detail.item_id, detail.condition), []).append(detail)

    when = current_time()
    for (item_id, condition), details in groups.items():
        item = details[0].item
        quantity = sum(d.quantity for d in details)
        target_state = CONDITION_TO_STATE[condition]
        target_attr = STATE_FIELDS[target_state]
        if int(getattr(item, target_attr)) < quantity:
            raise ConflictError(
                f"No se puede anular la devolucion: no hay {quantity} unidades de "
                f"'{item.name}' en estado '{STATE_LABELS[target_state]}'."
            )
        before = item.qty_available
        setattr(item, target_attr, int(getattr(item, target_attr)) - quantity)
        if condition == CONDITION_GOOD:
            if before < quantity:
                raise ConflictError(
                    f"No hay stock disponible suficiente de '{item.name}' para revertir la devolucion."
                )
            item.qty_available = before - quantity
        item.qty_assigned += quantity
        item.updated_at = when
        session.flush()

        for detail in details:
            if detail.delivery_detail is not None:
                if detail.delivery_detail.qty_returned < detail.quantity:
                    raise ConflictError(
                        "La asignacion de la entrega es inconsistente con esta devolucion."
                    )
                detail.delivery_detail.qty_returned -= detail.quantity

        original_movements = list(
            session.scalars(
                select(StockMovement).where(
                    StockMovement.return_id == record.id,
                    StockMovement.item_id == item.id,
                    StockMovement.to_state == target_state,
                    StockMovement.movement_type == MOVE_RETURN,
                )
            ).all()
        )
        for movement in original_movements:
            if not movement.is_voided:
                _mark_voided(movement, user_id, reason, when)
                add_stock_movement(
                    session,
                    movement_type=MOVE_VOID_RETURN,
                    item=item,
                    quantity=movement.quantity,
                    stock_delta=item.qty_available - before,
                    stock_before=before,
                    stock_after=item.qty_available,
                    user_id=user_id,
                    crew_id=record.crew_id,
                    return_id=record.id,
                    observations=f"Anulacion de devolucion {record.code}. Motivo: {reason}",
                    from_state=target_state,
                    to_state=STATE_ASSIGNED,
                    occurred_at=when,
                    related_movement_id=movement.id,
                )

    record.status = DELIVERY_VOIDED
    record.voided_at = when
    record.void_reason = reason
    session.flush()
    return record
