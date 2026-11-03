"""Construccion de informes diarios, semanales, mensuales e historicos."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Crew,
    Delivery,
    DeliveryDetail,
    Item,
    ReturnRecord,
    StockMovement,
)
from app.domain import (
    CONDITIONS,
    DELIVERY_ACTIVE,
    ICLASS_LOADED,
    ICLASS_PENDING,
    ICLASS_STATUSES,
    ITEM_CONSUMABLE,
    MOVE_ADJUSTMENT,
    MOVE_DELIVERY,
    MOVE_INCOME,
    MOVE_RETURN,
    MOVEMENT_TYPES,
    STATE_LABELS,
)
from app.services.balances import crew_balances
from app.services.crews import consumed_by_crew, list_crews
from app.services.deliveries import list_deliveries
from app.services.iclass import pending_deliveries
from app.services.movements import list_movements
from app.services.returns import list_returns
from app.utils.dates import fmt_date, end_of_day, month_range, now, start_of_day


def _crew_summary_rows(
    deliveries: list[Delivery],
    returns: list[ReturnRecord],
    consumed: dict[int, int],
) -> list[list]:
    data: dict[int, dict] = {}

    def bucket(crew):
        if crew.id not in data:
            data[crew.id] = {
                "name": crew.name,
                "deliveries": 0,
                "delivered_units": 0,
                "returns": 0,
                "returned_units": 0,
                "consumed": consumed.get(crew.id, 0),
                "pending_iclass": 0,
            }
        return data[crew.id]

    for delivery in deliveries:
        row = bucket(delivery.crew)
        row["deliveries"] += 1
        row["delivered_units"] += delivery.total_units
        if delivery.iclass_status == ICLASS_PENDING:
            row["pending_iclass"] += 1
    for record in returns:
        row = bucket(record.crew)
        row["returns"] += 1
        row["returned_units"] += record.total_units
    rows = [list(values.values()) for values in data.values()]
    rows.sort(key=lambda r: r[0])
    return rows


def _consumed_map(deliveries: list[Delivery]) -> tuple[dict[int, int], list[dict]]:
    consumed: dict[int, int] = defaultdict(int)
    detail_rows = []
    for delivery in deliveries:
        for detail in delivery.details:
            if detail.is_reusable:
                continue
            consumed[delivery.crew_id] += detail.quantity
            detail_rows.append(
                {
                    "datetime": delivery.created_at,
                    "crew": delivery.crew.name,
                    "technician": delivery.technician,
                    "item": detail.item_name_snapshot,
                    "quantity": detail.quantity,
                }
            )
    detail_rows.sort(key=lambda r: (r["crew"], r["item"]))
    return consumed, detail_rows


def _units_by_crew(returns: list[ReturnRecord]) -> dict[int, int]:
    data: dict[int, int] = defaultdict(int)
    for record in returns:
        data[record.crew_id] += record.total_units
    return data


def report_daily(session: Session, day: date) -> dict:
    deliveries = list_deliveries(
        session, date_from=day, date_to=day, status=DELIVERY_ACTIVE
    )
    returns = list_returns(session, date_from=day, date_to=day, status=DELIVERY_ACTIVE)
    consumed, consumption_rows = _consumed_map(deliveries)
    summary_rows = _crew_summary_rows(deliveries, returns, consumed)

    delivery_rows = [
        [
            d.code,
            d.created_at,
            d.crew.name,
            d.technician,
            ", ".join(f"{det.item_name_snapshot} x{det.quantity}" for det in d.details),
            d.total_units,
            ICLASS_STATUSES.get(d.iclass_status, d.iclass_status),
        ]
        for d in deliveries
    ]
    detail_rows = []
    for d in deliveries:
        for det in d.details:
            detail_rows.append(
                [
                    d.code,
                    d.created_at,
                    d.crew.name,
                    d.technician,
                    det.item_name_snapshot,
                    det.item_brand_snapshot,
                    det.quantity,
                    "Consumible" if not det.is_reusable else "Reutilizable",
                    ICLASS_STATUSES.get(d.iclass_status, d.iclass_status),
                ]
            )
    return_rows = []
    for record in returns:
        for det in record.details:
            return_rows.append(
                [
                    record.code,
                    record.created_at,
                    record.crew.name,
                    det.item.name,
                    det.quantity,
                    CONDITIONS.get(det.condition, det.condition),
                    det.notes or record.notes,
                ]
            )
    consumption_table = [
        [r["datetime"], r["crew"], r["technician"], r["item"], r["quantity"]]
        for r in consumption_rows
    ]
    sections = [
        {
            "key": "resumen_cuadrillas",
            "title": "Resumen por cuadrilla",
            "columns": [
                "Cuadrilla",
                "Entregas",
                "Unidades entregadas",
                "Devoluciones",
                "Unidades devueltas",
                "Consumibles",
                "Pendientes IClass",
            ],
            "rows": summary_rows,
            "totals": True,
        },
        {
            "key": "entregas",
            "title": "Entregas del dia",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Articulos",
                "Unidades",
                "Estado IClass",
            ],
            "rows": delivery_rows,
            "totals": True,
        },
        {
            "key": "detalle_entregas",
            "title": "Detalle de articulos entregados",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Articulo",
                "Marca",
                "Cantidad",
                "Tipo",
                "Estado IClass",
            ],
            "rows": detail_rows,
            "totals": False,
        },
        {
            "key": "devoluciones",
            "title": "Devoluciones del dia",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Articulo",
                "Cantidad",
                "Estado",
                "Observaciones",
            ],
            "rows": return_rows,
            "totals": True,
        },
        {
            "key": "consumos",
            "title": "Materiales consumidos",
            "columns": ["Fecha y hora", "Cuadrilla", "Tecnico", "Articulo", "Cantidad"],
            "rows": consumption_table,
            "totals": True,
        },
    ]
    return {
        "kind": "daily",
        "title": "Informe diario de movimientos",
        "subtitle": f"Fecha: {fmt_date(day)}",
        "filters": [("Fecha", fmt_date(day))],
        "generated_at": now(),
        "sections": sections,
    }


def _period_deliveries_returns(session, start: date, end: date):
    deliveries = list_deliveries(
        session, date_from=start, date_to=end, status=DELIVERY_ACTIVE
    )
    returns = list_returns(session, date_from=start, date_to=end, status=DELIVERY_ACTIVE)
    return deliveries, returns


def report_weekly(session: Session, start: date, end: date) -> dict:
    deliveries, returns = _period_deliveries_returns(session, start, end)
    consumed, consumption_rows = _consumed_map(deliveries)
    summary_rows = _crew_summary_rows(deliveries, returns, consumed)

    assign_rows = []
    for crew in list_crews(session):
        balances = crew_balances(session, crew.id)
        for balance in balances:
            assign_rows.append(
                [crew.name, balance["name"], balance["quantity"]]
            )

    delivery_rows = [
        [
            d.code,
            d.created_at,
            d.crew.name,
            d.technician,
            d.total_units,
            len(d.details),
            ICLASS_STATUSES.get(d.iclass_status, d.iclass_status),
        ]
        for d in deliveries
    ]
    return_rows = []
    for record in returns:
        for det in record.details:
            return_rows.append(
                [
                    record.code,
                    record.created_at,
                    record.crew.name,
                    det.item.name,
                    det.quantity,
                    CONDITIONS.get(det.condition, det.condition),
                ]
            )
    pending_rows = [
        [
            d.code,
            d.created_at,
            d.crew.name,
            d.technician,
            d.total_units,
            fmt_date(d.created_at),
        ]
        for d in deliveries
        if d.iclass_status == ICLASS_PENDING
    ]
    consumption_table = [
        [r["crew"], r["item"], r["quantity"]] for r in consumption_rows
    ]
    consumption_totals = [
        ["", "TOTAL", sum(r["quantity"] for r in consumption_rows)]
    ]
    sections = [
        {
            "key": "resumen_cuadrillas",
            "title": "Resumen del periodo por cuadrilla",
            "columns": [
                "Cuadrilla",
                "Entregas",
                "Unidades entregadas",
                "Devoluciones",
                "Unidades devueltas",
                "Consumibles",
                "Pendientes IClass",
            ],
            "rows": summary_rows,
            "totals": True,
        },
        {
            "key": "entregas",
            "title": "Entregas del periodo",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Unidades",
                "Articulos",
                "Estado IClass",
            ],
            "rows": delivery_rows,
            "totals": False,
        },
        {
            "key": "devoluciones",
            "title": "Devoluciones del periodo",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Articulo",
                "Cantidad",
                "Estado",
            ],
            "rows": return_rows,
            "totals": True,
        },
        {
            "key": "consumos",
            "title": "Materiales consumidos en el periodo",
            "columns": ["Cuadrilla", "Articulo", "Cantidad"],
            "rows": consumption_table,
            "totals": False,
            "totals_row": consumption_totals[0],
        },
        {
            "key": "asignaciones",
            "title": "Materiales actualmente asignados a cuadrillas",
            "columns": ["Cuadrilla", "Articulo", "Cantidad pendiente"],
            "rows": assign_rows,
            "totals": True,
        },
        {
            "key": "pendientes_iclass",
            "title": "Entregas pendientes de registrar en IClass",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Unidades",
                "Fecha",
            ],
            "rows": pending_rows,
            "totals": False,
        },
    ]
    return {
        "kind": "weekly",
        "title": "Informe semanal de movimientos",
        "subtitle": f"Periodo: {fmt_date(start)} al {fmt_date(end)}",
        "filters": [("Desde", fmt_date(start)), ("Hasta", fmt_date(end))],
        "generated_at": now(),
        "sections": sections,
    }


def report_monthly(session: Session, year: int, month: int) -> dict:
    start, end = month_range(year, month)
    deliveries, returns = _period_deliveries_returns(session, start, end)
    consumed, consumption_rows = _consumed_map(deliveries)
    summary_rows = _crew_summary_rows(deliveries, returns, consumed)

    period_movements = list_movements(
        session,
        date_from=start,
        date_to=end,
        movement_types=[
            MOVE_INCOME,
            MOVE_DELIVERY,
            MOVE_RETURN,
            MOVE_ADJUSTMENT,
        ],
    )
    income_rows = []
    income_units = 0
    adjustment_rows = []
    adjustment_net = 0
    for movement in period_movements:
        if movement.movement_type == MOVE_INCOME and not movement.is_voided:
            income_units += movement.quantity
            income_rows.append(
                [
                    movement.created_at,
                    movement.item_name_snapshot,
                    movement.quantity,
                    movement.stock_before,
                    movement.stock_after,
                    movement.observations,
                ]
            )
        elif movement.movement_type == MOVE_ADJUSTMENT:
            adjustment_net += movement.stock_delta
            adjustment_rows.append(
                [
                    movement.created_at,
                    movement.item_name_snapshot,
                    movement.stock_delta,
                    movement.stock_before,
                    movement.stock_after,
                    movement.observations,
                ]
            )

    top_rows = session.execute(
        select(
            StockMovement.item_name_snapshot,
            func.sum(
                StockMovement.quantity
            ).label("total"),
            func.sum(
                case(
                    (StockMovement.movement_type == MOVE_DELIVERY, StockMovement.quantity),
                    else_=0,
                )
            ).label("delivered"),
            func.sum(
                case(
                    (StockMovement.movement_type == MOVE_RETURN, StockMovement.quantity),
                    else_=0,
                )
            ).label("returned"),
        )
        .where(
            StockMovement.created_at >= start_of_day(start),
            StockMovement.created_at <= end_of_day(end),
            StockMovement.movement_type.in_([MOVE_DELIVERY, MOVE_RETURN]),
            StockMovement.is_voided.is_(False),
        )
        .group_by(StockMovement.item_name_snapshot)
        .order_by(func.sum(StockMovement.quantity).desc())
        .limit(15)
    ).all()
    top_items_rows = [
        [name, int(delivered or 0), int(returned or 0), int(total or 0)]
        for name, total, delivered, returned in top_rows
    ]

    delivery_rows = [
        [d.crew.name, 1, d.total_units, 1 if d.iclass_status == ICLASS_PENDING else 0]
        for d in deliveries
    ]
    per_crew: dict[str, list[int]] = {}
    for crew_name, deliveries_count, units, pending in delivery_rows:
        row = per_crew.setdefault(crew_name, [0, 0, 0])
        row[0] += deliveries_count
        row[1] += units
        row[2] += pending
    delivery_crew_rows = [[name, *vals] for name, vals in sorted(per_crew.items())]

    return_rows = []
    for record in returns:
        for det in record.details:
            return_rows.append(
                [
                    record.created_at,
                    record.crew.name,
                    det.item.name,
                    det.quantity,
                    CONDITIONS.get(det.condition, det.condition),
                ]
            )
    consumption_table = [
        [r["crew"], r["item"], r["quantity"]] for r in consumption_rows
    ]
    pending_rows = [
        [d.code, d.created_at, d.crew.name, d.technician, d.total_units]
        for d in deliveries
        if d.iclass_status == ICLASS_PENDING
    ]
    general_rows = [
        ["Entregas realizadas", len(deliveries)],
        ["Unidades entregadas", sum(d.total_units for d in deliveries)],
        ["Devoluciones realizadas", len(returns)],
        ["Unidades devueltas", sum(r.total_units for r in returns)],
        ["Unidades consumibles entregadas", sum(consumed.values())],
        ["Unidades ingresadas al stock", income_units],
        ["Ajustes por recuento o manuales", len(adjustment_rows)],
        ["Variacion neta por ajustes", adjustment_net],
        ["Entregas pendientes de IClass", len(pending_rows)],
    ]

    sections = [
        {
            "key": "resumen_general",
            "title": "Resumen general del mes",
            "columns": ["Indicador", "Valor"],
            "rows": general_rows,
            "totals": False,
        },
        {
            "key": "entregas_cuadrilla",
            "title": "Entregas por cuadrilla",
            "columns": [
                "Cuadrilla",
                "Entregas",
                "Unidades entregadas",
                "Pendientes IClass",
            ],
            "rows": delivery_crew_rows,
            "totals": True,
        },
        {
            "key": "articulos_movimiento",
            "title": "Articulos con mayor movimiento",
            "columns": [
                "Articulo",
                "Unidades entregadas",
                "Unidades devueltas",
                "Movimiento total",
            ],
            "rows": top_items_rows,
            "totals": True,
        },
        {
            "key": "ingresos",
            "title": "Ingresos de stock",
            "columns": [
                "Fecha y hora",
                "Articulo",
                "Cantidad",
                "Stock anterior",
                "Stock posterior",
                "Observaciones",
            ],
            "rows": income_rows,
            "totals": True,
        },
        {
            "key": "devoluciones",
            "title": "Devoluciones del mes",
            "columns": ["Fecha y hora", "Cuadrilla", "Articulo", "Cantidad", "Estado"],
            "rows": return_rows,
            "totals": True,
        },
        {
            "key": "consumos",
            "title": "Consumos del mes",
            "columns": ["Cuadrilla", "Articulo", "Cantidad"],
            "rows": consumption_table,
            "totals": True,
        },
        {
            "key": "ajustes",
            "title": "Ajustes de inventario",
            "columns": [
                "Fecha y hora",
                "Articulo",
                "Variacion",
                "Stock anterior",
                "Stock posterior",
                "Motivo",
            ],
            "rows": adjustment_rows,
            "totals": False,
        },
        {
            "key": "pendientes_iclass",
            "title": "Entregas pendientes de IClass",
            "columns": [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Unidades",
            ],
            "rows": pending_rows,
            "totals": False,
        },
    ]
    return {
        "kind": "monthly",
        "title": "Informe mensual de movimientos",
        "subtitle": f"Mes: {start.strftime('%m/%Y')}",
        "filters": [("Mes", start.strftime("%m/%Y"))],
        "generated_at": now(),
        "sections": sections,
    }


def report_historical(
    session: Session,
    *,
    start: date,
    end: date,
    crew_id: int | None = None,
    item_id: int | None = None,
    movement_types: list[str] | None = None,
    search: str = "",
) -> dict:
    movements = list_movements(
        session,
        date_from=start,
        date_to=end,
        crew_id=crew_id,
        item_id=item_id,
        movement_types=movement_types,
        search=search,
    )
    summary: dict[str, dict] = {}
    movement_rows = []
    for movement in movements:
        if movement.is_voided:
            status = "Anulado"
        else:
            status = "Vigente"
        movement_rows.append(
            [
                movement.created_at,
                MOVEMENT_TYPES.get(movement.movement_type, movement.movement_type),
                movement.item_name_snapshot,
                movement.quantity,
                movement.stock_delta,
                movement.stock_before,
                movement.stock_after,
                movement.crew.name if movement.crew else "",
                movement.technician,
                movement.user.username if movement.user else "",
                status,
                movement.observations,
            ]
        )
        key = MOVEMENT_TYPES.get(movement.movement_type, movement.movement_type)
        row = summary.setdefault(key, {"count": 0, "units": 0, "delta": 0})
        row["count"] += 1
        row["units"] += movement.quantity
        row["delta"] += movement.stock_delta
    summary_rows = [
        [key, values["count"], values["units"], values["delta"]]
        for key, values in sorted(summary.items())
    ]
    filters = [("Desde", fmt_date(start)), ("Hasta", fmt_date(end))]
    if crew_id:
        crew = session.get(Crew, crew_id)
        if crew:
            filters.append(("Cuadrilla", crew.name))
    if item_id:
        item = session.get(Item, item_id)
        if item:
            filters.append(("Articulo", item.name))
    if movement_types:
        filters.append(
            ("Tipos", ", ".join(MOVEMENT_TYPES.get(t, t) for t in movement_types))
        )
    if search.strip():
        filters.append(("Busqueda", search.strip()))
    return {
        "kind": "historical",
        "title": "Informe historico de movimientos",
        "subtitle": f"Periodo: {fmt_date(start)} al {fmt_date(end)}",
        "filters": filters,
        "generated_at": now(),
        "sections": [
            {
                "key": "resumen_tipos",
                "title": "Resumen por tipo de movimiento",
                "columns": [
                    "Tipo de movimiento",
                    "Movimientos",
                    "Unidades afectadas",
                    "Variacion neta de stock",
                ],
                "rows": summary_rows,
                "totals": True,
            },
            {
                "key": "movimientos",
                "title": "Detalle de movimientos",
                "columns": [
                    "Fecha y hora",
                    "Tipo",
                    "Articulo",
                    "Cantidad",
                    "Variacion stock",
                    "Stock anterior",
                    "Stock posterior",
                    "Cuadrilla",
                    "Tecnico",
                    "Usuario",
                    "Estado",
                    "Observaciones",
                ],
                "rows": movement_rows,
                "totals": False,
            },
        ],
    }
