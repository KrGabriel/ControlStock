from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.database import session_scope
from app.db.models import DeliveryDetail, Item, StockMovement
from app.domain import (
    CONDITION_DAMAGED,
    CONDITION_GOOD,
    ITEM_CONSUMABLE,
    ITEM_REUSABLE,
    MOVE_ADJUSTMENT,
    MOVE_DELIVERY,
    MOVE_INCOME,
)
from app.errors import ConflictError, NotFoundError, ValidationError
from app.services.auth import authenticate, change_password, count_users
from app.services.backups import (
    create_backup,
    list_backups,
    restore_backup,
    validate_backup_file,
)
from app.services.balances import crew_balances
from app.services.counts import (
    confirm_count,
    get_count,
    get_draft,
    save_count_draft,
    start_count,
)
from app.services.crews import crew_summary, set_crew_active
from app.services.deliveries import list_deliveries, void_delivery
from app.services.iclass import (
    mark_loaded,
    pending_deliveries,
    registrations_for_delivery,
    revert_loaded,
)
from app.services.inventory import list_items
from app.services.movements import list_movements
from app.services.reports import report_daily
from app.services.returns import create_return, void_return
from app.services.settings import get_setting
from app.services.stock import (
    change_state,
    register_income,
    void_movement,
    write_off,
)
from app.utils.dates import now
from app.utils.excel import export_report_to_excel
from tests.conftest import make_delivery, make_item, seed_context


def test_admin_authentication_and_password_change(session):
    assert count_users(session) == 1
    with pytest.raises(ValidationError):
        authenticate(session, "admin", "incorrecta")

    user = authenticate(session, "admin", "ClaveSegura123")
    assert user.last_login_at is not None

    with pytest.raises(ValidationError):
        change_password(session, user.id, "incorrecta", "NuevaClave456")

    change_password(session, user.id, "ClaveSegura123", "NuevaClave456")
    session.commit()
    assert authenticate(session, "admin", "NuevaClave456").id == user.id


def test_income_state_change_write_off_and_void_movements(session):
    item = make_item(session, initial_stock=10)
    assert item.qty_available == 10
    assert item.total_units == 10
    income = session.scalar(
        select(StockMovement).where(StockMovement.item_id == item.id, StockMovement.movement_type == MOVE_INCOME)
    )
    assert income is not None and income.quantity == 10

    register_income(session, item_id=item.id, quantity=5, user_id=1, supplier="Proveedor")
    assert item.qty_available == 15

    change_state(
        session,
        item_id=item.id,
        quantity=2,
        from_state="AVAILABLE",
        to_state="REPAIR",
        user_id=1,
        reason="Revision",
    )
    assert item.qty_available == 13
    assert item.qty_repair == 2
    assert item.total_units == 15

    write_off(session, item_id=item.id, quantity=1, reason="Roto", user_id=1)
    assert item.qty_available == 12
    assert item.total_units == 14

    second_income = session.scalar(
        select(StockMovement)
        .where(StockMovement.item_id == item.id, StockMovement.movement_type == MOVE_INCOME)
        .order_by(StockMovement.id.desc())
    )
    void_movement(session, second_income.id, 1, "Error de carga")
    assert item.qty_available == 7
    assert item.total_units == 9


def test_delivery_updates_stock_and_deliveries_are_audited(session):
    _, crew = seed_context(session)
    reusable = make_item(session, name="ONU", initial_stock=10)
    consumable = make_item(
        session, name="Conector", item_type=ITEM_CONSUMABLE, initial_stock=10
    )

    delivery = make_delivery(
        session,
        crew_id=crew.id,
        lines=[(reusable.id, 3), (consumable.id, 2)],
        notes="Entrega de prueba",
    )
    assert reusable.qty_available == 7
    assert reusable.qty_assigned == 3
    assert reusable.total_units == 10
    assert consumable.qty_available == 8
    assert consumable.qty_assigned == 0
    assert delivery.total_units == 5

    balances = crew_balances(session, crew.id)
    assert len(balances) == 1
    assert balances[0]["item_id"] == reusable.id
    assert balances[0]["quantity"] == 3

    movements = list(
        session.scalars(
            select(StockMovement).where(StockMovement.delivery_id == delivery.id)
        ).all()
    )
    assert len(movements) == 2
    assert all(m.movement_type == MOVE_DELIVERY for m in movements)
    assert all(m.stock_delta < 0 for m in movements)


def test_delivery_validations_avoid_negative_or_invalid_stock(session):
    _, crew = seed_context(session)
    item = make_item(session, initial_stock=2)

    with pytest.raises(ValidationError):
        make_delivery(session, crew_id=crew.id, lines=[(item.id, 3)])
    assert item.qty_available == 2

    with pytest.raises(ValidationError):
        make_delivery(session, crew_id=crew.id, lines=[(item.id, 0)])

    with pytest.raises(ValidationError):
        make_delivery(session, crew_id=crew.id, lines=[])

    with pytest.raises(ValidationError):
        make_delivery(session, crew_id=crew.id, lines=[(item.id, 1)], technician="")

    with pytest.raises(NotFoundError):
        make_delivery(session, crew_id=999, lines=[(item.id, 1)])

    assert item.qty_available == 2
    assert list_deliveries(session) == []


def test_returns_use_fifo_and_apply_condition_states(session):
    _, crew = seed_context(session)
    item = make_item(session, initial_stock=10)
    first = make_delivery(session, crew_id=crew.id, lines=[(item.id, 3)])
    second = make_delivery(session, crew_id=crew.id, lines=[(item.id, 4)])

    good_return = create_return(
        session,
        crew_id=crew.id,
        lines=[(item.id, 5, CONDITION_GOOD, "Devuelto completo")],
        user_id=1,
    )
    details = list(
        session.scalars(
            select(DeliveryDetail)
            .where(DeliveryDetail.delivery_id.in_([first.id, second.id]))
            .order_by(DeliveryDetail.delivery_id)
        ).all()
    )
    assert details[0].qty_returned == 3
    assert details[1].qty_returned == 2
    assert item.qty_assigned == 2
    assert item.qty_available == 8
    assert item.total_units == 10
    assert good_return.total_units == 5

    damaged_return = create_return(
        session,
        crew_id=crew.id,
        lines=[(item.id, 2, CONDITION_DAMAGED, "Pantalla rota")],
        user_id=1,
    )
    assert damaged_return.total_units == 2
    assert item.qty_assigned == 0
    assert item.qty_available == 8
    assert item.qty_damaged == 2
    assert item.total_units == 10

    with pytest.raises(ValidationError):
        create_return(
            session,
            crew_id=crew.id,
            lines=[(item.id, 1, CONDITION_GOOD, "")],
            user_id=1,
        )


def test_consumables_cannot_be_returned(session):
    _, crew = seed_context(session)
    item = make_item(
        session, name="Grapa", item_type=ITEM_CONSUMABLE, initial_stock=10
    )
    make_delivery(session, crew_id=crew.id, lines=[(item.id, 2)])

    with pytest.raises(ValidationError):
        create_return(
            session,
            crew_id=crew.id,
            lines=[(item.id, 1, CONDITION_GOOD, "")],
            user_id=1,
        )


def test_delivery_void_rules_and_compensating_movements(session):
    _, crew = seed_context(session)
    item = make_item(session, initial_stock=10)
    delivery = make_delivery(session, crew_id=crew.id, lines=[(item.id, 3)])

    with pytest.raises(ValidationError):
        void_delivery(session, delivery.id, 1, "")

    void_delivery(session, delivery.id, 1, "Entrega duplicada")
    assert delivery.status == "VOIDED"
    assert item.qty_available == 10
    assert item.qty_assigned == 0
    assert item.total_units == 10

    with pytest.raises(ConflictError):
        void_delivery(session, delivery.id, 1, "Nuevamente")

    with_return = make_delivery(session, crew_id=crew.id, lines=[(item.id, 2)])
    create_return(
        session,
        crew_id=crew.id,
        lines=[(item.id, 1, CONDITION_GOOD, "")],
        user_id=1,
    )
    with pytest.raises(ConflictError):
        void_delivery(session, with_return.id, 1, "No permitido")

    marked = make_delivery(session, crew_id=crew.id, lines=[(item.id, 1)])
    mark_loaded(session, marked.id, user_id=1, reference="IC-1")
    with pytest.raises(ConflictError):
        void_delivery(session, marked.id, 1, "No permitido")

    movements = list(
        session.scalars(
            select(StockMovement).where(StockMovement.delivery_id == delivery.id)
        ).all()
    )
    assert any(m.movement_type == "VOID_DELIVERY" for m in movements)


def test_return_void_restores_assignment(session):
    _, crew = seed_context(session)
    item = make_item(session, initial_stock=10)
    delivery = make_delivery(session, crew_id=crew.id, lines=[(item.id, 5)])
    record = create_return(
        session,
        crew_id=crew.id,
        lines=[(item.id, 2, CONDITION_GOOD, "")],
        user_id=1,
    )
    assert item.qty_available == 7
    assert item.qty_assigned == 3

    with pytest.raises(ValidationError):
        void_return(session, record.id, 1, "")

    void_return(session, record.id, 1, "Devolucion cargada por error")
    assert record.status == "VOIDED"
    assert item.qty_available == 5
    assert item.qty_assigned == 5
    assert item.total_units == 10
    detail = session.scalar(
        select(DeliveryDetail).where(DeliveryDetail.delivery_id == delivery.id)
    )
    assert detail.qty_returned == 0

    with pytest.raises(ConflictError):
        void_return(session, record.id, 1, "Repetido")


def test_inventory_count_draft_and_confirmation(session):
    item_a = make_item(session, name="Router A", initial_stock=10)
    item_b = make_item(session, name="Router B", initial_stock=5)

    count = start_count(session, user_id=1, notes="Recuento de prueba")
    assert count.status == "DRAFT"
    assert len(count.details) == 2
    assert get_draft(session).id == count.id
    with pytest.raises(ConflictError):
        start_count(session, user_id=1)

    save_count_draft(
        session,
        count.id,
        {item_a.id: (8, "Faltante detectado")},
        notes="Borrador guardado",
    )
    draft = get_draft(session)
    detail_a = next(d for d in draft.details if d.item_id == item_a.id)
    assert detail_a.physical_qty == 8
    assert detail_a.difference == -2

    confirmed = confirm_count(
        session,
        count.id,
        user_id=1,
        values={item_a.id: (8, "Faltante detectado"), item_b.id: (5, "")},
    )
    assert confirmed.status == "CONFIRMED"
    assert confirmed.total_differences == 1
    assert item_a.qty_available == 8
    assert item_b.qty_available == 5
    assert item_a.total_units == 8

    movement = session.scalar(
        select(StockMovement).where(
            StockMovement.inventory_count_id == count.id,
            StockMovement.movement_type == MOVE_ADJUSTMENT,
        )
    )
    assert movement is not None
    assert movement.stock_delta == -2

    with pytest.raises(ConflictError):
        save_count_draft(session, count.id, {item_a.id: (1, "")})
    with pytest.raises(ConflictError):
        confirm_count(session, count.id, user_id=1)


def test_iclass_workflow_does_not_modify_stock(session):
    _, crew = seed_context(session)
    item = make_item(session, initial_stock=10)
    delivery = make_delivery(session, crew_id=crew.id, lines=[(item.id, 4)])
    available = item.qty_available
    assigned = item.qty_assigned

    assert delivery in pending_deliveries(session)
    mark_loaded(session, delivery.id, user_id=1, reference="IC-2026", notes="Cargada")
    assert delivery.iclass_status == "LOADED"
    assert delivery not in pending_deliveries(session)
    assert item.qty_available == available
    assert item.qty_assigned == assigned

    with pytest.raises(ConflictError):
        mark_loaded(session, delivery.id, user_id=1)

    with pytest.raises(ValidationError):
        revert_loaded(session, delivery.id, user_id=1, reason="")

    revert_loaded(session, delivery.id, user_id=1, reason="Correccion")
    assert delivery.iclass_status == "PENDING"
    assert delivery in pending_deliveries(session)
    assert item.qty_available == available
    assert item.qty_assigned == assigned
    assert len(registrations_for_delivery(session, delivery.id)) == 3


def test_reports_and_excel_export(session, tmp_path):
    _, crew = seed_context(session)
    reusable = make_item(session, name="Router Reporte", initial_stock=10)
    consumable = make_item(
        session, name="Conector Reporte", item_type=ITEM_CONSUMABLE, initial_stock=10
    )
    make_delivery(
        session,
        crew_id=crew.id,
        lines=[(reusable.id, 3), (consumable.id, 2)],
        technician="Tecnico Reporte",
    )
    create_return(
        session,
        crew_id=crew.id,
        lines=[(reusable.id, 1, CONDITION_GOOD, "")],
        user_id=1,
    )

    report = report_daily(session, now().date())
    assert report["title"]
    assert any(section["key"] == "entregas" and section["rows"] for section in report["sections"])
    assert any(section["key"] == "consumos" and section["rows"] for section in report["sections"])

    path = export_report_to_excel(report, tmp_path / "informe.xlsx")
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_crew_summary_and_deactivation_guard(session):
    _, crew = seed_context(session)
    item = make_item(session, initial_stock=10)
    make_delivery(session, crew_id=crew.id, lines=[(item.id, 2)])

    summary = crew_summary(session, crew.id)
    assert summary["assigned_units"] == 2
    assert summary["assigned_articles"] == 1
    assert summary["delivery_count"] == 1
    assert len(summary["balances"]) == 1

    with pytest.raises(ConflictError):
        set_crew_active(session, crew.id, False)

    create_return(
        session,
        crew_id=crew.id,
        lines=[(item.id, 2, CONDITION_GOOD, "")],
        user_id=1,
    )
    set_crew_active(session, crew.id, False)
    assert crew.is_active is False


def test_backup_validate_and_restore(session):
    item = make_item(session, name="Router Backup", initial_stock=10)
    item_id = item.id
    session.commit()

    with session_scope() as backup_session:
        record = create_backup(
            backup_session,
            user_id=1,
            notes="Copia de prueba",
        )
        backup_path = record.path

    info = validate_backup_file(backup_path)
    assert info["users"] == 1
    assert info["items"] == 1
    assert Path(backup_path).exists()
    assert list_backups(session)[0].path == backup_path

    item.qty_available = 3
    session.commit()
    session.close()

    restored = restore_backup(backup_path, 1)
    assert restored["items"] == 1

    with session_scope() as check:
        restored_item = check.get(Item, item_id)
        assert restored_item is not None
        assert restored_item.qty_available == 10
        assert get_setting(check, "last_restore")


def test_inventory_filters_and_item_history(session):
    _, crew = seed_context(session)
    router = make_item(session, name="Router Filtro", initial_stock=10)
    switch = make_item(session, name="Switch Filtro", initial_stock=1, stock_min=2)
    make_delivery(session, crew_id=crew.id, lines=[(router.id, 2)])

    assert [i.id for i in list_items(session, search="Router")] == [router.id]
    assert [i.id for i in list_items(session, status="LOW")] == [switch.id]
    assert [i.id for i in list_items(session, status="ASSIGNED")] == [router.id]

    history = list_movements(session, item_id=router.id)
    assert len(history) >= 2
    types = {movement.movement_type for movement in history}
    assert {MOVE_INCOME, MOVE_DELIVERY}.issubset(types)
    assert all(movement.item_id == router.id for movement in history)
