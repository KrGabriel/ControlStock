from __future__ import annotations

import os
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPalette, QValidator
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit

from app.db.database import session_scope
from app.db.models import Item, StockAdjustment, User
from app.services.inventory import create_item, list_categories
from app.session import clear_current_user, set_current_user
from app.ui.common import AppMessageBox
from app.ui.login import LoginWindow
from app.ui.main_window import MainWindow, PAGE_SPECS
from app.ui.pages.inventory import InventoryPage
from app.ui.theme import COLORS, apply_theme


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    yield app


def _current_user(session):
    user = session.query(User).order_by(User.id).first()
    return set_current_user(user)


def _make_item(session, name: str = "Router de prueba"):
    category = list_categories(session)[0]
    return create_item(
        session,
        name=name,
        brand="Marca",
        category_id=category.id,
        item_type="REUSABLE",
        stock_min=1,
        initial_stock=5,
        user_id=1,
    )


def test_login_accepts_valid_credentials_and_rejects_invalid(qapp, session):
    login = LoginWindow("admin")
    captured = []
    login.logged_in.connect(captured.append)

    login.username.setText("admin")
    login.password.setText("incorrecta")
    login._login()
    assert not captured
    assert "incorrect" in login.error_label.text().lower()

    login.password.setText("ClaveSegura123")
    login._login()
    assert captured and captured[0].username == "admin"
    clear_current_user()


def test_create_item_from_inventory_dialog(qapp, session, monkeypatch):
    from app.ui.dialogs.item_dialogs import ItemFormDialog
    from app.ui.pages import inventory as inventory_page

    _current_user(session)
    monkeypatch.setattr(inventory_page, "show_info", lambda *args, **kwargs: None)

    def accept_dialog(self):
        self.name_edit.setText("Router Nuevo")
        self.brand_edit.setText("TP-Link")
        self.unit_edit.setText("unidades")
        self.initial_spin.setValue(4)
        self.accept()
        return self.result()

    monkeypatch.setattr(ItemFormDialog, "exec", accept_dialog)
    page = InventoryPage()
    page._new_item()

    with session_scope() as check:
        item = check.query(Item).filter(Item.name == "Router Nuevo").one()
        assert item.brand == "TP-Link"
        assert item.qty_available == 4
        assert item.stock_min == 0


def test_edit_item_from_inventory_dialog(qapp, session, monkeypatch):
    from app.ui.dialogs.item_dialogs import ItemFormDialog

    _current_user(session)
    item = _make_item(session, "Router Original")
    session.commit()
    page = InventoryPage()
    page.refresh()

    def edit_dialog(self):
        self.name_edit.setText("Router Editado")
        self.brand_edit.setText("Marca Editada")
        self.accept()
        return self.result()

    from app.ui.pages import inventory as inventory_page

    monkeypatch.setattr(inventory_page, "show_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(ItemFormDialog, "exec", edit_dialog)
    page._edit_item()

    with session_scope() as check:
        updated = check.get(Item, item.id)
        assert updated.name == "Router Editado"
        assert updated.brand == "Marca Editada"


def test_cancel_item_creation_does_not_persist(qapp, session, monkeypatch):
    from app.ui.dialogs.item_dialogs import ItemFormDialog
    from app.ui.pages import inventory as inventory_page

    _current_user(session)

    def reject_dialog(self):
        self.name_edit.setText("No debe guardarse")
        self.reject()
        return self.result()

    monkeypatch.setattr(ItemFormDialog, "exec", reject_dialog)
    monkeypatch.setattr(inventory_page, "show_info", lambda *args, **kwargs: None)
    page = InventoryPage()
    page._new_item()

    with session_scope() as check:
        assert check.query(Item).filter(Item.name == "No debe guardarse").first() is None


def test_login_and_main_window_have_no_inherited_grey_label_backgrounds(qapp, session):
    login = LoginWindow("admin")
    login.show()
    qapp.processEvents()
    image = login.grab().toImage()

    title = login.findChild(QLabel, "LoginBrandTitle")
    field = login.findChild(QLabel, "LoginFieldLabel")
    assert title is not None and field is not None

    title_point = title.mapTo(login, QPoint(max(0, title.width() - 4), 4))
    field_point = field.mapTo(login, QPoint(max(0, field.width() - 4), 4))
    assert image.pixelColor(title_point).lightness() < 90
    assert image.pixelColor(field_point).name() == "#ffffff"
    login.hide()


def test_main_window_cards_keep_white_background(qapp, session):
    user = _current_user(session)
    window = MainWindow(user)
    window.show()
    qapp.processEvents()

    cards = [card for card in window.findChildren(QFrame, "Card") if card.isVisible()]
    assert cards
    colors = Counter()
    card_image = cards[0].grab().toImage()
    for y in range(0, card_image.height(), max(1, card_image.height() // 20)):
        for x in range(0, card_image.width(), max(1, card_image.width() // 20)):
            colors[card_image.pixelColor(x, y).name()] += 1
    assert colors.most_common(1)[0][0] == "#ffffff"
    window.hide()


def test_all_main_sections_open_with_consistent_theme(qapp, session):
    user = _current_user(session)
    window = MainWindow(user)
    window.show()
    qapp.processEvents()
    for key, *_ in PAGE_SPECS:
        window.navigate(key, force=True)
        qapp.processEvents()
        assert key in window.pages
        assert window.stack.currentWidget() is window.pages[key]
    window.hide()


def test_delivery_picker_shows_stock_not_item_id(qapp, session):
    from app.ui.dialogs.delivery_dialogs import ItemPickerDialog

    category = list_categories(session)[0]
    stock_by_name = {
        "TP-Link": (11, 10),
        "Grampas": (47, 150),
        "ZTE": (83, 40),
    }
    for name, (item_id, available) in stock_by_name.items():
        session.add(
            Item(
                id=item_id,
                name=name,
                brand="Marca",
                category_id=category.id,
                item_type="CONSUMABLE" if name == "Grampas" else "REUSABLE",
                stock_min=1,
                qty_available=available,
            )
        )
    session.add(
        Item(
            id=99,
            name="Sin stock",
            brand="Marca",
            category_id=category.id,
            item_type="REUSABLE",
            stock_min=0,
            qty_available=0,
        )
    )
    session.commit()

    picker = ItemPickerDialog()
    picker.show()
    qapp.processEvents()
    try:
        assert picker.table.rowCount() == len(stock_by_name)
        rows = {
            picker.table.item(row, 0).text(): row
            for row in range(picker.table.rowCount())
        }
        for name, (item_id, available) in stock_by_name.items():
            row = rows[name]
            picker.table.selectRow(row)
            qapp.processEvents()
            quantity_item = picker.table.item(row, 3)
            assert int(quantity_item.text()) == available
            assert int(quantity_item.data(Qt.UserRole + 1)) == available
            assert picker.quantity.maximum() == available
            assert picker.available_label.text() == f"Disponible: {available}"
            assert int(picker.table.item(row, 0).data(Qt.UserRole + 1)) == item_id

        picker.table.selectRow(rows["TP-Link"])
        picker.quantity.setValue(3)
        picker._accept()
        assert picker.selected_item_id == 11
        assert picker.selected_quantity == 3
    finally:
        picker.hide()


def test_count_editor_numeric_fields_draft_and_confirmation(qapp, session, monkeypatch):
    from app.services.counts import get_count, start_count
    from app.ui.dialogs import count_dialogs
    from app.ui.dialogs.count_dialogs import CountEditorDialog

    _current_user(session)
    category = list_categories(session)[0]
    initial_stock = {
        "ZTE6600 R": 10,
        "Router TP-Link": 15,
        "Grampas": 150,
        "Opcional": 7,
    }
    items = {
        name: create_item(
            session,
            name=name,
            brand="Marca",
            category_id=category.id,
            item_type="CONSUMABLE" if name == "Grampas" else "REUSABLE",
            stock_min=0,
            initial_stock=stock,
            user_id=1,
        )
        for name, stock in initial_stock.items()
    }
    session.commit()
    count = start_count(session, user_id=1)
    session.commit()
    count_id = count.id

    monkeypatch.setattr(count_dialogs, "show_info", lambda *args, **kwargs: None)
    dialog = CountEditorDialog(count_id)
    dialog.show()
    qapp.processEvents()

    def editors_in(current):
        result = {}
        rows = {}
        for row in range(current.table.rowCount()):
            name = current.table.item(row, 0).text()
            editor = current.table.cellWidget(row, 2)
            assert isinstance(editor, QLineEdit)
            assert editor.placeholderText() == "Ingresar cantidad"
            assert editor.validator().validate("-1", 0)[0] == QValidator.Invalid
            assert editor.validator().validate("1.5", 0)[0] == QValidator.Invalid
            assert editor.validator().validate("", 0)[0] == QValidator.Acceptable
            assert editor.validator().validate("0", 0)[0] == QValidator.Acceptable
            result[name] = editor
            rows[name] = row
        return result, rows

    def difference(current, row):
        item = current.table.item(row, 3)
        return item.text(), item.foreground().color().name()

    dialog_two = None
    try:
        editors, rows = editors_in(dialog)
        assert all(editor.text() == "" for editor in editors.values())
        assert all(dialog.table.item(row, 3).text() == "" for row in rows.values())

        editors["ZTE6600 R"].setText("8")
        editors["Router TP-Link"].setText("18")
        editors["Grampas"].setText("0")
        qapp.processEvents()

        assert difference(dialog, rows["ZTE6600 R"]) == ("-2", COLORS["danger"])
        assert difference(dialog, rows["Router TP-Link"]) == ("+3", COLORS["success"])
        assert difference(dialog, rows["Grampas"]) == ("-150", COLORS["danger"])
        assert difference(dialog, rows["Opcional"]) == ("", COLORS["muted"])
        assert dialog.summary_label.text().startswith("Filas contadas: 3 de 4")
        assert "Unidades fisicas: 26" in dialog.summary_label.text()

        session.expire_all()
        for name, stock in initial_stock.items():
            assert session.get(Item, items[name].id).qty_available == stock

        dialog.notes.setPlainText("Borrador UI")
        dialog._save()
        qapp.processEvents()

        with session_scope() as check:
            saved = get_count(check, count_id)
            saved_values = {
                detail.item.name: (detail.physical_qty, detail.difference)
                for detail in saved.details
            }
            assert saved.notes == "Borrador UI"
            assert saved_values["ZTE6600 R"] == (8, -2)
            assert saved_values["Router TP-Link"] == (18, 3)
            assert saved_values["Grampas"] == (0, -150)
            assert saved_values["Opcional"] == (None, None)

        dialog.hide()
        dialog_two = CountEditorDialog(count_id)
        dialog_two.show()
        qapp.processEvents()
        editors, rows = editors_in(dialog_two)
        assert editors["ZTE6600 R"].text() == "8"
        assert editors["Router TP-Link"].text() == "18"
        assert editors["Grampas"].text() == "0"
        assert editors["Opcional"].text() == ""
        assert difference(dialog_two, rows["ZTE6600 R"]) == ("-2", COLORS["danger"])
        assert difference(dialog_two, rows["Router TP-Link"]) == ("+3", COLORS["success"])
        assert difference(dialog_two, rows["Grampas"]) == ("-150", COLORS["danger"])

        editors["Grampas"].setText("150")
        qapp.processEvents()
        assert difference(dialog_two, rows["Grampas"]) == ("0", COLORS["muted"])

        monkeypatch.setattr(count_dialogs, "confirm", lambda *args, **kwargs: True)
        dialog_two._confirm()
        qapp.processEvents()
        assert dialog_two.confirmed is True

        with session_scope() as check:
            confirmed = get_count(check, count_id)
            assert confirmed.status == "CONFIRMED"
            stocks = {detail.item.name: detail.item.qty_available for detail in confirmed.details}
            assert stocks["ZTE6600 R"] == 8
            assert stocks["Router TP-Link"] == 18
            assert stocks["Grampas"] == 150
            assert stocks["Opcional"] == 7
            adjustments = (
                check.query(StockAdjustment)
                .filter(StockAdjustment.inventory_count_id == count_id)
                .all()
            )
            changes = {
                adjustment.item_id: (
                    adjustment.previous_available,
                    adjustment.new_available,
                )
                for adjustment in adjustments
            }
            assert len(changes) == 2
            assert changes[items["ZTE6600 R"].id] == (10, 8)
            assert changes[items["Router TP-Link"].id] == (15, 18)
    finally:
        dialog.hide()
        if dialog_two is not None:
            dialog_two.hide()


def test_message_box_has_light_background_and_dark_text(qapp):
    box = AppMessageBox()
    box.setWindowTitle("Prueba")
    box.setIcon(AppMessageBox.Information)
    box.setText("Mensaje de informacion legible para la prueba de contraste.")
    box.setStandardButtons(AppMessageBox.Ok)
    box.show()
    qapp.processEvents()

    image = box.grab().toImage()
    colors = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            colors[image.pixelColor(x, y).name()] += 1
    assert colors.most_common(1)[0][0] == "#ffffff"
    assert any(color == "#0f172a" for color, _ in colors.most_common(20))
    assert box.palette().color(QPalette.Window).name() == "#ffffff"
    box.hide()
