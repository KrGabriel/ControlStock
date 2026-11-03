"""Indicadores y datos de graficos del panel principal."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Delivery, DeliveryDetail, Item, StockMovement
from app.domain import (
    DELIVERY_ACTIVE,
    ICLASS_PENDING,
    MOVE_DELIVERY,
    MOVE_RETURN,
)
from app.services.balances import assigned_by_crew
from app.services.deliveries import list_deliveries
from app.services.iclass import pending_deliveries
from app.services.inventory import low_stock_items
from app.services.movements import list_movements
from app.utils.dates import end_of_day, month_range, now, start_of_day, today


def get_dashboard_data(session: Session) -> dict:
    today_date = today()
    now_dt = now()
    month_start, month_end = month_range(today_date.year, today_date.month)

    total_articles = int(
        session.scalar(
            select(func.count()).select_from(Item).where(Item.is_active.is_(True))
        )
        or 0
    )
    total_available = int(
        session.scalar(select(func.coalesce(func.sum(Item.qty_available), 0))) or 0
    )
    total_assigned = int(
        session.scalar(select(func.coalesce(func.sum(Item.qty_assigned), 0))) or 0
    )
    low_stock_count = int(
        session.scalar(
            select(func.count())
            .select_from(Item)
            .where(
                Item.is_active.is_(True),
                Item.qty_available <= Item.stock_min,
            )
        )
        or 0
    )
    movements_today = int(
        session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(
                StockMovement.created_at >= start_of_day(today_date),
                StockMovement.created_at <= end_of_day(today_date),
            )
        )
        or 0
    )
    pending_iclass = int(
        session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(
                Delivery.status == DELIVERY_ACTIVE,
                Delivery.iclass_status == ICLASS_PENDING,
            )
        )
        or 0
    )
    repair_units = int(
        session.scalar(select(func.coalesce(func.sum(Item.qty_repair), 0))) or 0
    )
    out_units = int(
        session.scalar(
            select(func.coalesce(func.sum(Item.qty_out_of_service), 0))
        )
        or 0
    )
    damaged_units = int(
        session.scalar(select(func.coalesce(func.sum(Item.qty_damaged), 0))) or 0
    )

    # Movimientos por dia (ultimos 7 dias)
    start_7 = today_date - timedelta(days=6)
    movement_rows = session.execute(
        select(
            StockMovement.created_at,
            StockMovement.movement_type,
            StockMovement.quantity,
            StockMovement.is_voided,
        ).where(StockMovement.created_at >= start_of_day(start_7))
    ).all()
    day_labels = [(start_7 + timedelta(days=i)) for i in range(7)]
    delivered_by_day = {d: 0 for d in day_labels}
    returned_by_day = {d: 0 for d in day_labels}
    for created_at, mtype, quantity, is_voided in movement_rows:
        if is_voided:
            continue
        day = created_at.date()
        if day not in delivered_by_day:
            continue
        if mtype == MOVE_DELIVERY:
            delivered_by_day[day] += int(quantity)
        elif mtype == MOVE_RETURN:
            returned_by_day[day] += int(quantity)

    # Entregas por dia del mes actual
    month_days = (month_end - month_start).days + 1
    delivery_days = [month_start + timedelta(days=i) for i in range(month_days)]
    deliveries_by_day = {d: 0 for d in delivery_days}
    month_delivery_rows = session.execute(
        select(Delivery.created_at).where(
            Delivery.status == DELIVERY_ACTIVE,
            Delivery.created_at >= start_of_day(month_start),
            Delivery.created_at <= end_of_day(month_end),
        )
    ).all()
    for (created_at,) in month_delivery_rows:
        day = created_at.date()
        if day in deliveries_by_day:
            deliveries_by_day[day] += 1

    # Distribucion actual asignada por cuadrilla
    crew_distribution = assigned_by_crew(session)

    # Articulos con mayor movimiento en 30 dias
    since_30 = today_date - timedelta(days=29)
    top_rows = session.execute(
        select(
            Item.name,
            func.sum(StockMovement.quantity),
        )
        .join(StockMovement, StockMovement.item_id == Item.id)
        .where(
            StockMovement.created_at >= start_of_day(since_30),
            StockMovement.movement_type.in_([MOVE_DELIVERY, MOVE_RETURN]),
            StockMovement.is_voided.is_(False),
        )
        .group_by(Item.id)
        .order_by(func.sum(StockMovement.quantity).desc())
        .limit(7)
    ).all()
    top_items = [(name, int(total or 0)) for name, total in top_rows]

    latest_movements = list_movements(session, limit=8)
    latest_deliveries = list_deliveries(session, status=DELIVERY_ACTIVE, limit=6)
    alerts = low_stock_items(session, limit=7)
    pending = pending_deliveries(session, limit=6)

    return {
        "cards": {
            "articles": total_articles,
            "available": total_available,
            "assigned": total_assigned,
            "low_stock": low_stock_count,
            "movements_today": movements_today,
            "pending_iclass": pending_iclass,
            "repair_out": repair_units + out_units,
        },
        "extra_cards": {
            "repair": repair_units,
            "out_of_service": out_units,
            "damaged": damaged_units,
        },
        "days": day_labels,
        "delivered_by_day": [delivered_by_day[d] for d in day_labels],
        "returned_by_day": [returned_by_day[d] for d in day_labels],
        "crew_distribution": crew_distribution,
        "top_items": top_items,
        "month_days": delivery_days,
        "deliveries_by_day": [deliveries_by_day[d] for d in delivery_days],
        "latest_movements": latest_movements,
        "latest_deliveries": latest_deliveries,
        "alerts": alerts,
        "pending_iclass": pending,
        "generated_at": now_dt,
    }
