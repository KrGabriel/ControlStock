"""Operaciones de stock y movimientos auditables."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Item, StockAdjustment, StockMovement
from app.domain import (
    ADJUSTMENT_INCOME,
    ADJUSTMENT_STATE,
    ADJUSTMENT_WRITE_OFF,
    MOVE_ADJUSTMENT,
    MOVE_INCOME,
    MOVE_STATE_CHANGE,
    MOVE_VOID_INCOME,
    MOVE_VOID_STATE_CHANGE,
    MOVE_VOID_WRITE_OFF,
    MOVE_WRITE_OFF,
    STATE_AVAILABLE,
    STATE_FIELDS,
    STATE_LABELS,
    MANUAL_STATES,
)
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.settings import get_setting
from app.utils.dates import now as current_time


def _get_item(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise NotFoundError("El articulo no existe.")
    return item


def _validate_positive(quantity: int) -> int:
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError("La cantidad debe ser un numero entero.")
    if quantity <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")
    return quantity


def add_stock_movement(
    session: Session,
    *,
    movement_type: str,
    item: Item,
    quantity: int,
    stock_delta: int,
    stock_before: int,
    stock_after: int,
    user_id: int | None = None,
    crew_id: int | None = None,
    technician: str = "",
    delivery_id: int | None = None,
    return_id: int | None = None,
    inventory_count_id: int | None = None,
    observations: str = "",
    from_state: str | None = None,
    to_state: str | None = None,
    occurred_at: datetime | None = None,
    related_movement_id: int | None = None,
) -> StockMovement:
    movement = StockMovement(
        movement_type=movement_type,
        item_id=item.id,
        item_name_snapshot=item.name,
        quantity=quantity,
        stock_delta=stock_delta,
        stock_before=stock_before,
        stock_after=stock_after,
        user_id=user_id,
        crew_id=crew_id,
        technician=technician,
        delivery_id=delivery_id,
        return_id=return_id,
        inventory_count_id=inventory_count_id,
        observations=observations or "",
        from_state=from_state,
        to_state=to_state,
        created_at=occurred_at or current_time(),
        related_movement_id=related_movement_id,
    )
    session.add(movement)
    session.flush()
    return movement


def _income_observations(supplier: str, observations: str) -> str:
    parts = []
    if supplier.strip():
        parts.append(f"Proveedor: {supplier.strip()}")
    if observations.strip():
        parts.append(observations.strip())
    return " | ".join(parts)


def register_income(
    session: Session,
    *,
    item_id: int,
    quantity: int,
    user_id: int | None,
    supplier: str = "",
    observations: str = "",
    occurred_at: datetime | None = None,
) -> Item:
    item = _get_item(session, item_id)
    if not item.is_active:
        raise ConflictError("El articulo esta desactivado. Reactivelo antes de ingresar stock.")
    quantity = _validate_positive(quantity)
    before = item.qty_available
    item.qty_available = before + quantity
    item.updated_at = current_time()
    session.flush()

    note = _income_observations(supplier, observations)
    movement = add_stock_movement(
        session,
        movement_type=MOVE_INCOME,
        item=item,
        quantity=quantity,
        stock_delta=quantity,
        stock_before=before,
        stock_after=item.qty_available,
        user_id=user_id,
        observations=note,
        from_state=None,
        to_state=STATE_AVAILABLE,
        occurred_at=occurred_at,
    )
    session.add(
        StockAdjustment(
            item_id=item.id,
            adjustment_type=ADJUSTMENT_INCOME,
            quantity=quantity,
            previous_available=before,
            new_available=item.qty_available,
            reason=note,
            user_id=user_id,
            movement_id=movement.id,
            created_at=occurred_at or current_time(),
        )
    )
    session.flush()
    return item


def _manual_state_attr(state: str) -> str:
    if state not in MANUAL_STATES:
        raise ValidationError("El estado seleccionado no es valido para un ajuste manual.")
    return STATE_FIELDS[state]


def change_state(
    session: Session,
    *,
    item_id: int,
    quantity: int,
    from_state: str,
    to_state: str,
    user_id: int | None,
    reason: str = "",
    occurred_at: datetime | None = None,
) -> Item:
    item = _get_item(session, item_id)
    quantity = _validate_positive(quantity)
    if from_state == to_state:
        raise ValidationError("El estado de origen y destino deben ser diferentes.")
    from_attr = _manual_state_attr(from_state)
    to_attr = _manual_state_attr(to_state)
    available_qty = int(getattr(item, from_attr))
    if available_qty < quantity:
        raise ValidationError(
            f"No hay suficientes unidades en estado '{STATE_LABELS[from_state]}'. "
            f"Disponibles: {available_qty}."
        )
    before_available = item.qty_available
    setattr(item, from_attr, available_qty - quantity)
    setattr(item, to_attr, int(getattr(item, to_attr)) + quantity)
    item.updated_at = current_time()
    session.flush()

    delta = item.qty_available - before_available
    movement = add_stock_movement(
        session,
        movement_type=MOVE_STATE_CHANGE,
        item=item,
        quantity=quantity,
        stock_delta=delta,
        stock_before=before_available,
        stock_after=item.qty_available,
        user_id=user_id,
        observations=reason or f"Cambio de {STATE_LABELS[from_state]} a {STATE_LABELS[to_state]}",
        from_state=from_state,
        to_state=to_state,
        occurred_at=occurred_at,
    )
    session.add(
        StockAdjustment(
            item_id=item.id,
            adjustment_type=ADJUSTMENT_STATE,
            quantity=quantity,
            previous_available=before_available,
            new_available=item.qty_available,
            reason=reason,
            user_id=user_id,
            movement_id=movement.id,
            created_at=occurred_at or current_time(),
        )
    )
    session.flush()
    return item


def write_off(
    session: Session,
    *,
    item_id: int,
    quantity: int,
    reason: str,
    user_id: int | None,
    occurred_at: datetime | None = None,
) -> Item:
    item = _get_item(session, item_id)
    quantity = _validate_positive(quantity)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Debe indicar el motivo de la baja.")
    if item.qty_available < quantity:
        raise ValidationError(
            f"No puede dar de baja {quantity} unidades. Stock disponible: {item.qty_available}."
        )
    before = item.qty_available
    item.qty_available = before - quantity
    item.updated_at = current_time()
    session.flush()
    movement = add_stock_movement(
        session,
        movement_type=MOVE_WRITE_OFF,
        item=item,
        quantity=quantity,
        stock_delta=-quantity,
        stock_before=before,
        stock_after=item.qty_available,
        user_id=user_id,
        observations=reason,
        from_state=STATE_AVAILABLE,
        to_state=None,
        occurred_at=occurred_at,
    )
    session.add(
        StockAdjustment(
            item_id=item.id,
            adjustment_type=ADJUSTMENT_WRITE_OFF,
            quantity=quantity,
            previous_available=before,
            new_available=item.qty_available,
            reason=reason,
            user_id=user_id,
            movement_id=movement.id,
            created_at=occurred_at or current_time(),
        )
    )
    session.flush()
    return item


def _mark_voided(movement: StockMovement, user_id: int | None, reason: str, when: datetime) -> None:
    movement.is_voided = True
    movement.voided_at = when
    movement.voided_by_id = user_id
    movement.void_reason = reason


def void_income(
    session: Session,
    movement: StockMovement,
    user_id: int | None,
    reason: str,
    occurred_at: datetime | None = None,
) -> StockMovement:
    if movement.movement_type != MOVE_INCOME or movement.is_voided:
        raise ConflictError("El movimiento no puede anularse.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Debe indicar el motivo de la anulacion.")
    item = _get_item(session, movement.item_id)
    if item.qty_available < movement.quantity:
        raise ConflictError(
            "No se puede anular el ingreso: parte de ese stock ya fue entregado o ajustado."
        )
    before = item.qty_available
    item.qty_available = before - movement.quantity
    item.updated_at = current_time()
    session.flush()
    when = occurred_at or current_time()
    _mark_voided(movement, user_id, reason, when)
    compensation = add_stock_movement(
        session,
        movement_type=MOVE_VOID_INCOME,
        item=item,
        quantity=movement.quantity,
        stock_delta=-movement.quantity,
        stock_before=before,
        stock_after=item.qty_available,
        user_id=user_id,
        observations=f"Anulacion del movimiento #{movement.id}. Motivo: {reason}",
        from_state=STATE_AVAILABLE,
        to_state=None,
        occurred_at=when,
        related_movement_id=movement.id,
    )
    return compensation


def void_write_off(
    session: Session,
    movement: StockMovement,
    user_id: int | None,
    reason: str,
    occurred_at: datetime | None = None,
) -> StockMovement:
    if movement.movement_type != MOVE_WRITE_OFF or movement.is_voided:
        raise ConflictError("El movimiento no puede anularse.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Debe indicar el motivo de la anulacion.")
    item = _get_item(session, movement.item_id)
    before = item.qty_available
    item.qty_available = before + movement.quantity
    item.updated_at = current_time()
    session.flush()
    when = occurred_at or current_time()
    _mark_voided(movement, user_id, reason, when)
    return add_stock_movement(
        session,
        movement_type=MOVE_VOID_WRITE_OFF,
        item=item,
        quantity=movement.quantity,
        stock_delta=movement.quantity,
        stock_before=before,
        stock_after=item.qty_available,
        user_id=user_id,
        observations=f"Anulacion del movimiento #{movement.id}. Motivo: {reason}",
        from_state=None,
        to_state=STATE_AVAILABLE,
        occurred_at=when,
        related_movement_id=movement.id,
    )


def void_state_change(
    session: Session,
    movement: StockMovement,
    user_id: int | None,
    reason: str,
    occurred_at: datetime | None = None,
) -> StockMovement:
    if movement.movement_type != MOVE_STATE_CHANGE or movement.is_voided:
        raise ConflictError("El movimiento no puede anularse.")
    if not movement.from_state or not movement.to_state:
        raise ConflictError("El movimiento no contiene informacion de estados.")
    if movement.from_state not in MANUAL_STATES or movement.to_state not in MANUAL_STATES:
        raise ConflictError("El cambio de estado no puede anularse.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Debe indicar el motivo de la anulacion.")
    item = _get_item(session, movement.item_id)
    to_attr = STATE_FIELDS[movement.to_state]
    if int(getattr(item, to_attr)) < movement.quantity:
        raise ConflictError(
            "No se puede anular el cambio: las unidades ya no se encuentran en el estado destino."
        )
    from_attr = STATE_FIELDS[movement.from_state]
    before = item.qty_available
    setattr(item, to_attr, int(getattr(item, to_attr)) - movement.quantity)
    setattr(item, from_attr, int(getattr(item, from_attr)) + movement.quantity)
    item.updated_at = current_time()
    session.flush()
    when = occurred_at or current_time()
    _mark_voided(movement, user_id, reason, when)
    return add_stock_movement(
        session,
        movement_type=MOVE_VOID_STATE_CHANGE,
        item=item,
        quantity=movement.quantity,
        stock_delta=item.qty_available - before,
        stock_before=before,
        stock_after=item.qty_available,
        user_id=user_id,
        observations=f"Anulacion del movimiento #{movement.id}. Motivo: {reason}",
        from_state=movement.to_state,
        to_state=movement.from_state,
        occurred_at=when,
        related_movement_id=movement.id,
    )


def void_movement(
    session: Session, movement_id: int, user_id: int | None, reason: str
) -> StockMovement:
    movement = session.get(StockMovement, movement_id)
    if movement is None:
        raise NotFoundError("El movimiento no existe.")
    if movement.is_voided:
        raise ConflictError("El movimiento ya fue anulado.")
    if movement.movement_type == MOVE_INCOME:
        return void_income(session, movement, user_id, reason)
    if movement.movement_type == MOVE_WRITE_OFF:
        return void_write_off(session, movement, user_id, reason)
    if movement.movement_type == MOVE_STATE_CHANGE:
        return void_state_change(session, movement, user_id, reason)
    if movement.movement_type in ("DELIVERY", "RETURN"):
        if movement.delivery_id:
            from app.services.deliveries import void_delivery

            void_delivery(session, movement.delivery_id, user_id, reason)
            return movement
        if movement.return_id:
            from app.services.returns import void_return

            void_return(session, movement.return_id, user_id, reason)
            return movement
    if movement.movement_type == MOVE_ADJUSTMENT:
        raise ConflictError(
            "Los ajustes de recuento no se anulan individualmente. Realice un nuevo recuento fisico."
        )
    raise ConflictError("Este tipo de movimiento no admite anulacion directa.")
