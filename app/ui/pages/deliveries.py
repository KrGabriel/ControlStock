"""Registro y consulta de entregas a cuadrillas."""
from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
)

from app.db.database import session_scope
from app.domain import (
    DELIVERY_ACTIVE,
    DELIVERY_VOIDED,
    ICLASS_LOADED,
    ICLASS_PENDING,
)
from app.errors import AppError
from app.services.crews import crew_options
from app.services.deliveries import create_delivery, list_deliveries, void_delivery
from app.session import get_current_user
from app.ui.common import (
    Card,
    FormDialog,
    PageHeader,
    SearchLineEdit,
    ask_reason,
    clear_table,
    confirm,
    finish_table,
    make_button,
    make_item,
    selected_id,
    set_row,
    setup_table,
    show_error,
    show_info,
    show_warning,
    fmt_datetime,
    fmt_int,
)
from app.ui.dialogs.delivery_dialogs import DeliveryDetailDialog, ItemPickerDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS


class NewDeliveryDialog(FormDialog):
    def __init__(self, crews: list[tuple[int, str]], parent=None):
        super().__init__(
            "Nueva entrega",
            "Registre la salida de materiales hacia una cuadrilla. "
            "Los consumibles se descuentan y los reutilizables quedan asignados.",
            parent,
            width=760,
        )
        self.set_primary_text("Registrar entrega")
        self.lines: dict[int, dict] = {}
        self.crew_combo = QComboBox()
        for crew_id, name in crews:
            self.crew_combo.addItem(name, crew_id)
        self.technician = QLineEdit()
        self.technician.setPlaceholderText("Nombre del tecnico responsable")
        self.when = QDateTimeEdit(QDateTime.currentDateTime())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(62)
        self.notes.setPlaceholderText("Observaciones opcionales")
        self.form.addRow("Cuadrilla *", self.crew_combo)
        self.form.addRow("Tecnico *", self.technician)
        self.form.addRow("Fecha y hora", self.when)
        self.form.addRow("Observaciones", self.notes)

        body_head = QHBoxLayout()
        body_title = QLabel("Articulos de la entrega")
        body_title.setObjectName("SectionTitle")
        body_head.addWidget(body_title, 1)
        add_button = make_button("Agregar articulo", "secondary", "plus")
        add_button.clicked.connect(self._add_item)
        body_head.addWidget(add_button)
        remove_button = make_button("Quitar", "secondary", "trash")
        remove_button.clicked.connect(self._remove_item)
        body_head.addWidget(remove_button)
        self.body.addLayout(body_head)

        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Articulo", "Tipo", "Disponible", "Cantidad"],
            stretch=0,
            column_widths={2: 90, 3: 90},
        )
        self.table.setMinimumHeight(240)
        self.body.addWidget(self.table)
        self.total_label = QLabel("Sin articulos agregados")
        self.total_label.setObjectName("Muted")
        self.body.addWidget(self.total_label)
        self.set_validator(self._validate)

    def _add_item(self) -> None:
        picker = ItemPickerDialog(self)
        if picker.exec() != QDialog.DialogCode.Accepted or picker.selected_item_id is None:
            return
        item_id = picker.selected_item_id
        existing = self.lines.get(item_id)
        try:
            with session_scope() as session:
                from app.services.inventory import get_item

                item = get_item(session, item_id)
                available = item.qty_available
                item_type = item.item_type
                name = item.name
        except Exception as exc:
            show_error(self, exc)
            return
        current = existing["quantity"] if existing else 0
        quantity = current + picker.selected_quantity
        if quantity > available:
            show_warning(
                self,
                f"La cantidad total de '{name}' supera el stock disponible ({fmt_int(available)}).",
            )
            return
        self.lines[item_id] = {
            "name": name,
            "quantity": quantity,
            "available": available,
            "item_type": item_type,
        }
        self._render_lines()

    def _remove_item(self) -> None:
        item_id = selected_id(self.table)
        if item_id is None:
            return
        self.lines.pop(item_id, None)
        self._render_lines()

    def _render_lines(self) -> None:
        table = self.table
        clear_table(table)
        rows = list(self.lines.items())
        table.setRowCount(len(rows))
        for row, (item_id, data) in enumerate(rows):
            set_row(
                table,
                row,
                [
                    make_item(data["name"], data=item_id),
                    make_item("Reutilizable" if data["item_type"] == "REUSABLE" else "Consumible"),
                    make_item(fmt_int(data["available"]), sort_value=data["available"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(fmt_int(data["quantity"]), sort_value=data["quantity"], align=Qt.AlignRight | Qt.AlignVCenter),
                ],
            )
        finish_table(table, sortable=False)
        total_items = len(rows)
        total_units = sum(data["quantity"] for data in self.lines.values())
        self.total_label.setText(
            f"{total_items} articulo(s) | {fmt_int(total_units)} unidad(es)"
            if total_items
            else "Sin articulos agregados"
        )

    def _validate(self) -> None:
        from app.errors import ValidationError

        if self.crew_combo.currentData() is None:
            raise ValidationError("Seleccione una cuadrilla activa.")
        if len(self.technician.text().strip()) < 2:
            raise ValidationError("Ingrese el nombre del tecnico responsable.")
        if not self.lines:
            raise ValidationError("Agregue al menos un articulo a la entrega.")

    def values(self) -> dict:
        return {
            "crew_id": self.crew_combo.currentData(),
            "technician": self.technician.text(),
            "lines": [(item_id, data["quantity"]) for item_id, data in self.lines.items()],
            "notes": self.notes.toPlainText(),
            "occurred_at": self.when.dateTime().toPython(),
        }


class DeliveriesPage(BasePage):
    page_key = "deliveries"
    title = "Entregas"
    subtitle = "Salidas de materiales hacia las cuadrillas."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Entregas a cuadrillas",
            "Cada entrega actualiza el stock y queda vinculada a la cuadrilla y al tecnico.",
        )
        new_button = make_button("Nueva entrega", "primary", "plus")
        new_button.clicked.connect(self._new_delivery)
        header.add_action(new_button)
        detail_button = make_button("Ver detalle", "secondary", "eye")
        detail_button.clicked.connect(self._open_detail)
        header.add_action(detail_button)
        void_button = make_button("Anular", "secondary", "trash")
        void_button.clicked.connect(self._void_delivery)
        header.add_action(void_button)
        self.root.addWidget(header)

        filter_card = Card(margins=12, spacing=8)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(QLabel("Desde"))
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.dateChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("Hasta"))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.dateChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.date_to)
        self.crew_combo = QComboBox()
        self.crew_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.crew_combo)
        self.iclass_combo = QComboBox()
        self.iclass_combo.addItem("Todo IClass", None)
        self.iclass_combo.addItem("Pendiente de IClass", ICLASS_PENDING)
        self.iclass_combo.addItem("Cargada en IClass", ICLASS_LOADED)
        self.iclass_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.iclass_combo)
        self.status_combo = QComboBox()
        self.status_combo.addItem("Activas", DELIVERY_ACTIVE)
        self.status_combo.addItem("Anuladas", DELIVERY_VOIDED)
        self.status_combo.addItem("Todas", None)
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.status_combo)
        self.search = SearchLineEdit("Codigo o tecnico...")
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
        filter_card.layout.addLayout(filters)
        self.root.addWidget(filter_card)

        table_card = Card(margins=16, spacing=8)
        table_head = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        table_head.addWidget(self.count_label, 1)
        table_card.layout.addLayout(table_head)
        self.table = QTableWidget()
        setup_table(
            self.table,
            [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Articulos",
                "Unidades",
                "Devueltas",
                "IClass",
                "Estado",
            ],
            stretch=3,
            column_widths={0: 150, 1: 125, 4: 70, 5: 75, 6: 75, 7: 150, 8: 85},
        )
        self.table.doubleClicked.connect(self._open_detail)
        table_card.layout.addWidget(self.table, 1)
        self.root.addWidget(table_card, 1)
        self._load_crews()

    def activate(self) -> None:
        self._load_crews()
        self.refresh()

    def _load_crews(self) -> None:
        current = self.crew_combo.currentData()
        self.crew_combo.blockSignals(True)
        self.crew_combo.clear()
        self.crew_combo.addItem("Todas las cuadrillas", None)
        try:
            with session_scope() as session:
                for crew_id, name in crew_options(session):
                    self.crew_combo.addItem(name, crew_id)
        except Exception:
            pass
        index = self.crew_combo.findData(current)
        if index >= 0:
            self.crew_combo.setCurrentIndex(index)
        self.crew_combo.blockSignals(False)

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                deliveries = list_deliveries(
                    session,
                    date_from=self.date_from.date().toPython(),
                    date_to=self.date_to.date().toPython(),
                    crew_id=self.crew_combo.currentData(),
                    iclass_status=self.iclass_combo.currentData(),
                    status=self.status_combo.currentData(),
                    search=self.search.text(),
                )
                rows = []
                for delivery in deliveries:
                    rows.append(
                        {
                            "id": delivery.id,
                            "code": delivery.code,
                            "created_at": delivery.created_at,
                            "crew": delivery.crew.name,
                            "technician": delivery.technician,
                            "items": len(delivery.details),
                            "units": delivery.total_units,
                            "returned": sum(detail.qty_returned for detail in delivery.details),
                            "iclass": delivery.iclass_status,
                            "status": delivery.status,
                        }
                    )
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            if data["status"] == DELIVERY_VOIDED:
                status_text, status_color, status_bg = "Anulada", COLORS["danger"], COLORS["danger_soft"]
                row_color = COLORS["muted"]
            else:
                status_text, status_color, status_bg = "Activa", COLORS["success"], COLORS["success_soft"]
                row_color = None
            if data["iclass"] == ICLASS_LOADED:
                iclass_text, iclass_color, iclass_bg = "Cargada", COLORS["success"], COLORS["success_soft"]
            else:
                iclass_text, iclass_color, iclass_bg = "Pendiente", COLORS["warning"], COLORS["warning_soft"]
            set_row(
                table,
                row,
                [
                    make_item(data["code"], data=data["id"], color=row_color, bold=True),
                    make_item(fmt_datetime(data["created_at"]), color=row_color),
                    make_item(data["crew"], color=row_color),
                    make_item(data["technician"], color=row_color),
                    make_item(fmt_int(data["items"]), sort_value=data["items"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_int(data["units"]), sort_value=data["units"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_int(data["returned"]), sort_value=data["returned"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(iclass_text, color=iclass_color, bg=iclass_bg, bold=True),
                    make_item(status_text, color=status_color, bg=status_bg, bold=True),
                ],
            )
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)} entrega(s)")

    def _new_delivery(self) -> None:
        try:
            with session_scope() as session:
                crews = crew_options(session)
        except Exception as exc:
            show_error(self, exc)
            return
        if not crews:
            show_warning(self, "No hay cuadrillas activas. Cree o reactive una cuadrilla primero.")
            return
        dialog = NewDeliveryDialog(crews, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                delivery = create_delivery(
                    session,
                    user_id=get_current_user().id,
                    **dialog.values(),
                )
                code = delivery.code
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, f"La entrega {code} fue registrada correctamente.")

    def _selected(self) -> int | None:
        delivery_id = selected_id(self.table)
        if delivery_id is None:
            show_warning(self, "Seleccione una entrega de la tabla.")
        return delivery_id

    def _open_detail(self) -> None:
        delivery_id = self._selected()
        if delivery_id is None:
            return
        DeliveryDetailDialog(delivery_id, self).exec()

    def _void_delivery(self) -> None:
        delivery_id = self._selected()
        if delivery_id is None:
            return
        reason = ask_reason(
            self,
            "Anular entrega",
            "La entrega se marcara como anulada y el stock regresara al inventario. "
            "La operacion queda registrada en el historial.",
            "Motivo de la anulacion",
        )
        if reason is None:
            return
        try:
            with session_scope() as session:
                delivery = void_delivery(
                    session, delivery_id, get_current_user().id, reason
                )
                code = delivery.code
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, f"La entrega {code} fue anulada.")
