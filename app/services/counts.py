"""Recuento fisico del stock principal."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    InventoryCount,
    InventoryCountDetail,
    Item,
    StockAdjustment,
)
from app.domain import ADJUSTMENT_COUNT, COUNT_CONFIRMED, COUNT_DRAFT, MOVE_ADJUSTMENT
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.common import generate_code
from app.services.stock import add_stock_movement
from app.utils.dates import now as current_time


def get_count(session: Session, count_id: int) -> InventoryCount:
    count = session.scalar(
        select(InventoryCount)
        .options(
            joinedload(InventoryCount.details).joinedload(InventoryCountDetail.item)
        )
        .where(InventoryCount.id == count_id)
    )
    if count is None:
        raise NotFoundError("El recuento no existe.")
    return count


def get_draft(session: Session) -> InventoryCount | None:
    return session.scalar(
        select(InventoryCount)
        .options(
            joinedload(InventoryCount.details).joinedload(InventoryCountDetail.item)
        )
        .where(InventoryCount.status == COUNT_DRAFT)
        .order_by(InventoryCount.id.desc())
    )


def list_counts(session: Session, limit: int | None = None) -> list[InventoryCount]:
    stmt = (
        select(InventoryCount)
        .options(joinedload(InventoryCount.details))
        .order_by(InventoryCount.started_at.desc(), InventoryCount.id.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique().all())


def start_count(
    session: Session,
    *,
    user_id: int | None,
    notes: str = "",
    occurred_at=None,
) -> InventoryCount:
    existing = get_draft(session)
    if existing is not None:
        raise ConflictError(
            f"Ya existe un recuento en borrador ({existing.code}). Continuelo o descartelo."
        )
    items = list(
        session.scalars(
            select(Item).where(Item.is_active.is_(True)).order_by(Item.name, Item.brand)
        ).all()
    )
    if not items:
        raise ValidationError("No hay articulos activos para realizar el recuento.")
    when = occurred_at or current_time()
    count = InventoryCount(
        code=generate_code(session, "REC", InventoryCount),
        status=COUNT_DRAFT,
        notes=(notes or "").strip(),
        started_at=when,
        created_by_id=user_id,
    )
    session.add(count)
    session.flush()
    for item in items:
        session.add(
            InventoryCountDetail(
                count_id=count.id,
                item_id=item.id,
                item_name_snapshot=item.name,
                system_qty=item.qty_available,
                physical_qty=None,
                difference=None,
                notes="",
            )
        )
    session.flush()
    return get_count(session, count.id)


def _parse_physical(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Las cantidades fisicas deben ser numeros enteros.")
    if parsed < 0:
        raise ValidationError("Las cantidades fisicas no pueden ser negativas.")
    return parsed


def save_count_draft(
    session: Session,
    count_id: int,
    values: dict[int, tuple[int | str | None, str]] | None = None,
    *,
    notes: str | None = None,
) -> InventoryCount:
    count = get_count(session, count_id)
    if count.status != COUNT_DRAFT:
        raise ConflictError("El recuento ya fue confirmado y no puede modificarse.")
    if notes is not None:
        count.notes = (notes or "").strip()
    if values:
        details_by_item = {detail.item_id: detail for detail in count.details}
        for item_id, payload in values.items():
            detail = details_by_item.get(int(item_id))
            if detail is None:
                continue
            if isinstance(payload, tuple):
                physical_raw, line_notes = payload
            else:
                physical_raw, line_notes = payload, ""
            physical = _parse_physical(physical_raw)
            detail.physical_qty = physical
            detail.notes = (line_notes or "").strip()
            detail.difference = (
                physical - detail.system_qty if physical is not None else None
            )
    session.flush()
    return count


def confirm_count(
    session: Session,
    count_id: int,
    *,
    user_id: int | None,
    values: dict[int, tuple[int | str | None, str]] | None = None,
    notes: str | None = None,
    occurred_at=None,
) -> InventoryCount:
    count = get_count(session, count_id)
    if count.status != COUNT_DRAFT:
        raise ConflictError("El recuento ya fue confirmado.")
    if values is not None:
        save_count_draft(session, count_id, values, notes=notes)
    elif notes is not None:
        count.notes = (notes or "").strip()

    when = occurred_at or current_time()
    differences = 0
    for detail in count.details:
        item = detail.item
        if item is None:
            continue
        current = item.qty_available
        physical = detail.physical_qty if detail.physical_qty is not None else current
        if physical < 0:
            raise ValidationError(
                f"La cantidad fisica de '{item.name}' no puede ser negativa."
            )
        difference = physical - current
        detail.system_qty = current
        detail.physical_qty = physical
        detail.difference = difference
        if difference == 0:
            continue

        differences += 1
        before = current
        item.qty_available = physical
        item.updated_at = when
        session.flush()
        reason_parts = [f"Recuento fisico {count.code}"]
        if count.notes:
            reason_parts.append(count.notes)
        if detail.notes:
            reason_parts.append(detail.notes)
        reason = " | ".join(reason_parts)
        movement = add_stock_movement(
            session,
            movement_type=MOVE_ADJUSTMENT,
            item=item,
            quantity=abs(difference),
            stock_delta=difference,
            stock_before=before,
            stock_after=physical,
            user_id=user_id,
            inventory_count_id=count.id,
            observations=reason,
            from_state=None,
            to_state=None,
            occurred_at=when,
        )
        session.add(
            StockAdjustment(
                item_id=item.id,
                adjustment_type=ADJUSTMENT_COUNT,
                quantity=abs(difference),
                previous_available=before,
                new_available=physical,
                reason=reason,
                user_id=user_id,
                movement_id=movement.id,
                inventory_count_id=count.id,
                created_at=when,
            )
        )

    count.status = COUNT_CONFIRMED
    count.confirmed_at = when
    count.confirmed_by_id = user_id
    count.total_differences = differences
    session.flush()
    return count


def discard_draft(session: Session, count_id: int) -> None:
    count = get_count(session, count_id)
    if count.status != COUNT_DRAFT:
        raise ConflictError("Solo se puede descartar un recuento en borrador.")
    session.delete(count)
    session.flush()


def count_rows(count: InventoryCount) -> list[dict]:
    return [
        {
            "detail": detail,
            "item": detail.item,
            "name": detail.item.name if detail.item else detail.item_name_snapshot,
            "system": detail.system_qty,
            "physical": detail.physical_qty,
            "difference": detail.difference,
            "notes": detail.notes,
        }
        for detail in count.details
    ]
