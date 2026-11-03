"""Modulo de inventario principal."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QVBoxLayout,
)

from app.db.database import session_scope
from app.domain import ITEM_TYPES
from app.errors import AppError
from app.services import inventory, stock
from app.services.inventory import get_item, list_categories, list_items
from app.ui.common import (
    Card,
    PageHeader,
    SearchLineEdit,
    clear_table,
    confirm,
    finish_table,
    make_button,
    make_item,
    set_row,
    setup_table,
    show_error,
    show_info,
    show_warning,
    fmt_int,
)
from app.ui.dialogs.item_dialogs import (
    ItemDetailDialog,
    ItemFormDialog,
    StateChangeDialog,
    WriteOffDialog,
)
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS
from app.session import get_current_user

STATUS_FILTERS = [
    ("Todos los estados", "ALL"),
    ("Disponibles", "AVAILABLE"),
    ("Stock bajo", "LOW"),
    ("Sin stock", "NO_STOCK"),
    ("Con unidades en reparacion", "REPAIR"),
    ("Con unidades daÃ±adas", "DAMAGED"),
    ("Con unidades extraviadas", "LOST"),
    ("Con unidades fuera de servicio", "OUT_OF_SERVICE"),
    ("Con unidades entregadas", "ASSIGNED"),
    ("Inactivos", "INACTIVE"),
]

STATUS_STYLE = {
    "OK": ("Disponible", COLORS["success"], COLORS["success_soft"]),
    "LOW": ("Stock bajo", COLORS["warning"], COLORS["warning_soft"]),
    "NO_STOCK": ("Sin stock", COLORS["danger"], COLORS["danger_soft"]),
    "REPAIR": ("En reparacion", "#7c3aed", COLORS["purple_soft"]),
    "OUT_OF_SERVICE": ("Fuera de servicio", "#475569", "#e2e8f0"),
    "DAMAGED": ("DaÃ±ado", "#c2410c", "#ffedd5"),
    "LOST": ("Extraviado", COLORS["danger"], COLORS["danger_soft"]),
}


class InventoryPage(BasePage):
    page_key = "inventory"
    title = "Inventario"
    subtitle = "Catalogo de materiales, equipos y herramientas."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Inventario",
            "Administre articulos, stock minimo y estados sin perder trazabilidad.",
        )
        new_button = make_button("Nuevo articulo", "primary", "plus")
        new_button.clicked.connect(self._new_item)
        header.add_action(new_button)
        income_button = make_button("Ingreso de stock", "secondary", "income")
        income_button.clicked.connect(lambda: self.navigate_requested.emit("stock_in"))
        header.add_action(income_button)
        self.root.addWidget(header)

        filter_card = Card(margins=14, spacing=10)
        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search = SearchLineEdit("Buscar por nombre o marca...")
        self.search.textChanged.connect(self._on_filter_changed)
        filters.addWidget(self.search, 1)
        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.category_combo)
        self.status_combo = QComboBox()
        for label, value in STATUS_FILTERS:
            self.status_combo.addItem(label, value)
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.status_combo)
        self.type_combo = QComboBox()
        self.type_combo.addItem("Todos los tipos", None)
        for key, label in ITEM_TYPES.items():
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.type_combo)
        self.include_inactive = QCheckBox("Incluir inactivos")
        self.include_inactive.setChecked(True)
        self.include_inactive.toggled.connect(lambda _: self.refresh())
        filters.addWidget(self.include_inactive)
        filter_card.layout.addLayout(filters)
        self.root.addWidget(filter_card)

        table_card = Card(margins=16, spacing=10)
        table_header = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        table_header.addWidget(self.count_label, 1)
        self.detail_button = make_button("Ver detalle", "secondary", "eye")
        self.detail_button.clicked.connect(self._open_detail)
        table_header.addWidget(self.detail_button)
        edit_button = make_button("Editar", "secondary", "edit")
        edit_button.clicked.connect(self._edit_item)
        table_header.addWidget(edit_button)
        state_button = make_button("Cambio de estado", "secondary", "refresh")
        state_button.clicked.connect(self._change_state)
        table_header.addWidget(state_button)
        writeoff_button = make_button("Baja", "secondary", "trash")
        writeoff_button.clicked.connect(self._write_off)
        table_header.addWidget(writeoff_button)
        self.toggle_button = make_button("Desactivar", "secondary")
        self.toggle_button.clicked.connect(self._toggle_active)
        table_header.addWidget(self.toggle_button)
        table_card.layout.addLayout(table_header)

        self.table = QTableWidget()
        setup_table(
            self.table,
            [
                "Articulo",
                "Marca",
                "Categoria",
                "Tipo",
                "Disponible",
                "Entregado",
                "Reparacion",
                "Total",
                "Minimo",
                "Estado",
            ],
            stretch=0,
            column_widths={4: 82, 5: 82, 6: 86, 7: 65, 8: 65, 9: 160},
        )
        self.table.doubleClicked.connect(self._open_detail)
        self.table.itemSelectionChanged.connect(self._update_action_state)
        table_card.layout.addWidget(self.table, 1)
        self.root.addWidget(table_card, 1)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(220)
        self._refresh_timer.timeout.connect(self.refresh)
        self._load_categories()

    def activate(self) -> None:
        self._load_categories()
        self.refresh()

    def _load_categories(self) -> None:
        current = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Todas las categorias", None)
        try:
            with session_scope() as session:
                categories = list_categories(session)
                for category in categories:
                    self.category_combo.addItem(category.name, category.id)
        except Exception:
            pass
        index = self.category_combo.findData(current)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def _on_filter_changed(self) -> None:
        self._refresh_timer.start()

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                items = list_items(
                    session,
                    search=self.search.text(),
                    category_id=self.category_combo.currentData(),
                    status=self.status_combo.currentData(),
                    item_type=self.type_combo.currentData(),
                    include_inactive=self.include_inactive.isChecked(),
                )
                rows = []
                for item in items:
                    rows.append(
                        {
                            "id": item.id,
                            "name": item.name,
                            "brand": item.brand,
                            "category": item.category.name if item.category else "",
                            "type": ITEM_TYPES.get(item.item_type, item.item_type),
                            "available": item.qty_available,
                            "assigned": item.qty_assigned,
                            "repair": item.qty_repair,
                            "total": item.total_units,
                            "min": item.stock_min,
                            "status": item.primary_status,
                            "active": item.is_active,
                            "observations": item.observations,
                        }
                    )
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            status_text, color, bg = self._status_style(data["status"], data["active"])
            set_row(
                table,
                row,
                [
                    make_item(data["name"], tooltip=data["observations"], data=data["id"]),
                    make_item(data["brand"]),
                    make_item(data["category"]),
                    make_item(data["type"]),
                    make_item(fmt_int(data["available"]), sort_value=data["available"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(fmt_int(data["assigned"]), sort_value=data["assigned"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(fmt_int(data["repair"]), sort_value=data["repair"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(fmt_int(data["total"]), sort_value=data["total"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(fmt_int(data["min"]), sort_value=data["min"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(status_text, color=color, bg=bg, bold=True),
                ],
            )
        finish_table(table, sortable=True)
        if table.rowCount() > 0:
            table.selectRow(0)
        self.count_label.setText(f"{len(rows)} articulo(s)")
        self._update_action_state()

    def _status_style(self, status: str, active: bool):
        if not active:
            return "Inactivo", COLORS["muted"], "#e2e8f0"
        return STATUS_STYLE.get(status, ("Disponible", COLORS["success"], COLORS["success_soft"]))

    def _current_item_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(Qt.UserRole + 1)) if item else None

    def _require_item(self) -> int | None:
        item_id = self._current_item_id()
        if item_id is None:
            show_warning(self, "Seleccione un articulo de la tabla.")
        return item_id

    def _update_action_state(self) -> None:
        item_id = self._current_item_id()
        self.toggle_button.setEnabled(item_id is not None)
        if item_id is None:
            self.toggle_button.setText("Desactivar")
            return
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                self.toggle_button.setText("Activar" if not item.is_active else "Desactivar")
        except Exception:
            pass

    def _new_item(self) -> None:
        try:
            with session_scope() as session:
                categories = [(c.id, c.name) for c in list_categories(session)]
        except Exception as exc:
            show_error(self, exc)
            return
        dialog = ItemFormDialog(categories)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                values = dialog.values()
                inventory.create_item(
                    session,
                    **values,
                    user_id=get_current_user().id,
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "El articulo fue creado correctamente.")

    def _edit_item(self) -> None:
        item_id = self._require_item()
        if item_id is None:
            return
        try:
            with session_scope() as session:
                categories = [(c.id, c.name) for c in list_categories(session)]
        except Exception as exc:
            show_error(self, exc)
            return
        dialog = ItemFormDialog(categories, item_id=item_id)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                values = dialog.values()
                inventory.update_item(
                    session,
                    item_id,
                    name=values["name"],
                    brand=values["brand"],
                    category_id=values["category_id"],
                    item_type=values["item_type"],
                    stock_min=values["stock_min"],
                    unit=values["unit"],
                    observations=values["observations"],
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()

    def _open_detail(self) -> None:
        item_id = self._require_item()
        if item_id is None:
            return
        dialog = ItemDetailDialog(item_id, self)
        dialog.exec()

    def _change_state(self) -> None:
        item_id = self._require_item()
        if item_id is None:
            return
        dialog = StateChangeDialog(item_id, self)
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                if item.qty_available + item.qty_repair + item.qty_damaged + item.qty_lost + item.qty_out_of_service <= 0:
                    show_warning(self, "El articulo no tiene unidades para cambiar de estado.")
                    return
        except Exception as exc:
            show_error(self, exc)
            return
        dialog.set_validator(lambda: None)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                stock.change_state(
                    session,
                    user_id=get_current_user().id,
                    **dialog.values(),
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "El cambio de estado fue registrado.")

    def _write_off(self) -> None:
        item_id = self._require_item()
        if item_id is None:
            return
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                if item.qty_available <= 0:
                    show_warning(self, "El articulo no tiene stock disponible para dar de baja.")
                    return
        except Exception as exc:
            show_error(self, exc)
            return
        dialog = WriteOffDialog(item_id, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                stock.write_off(
                    session,
                    user_id=get_current_user().id,
                    **dialog.values(),
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "La baja fue registrada correctamente.")

    def _toggle_active(self) -> None:
        item_id = self._require_item()
        if item_id is None:
            return
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                activate = not item.is_active
                name = item.name
        except Exception as exc:
            show_error(self, exc)
            return
        if not activate:
            if not confirm(
                self,
                "Desactivar articulo",
                f"El articulo '{name}' dejara de estar disponible para nuevas entregas. "
                "El historial y los saldos asignados se conservan.",
                "Desactivar",
            ):
                return
        try:
            with session_scope() as session:
                inventory.set_item_active(session, item_id, activate)
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "Articulo activado." if activate else "Articulo desactivado.")
