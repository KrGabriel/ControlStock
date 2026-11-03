"""Gestion de articulos y categorias."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Category,
    DeliveryDetail,
    InventoryCountDetail,
    Item,
    ReturnDetail,
    StockAdjustment,
    StockMovement,
)
from app.domain import ITEM_CONSUMABLE, ITEM_REUSABLE, ITEM_TYPES
from app.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import now

STATUS_ORDER = {
    "NO_STOCK": 0,
    "LOW": 1,
    "REPAIR": 2,
    "OUT_OF_SERVICE": 3,
    "DAMAGED": 4,
    "LOST": 5,
    "OK": 6,
}


def list_categories(session: Session, include_inactive: bool = False) -> list[Category]:
    stmt = select(Category).order_by(Category.name)
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    return list(session.scalars(stmt).all())


def create_category(session: Session, name: str, description: str = "") -> Category:
    name = (name or "").strip()
    if len(name) < 2:
        raise ValidationError("El nombre de la categoria es demasiado corto.")
    exists = session.scalar(select(Category).where(func.lower(Category.name) == name.lower()))
    if exists:
        raise ValidationError("Ya existe una categoria con ese nombre.")
    category = Category(name=name, description=(description or "").strip())
    session.add(category)
    session.flush()
    return category


def update_category(session: Session, category_id: int, name: str, description: str = "") -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise NotFoundError("La categoria no existe.")
    name = (name or "").strip()
    if len(name) < 2:
        raise ValidationError("El nombre de la categoria es demasiado corto.")
    exists = session.scalar(
        select(Category).where(func.lower(Category.name) == name.lower(), Category.id != category_id)
    )
    if exists:
        raise ValidationError("Ya existe una categoria con ese nombre.")
    category.name = name
    category.description = (description or "").strip()
    session.flush()
    return category


def delete_category(session: Session, category_id: int) -> None:
    category = session.get(Category, category_id)
    if category is None:
        raise NotFoundError("La categoria no existe.")
    used = session.scalar(
        select(func.count()).select_from(Item).where(Item.category_id == category_id)
    )
    if used:
        raise ConflictError(
            "La categoria tiene articulos asociados. Puede desactivarla, pero no eliminarla."
        )
    session.delete(category)
    session.flush()


def get_item(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise NotFoundError("El articulo no existe.")
    return item


def _validate_item_data(
    session: Session,
    *,
    name: str,
    brand: str,
    category_id: int,
    item_type: str,
    stock_min: int,
    unit: str,
) -> tuple[str, str, int, str, str, int]:
    name = (name or "").strip()
    brand = (brand or "").strip()
    unit = (unit or "unidades").strip() or "unidades"
    if len(name) < 2:
        raise ValidationError("El nombre del articulo es obligatorio.")
    if item_type not in ITEM_TYPES:
        raise ValidationError("El tipo de articulo no es valido.")
    category = session.get(Category, category_id)
    if category is None:
        raise ValidationError("Seleccione una categoria valida.")
    try:
        stock_min = int(stock_min)
    except (TypeError, ValueError):
        raise ValidationError("El stock minimo debe ser un numero entero.")
    if stock_min < 0:
        raise ValidationError("El stock minimo no puede ser negativo.")
    return name, brand, category_id, item_type, unit, stock_min


def create_item(
    session: Session,
    *,
    name: str,
    brand: str,
    category_id: int,
    item_type: str,
    stock_min: int,
    unit: str = "unidades",
    observations: str = "",
    initial_stock: int = 0,
    user_id: int | None = None,
) -> Item:
    name, brand, category_id, item_type, unit, stock_min = _validate_item_data(
        session,
        name=name,
        brand=brand,
        category_id=category_id,
        item_type=item_type,
        stock_min=stock_min,
        unit=unit,
    )
    try:
        initial_stock = int(initial_stock or 0)
    except (TypeError, ValueError):
        raise ValidationError("El stock inicial debe ser un numero entero.")
    if initial_stock < 0:
        raise ValidationError("El stock inicial no puede ser negativo.")
    item = Item(
        name=name,
        brand=brand,
        category_id=category_id,
        item_type=item_type,
        stock_min=stock_min,
        unit=unit,
        observations=(observations or "").strip(),
        qty_available=0,
    )
    session.add(item)
    session.flush()
    if initial_stock > 0:
        from app.services.stock import register_income

        register_income(
            session,
            item_id=item.id,
            quantity=initial_stock,
            user_id=user_id,
            observations="Stock inicial del articulo",
        )
    return item


def update_item(
    session: Session,
    item_id: int,
    *,
    name: str,
    brand: str,
    category_id: int,
    item_type: str,
    stock_min: int,
    unit: str = "unidades",
    observations: str = "",
) -> Item:
    item = get_item(session, item_id)
    name, brand, category_id, item_type, unit, stock_min = _validate_item_data(
        session,
        name=name,
        brand=brand,
        category_id=category_id,
        item_type=item_type,
        stock_min=stock_min,
        unit=unit,
    )
    if item.item_type != item_type and item.qty_assigned > 0:
        raise ConflictError(
            "No puede cambiar el tipo mientras la cuadrilla tenga unidades pendientes de devolucion."
        )
    if item.item_type == ITEM_CONSUMABLE and item_type == ITEM_REUSABLE and item.total_units == 0:
        pass
    item.name = name
    item.brand = brand
    item.category_id = category_id
    item.item_type = item_type
    item.stock_min = stock_min
    item.unit = unit
    item.observations = (observations or "").strip()
    item.updated_at = now()
    session.flush()
    return item


def set_stock_min(session: Session, item_id: int, stock_min: int) -> Item:
    item = get_item(session, item_id)
    try:
        stock_min = int(stock_min)
    except (TypeError, ValueError):
        raise ValidationError("El stock minimo debe ser un numero entero.")
    if stock_min < 0:
        raise ValidationError("El stock minimo no puede ser negativo.")
    item.stock_min = stock_min
    item.updated_at = now()
    session.flush()
    return item


def set_item_active(session: Session, item_id: int, active: bool) -> Item:
    item = get_item(session, item_id)
    item.is_active = bool(active)
    item.updated_at = now()
    session.flush()
    return item


def delete_item(session: Session, item_id: int) -> None:
    item = get_item(session, item_id)
    checks = (
        (StockMovement, StockMovement.item_id),
        (DeliveryDetail, DeliveryDetail.item_id),
        (ReturnDetail, ReturnDetail.item_id),
        (InventoryCountDetail, InventoryCountDetail.item_id),
        (StockAdjustment, StockAdjustment.item_id),
    )
    for model, column in checks:
        count = session.scalar(select(func.count()).select_from(model).where(column == item_id))
        if count:
            raise ConflictError(
                "El articulo tiene historial de movimientos. Desactivelo en lugar de eliminarlo."
            )
    if item.total_units > 0:
        raise ConflictError("No se puede eliminar un articulo con unidades registradas.")
    session.delete(item)
    session.flush()


def _status_matches(item: Item, status: str) -> bool:
    if not status or status == "ALL":
        return True
    if status == "INACTIVE":
        return not item.is_active
    if not item.is_active:
        return False
    if status == "OK":
        return item.qty_available > 0 and item.primary_status == "OK"
    if status == "LOW":
        return item.qty_available > 0 and item.qty_available <= item.stock_min
    if status == "NO_STOCK":
        return item.qty_available <= 0
    if status == "REPAIR":
        return item.qty_repair > 0
    if status == "DAMAGED":
        return item.qty_damaged > 0
    if status == "LOST":
        return item.qty_lost > 0
    if status == "OUT_OF_SERVICE":
        return item.qty_out_of_service > 0
    if status == "ASSIGNED":
        return item.qty_assigned > 0
    if status == "AVAILABLE":
        return item.qty_available > 0
    return True


def list_items(
    session: Session,
    *,
    search: str = "",
    category_id: int | None = None,
    status: str = "ALL",
    item_type: str | None = None,
    include_inactive: bool = True,
    sort_key: str = "name",
    descending: bool = False,
) -> list[Item]:
    stmt = select(Item).options(joinedload(Item.category))
    if not include_inactive:
        stmt = stmt.where(Item.is_active.is_(True))
    if category_id:
        stmt = stmt.where(Item.category_id == category_id)
    if item_type:
        stmt = stmt.where(Item.item_type == item_type)
    search = (search or "").strip()
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(Item.name.ilike(pattern), Item.brand.ilike(pattern)))
    items = list(session.scalars(stmt).all())
    items = [item for item in items if _status_matches(item, status)]

    key_funcs = {
        "name": lambda i: (i.name.lower(), i.brand.lower()),
        "available": lambda i: i.qty_available,
        "assigned": lambda i: i.qty_assigned,
        "total": lambda i: i.total_units,
        "status": lambda i: STATUS_ORDER.get(i.primary_status, 9),
        "category": lambda i: (i.category.name.lower() if i.category else "", i.name.lower()),
        "created": lambda i: i.created_at,
    }
    func_key = key_funcs.get(sort_key, key_funcs["name"])
    items.sort(key=func_key, reverse=descending)
    return items


def low_stock_items(session: Session, limit: int | None = None) -> list[Item]:
    items = list_items(session, include_inactive=False)
    result = [
        item for item in items if item.qty_available <= item.stock_min and item.is_active
    ]
    result.sort(key=lambda i: (i.qty_available, i.name.lower()))
    return result[:limit] if limit else result


def item_history(session: Session, item_id: int) -> list[StockMovement]:
    return list(
        session.scalars(
            select(StockMovement)
            .where(StockMovement.item_id == item_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        ).all()
    )
