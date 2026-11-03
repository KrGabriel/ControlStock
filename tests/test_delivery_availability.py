from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain import CONDITION_GOOD, ITEM_CONSUMABLE
from app.errors import ValidationError
from app.services.crews import create_crew
from app.services.returns import create_return
from app.services.stock import change_state
from app.utils.dates import now
from tests.conftest import make_delivery, make_item, seed_context


def test_delivery_availability_matches_stock_and_tracks_reusable_and_consumable(session):
    _, crew = seed_context(session)
    tplink = make_item(session, name="TP-Link", initial_stock=10)
    grampas = make_item(
        session, name="Grampas", item_type=ITEM_CONSUMABLE, initial_stock=150
    )
    zte = make_item(session, name="ZTE", initial_stock=40)

    assert tplink.qty_available == 10
    assert grampas.qty_available == 150
    assert zte.qty_available == 40

    when = now()
    first = make_delivery(
        session,
        crew_id=crew.id,
        lines=[(tplink.id, 3), (grampas.id, 20)],
        when=when,
    )

    assert tplink.qty_available == 7
    assert tplink.qty_assigned == 3
    assert tplink.total_units == 10
    assert grampas.qty_available == 130
    assert grampas.qty_assigned == 0
    assert grampas.total_units == 130
    assert zte.qty_available == 40
    assert zte.qty_assigned == 0

    details = {detail.item_id: detail for detail in first.details}
    assert details[tplink.id].is_reusable is True
    assert details[grampas.id].is_reusable is False

    with pytest.raises(ValidationError, match="Disponible: 7"):
        make_delivery(session, crew_id=crew.id, lines=[(tplink.id, 8)], when=when)
    with pytest.raises(ValidationError, match="Disponible: 40"):
        make_delivery(session, crew_id=crew.id, lines=[(zte.id, 41)], when=when)

    second = make_delivery(
        session,
        crew_id=crew.id,
        lines=[(tplink.id, 2), (grampas.id, 5)],
        when=when + timedelta(hours=1),
    )
    assert second.created_at.date() == first.created_at.date()
    assert tplink.qty_available == 5
    assert tplink.qty_assigned == 5
    assert grampas.qty_available == 125
    assert grampas.total_units == 125
    assert zte.qty_available == 40

    create_return(
        session,
        crew_id=crew.id,
        lines=[(tplink.id, 2, CONDITION_GOOD, "Devolucion parcial")],
        user_id=1,
    )
    assert tplink.qty_available == 7
    assert tplink.qty_assigned == 3
    assert tplink.total_units == 10


def test_delivery_availability_excludes_other_crews_repair_and_low_stock(session):
    _, crew = seed_context(session)
    other_crew = create_crew(session, "Cuadrilla de prueba")
    item = make_item(session, name="Equipo compartido", initial_stock=20)

    make_delivery(session, crew_id=other_crew.id, lines=[(item.id, 4)])
    assert item.qty_available == 16
    assert item.qty_assigned == 4

    change_state(
        session,
        item_id=item.id,
        quantity=3,
        from_state="AVAILABLE",
        to_state="REPAIR",
        user_id=1,
        reason="Revision",
    )
    assert item.qty_available == 13
    assert item.qty_repair == 3
    assert item.qty_assigned == 4
    assert item.total_units == 20

    make_delivery(session, crew_id=crew.id, lines=[(item.id, 5)])
    assert item.qty_available == 8
    assert item.qty_assigned == 9
    assert item.qty_repair == 3
    assert item.total_units == 20

    with pytest.raises(ValidationError, match="Disponible: 8"):
        make_delivery(session, crew_id=crew.id, lines=[(item.id, 9)])

    low_stock = make_item(
        session, name="Stock bajo", initial_stock=2, stock_min=5
    )
    make_delivery(session, crew_id=crew.id, lines=[(low_stock.id, 1)])
    assert low_stock.qty_available == 1
    assert low_stock.primary_status == "LOW"

    zero_stock = make_item(session, name="Sin stock", initial_stock=0)
    with pytest.raises(ValidationError, match="Disponible: 0"):
        make_delivery(session, crew_id=crew.id, lines=[(zero_stock.id, 1)])
    assert zero_stock.qty_available == 0
    assert zero_stock.total_units == 0
