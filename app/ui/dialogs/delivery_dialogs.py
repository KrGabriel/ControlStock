"""Dialogos de seleccion de articulos, detalle de entregas y devoluciones."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
)

from app.db.database import session_scope
from app.domain import (
    CONDITIONS,
    DELIVERY_ACTIVE,
    ICLASS_ACTIONS,
    ICLASS_STATUSES,
    ITEM_TYPES,
    STATE_AVAILABLE,
)
from app.errors import ValidationError
from app.services.deliveries import get_delivery
from app.services.iclass import registrations_for_delivery
from app.services.inventory import list_categories, list_items
from app.ui.common import (
    Card,
    FormDialog,
    SearchLineEdit,
    clear_table,
    finish_table,
    make_button,
    make_item,
    set_row,
    setup_table,
    show_error,
    show_warning,
    fmt_datetime,
    fmt_int,
)
from app.ui.theme import COLORS


class ItemPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar articulo a la entrega")
        self.setModal(True)
        self.resize(820, 580)
        self.selected_item_id: int | None = None
        self.selected_quantity = 0
        self.selected_name = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        title = QLabel("Seleccionar articulo")
        title.setObjectName("PageTitle")
        title.setStyleSheet("font-size: 16pt;")
        root.addWidget(title)
        subtitle = QLabel("Solo se muestran articulos activos con stock disponible.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        filters = QHBoxLayout()
        self.search = SearchLineEdit("Buscar por nombre o marca...")
        self.search.textChanged.connect(self._load)
        filters.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.addItem("Todas las categorias", None)
        try:
            with session_scope() as session:
                for cat in list_categories(session):
                    self.category.addItem(cat.name, cat.id)
        except Exception as exc:
            show_error(self, exc)
        self.category.currentIndexChanged.connect(self._load)
        filters.addWidget(self.category, 0)
        root.addLayout(filters)

        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Articulo", "Marca", "Categoria", "Disponible", "Tipo"],
            stretch=0,
            column_widths={3: 90},
        )
        self.table.doubleClicked.connect(self._accept)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        qty_label = QLabel("Cantidad a entregar:")
        qty_label.setStyleSheet("font-weight: 600;")
        footer.addWidget(qty_label)
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 1)
        self.quantity.setMinimumWidth(100)
        footer.addWidget(self.quantity)
        self.available_label = QLabel("Seleccione un articulo")
        self.available_label.setObjectName("Muted")
        footer.addWidget(self.available_label)
        footer.addStretch(1)
        cancel = make_button("Cancelar", "secondary")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        add = make_button("Agregar a la entrega", "primary", "plus")
        add.clicked.connect(self._accept)
        footer.addWidget(add)
        root.addLayout(footer)
        self._load()

    def _load(self) -> None:
        try:
            with session_scope() as session:
                items = list_items(
                    session,
                    search=self.search.text(),
                    category_id=self.category.currentData(),
                    include_inactive=False,
                )
        except Exception as exc:
            show_error(self, exc)
            return
        items = [item for item in items if item.qty_available > 0]
        table = self.table
        clear_table(table)
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            set_row(
                table,
                row,
                [
                    make_item(item.name, tooltip=item.observations, data=item.id),
                    make_item(item.brand),
                    make_item(item.category.name if item.category else ""),
                    make_item(
                        fmt_int(item.qty_available),
                        sort_value=item.qty_available,
                        align=Qt.AlignRight | Qt.AlignVCenter,
                        data=item.qty_available,
                    ),
                    make_item(ITEM_TYPES.get(item.item_type, item.item_type)),
                ],
            )
        finish_table(table, sortable=False)
        if items:
            table.selectRow(0)
        else:
            self.quantity.setMaximum(1)
            self.available_label.setText("Sin articulos disponibles")

    def _selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 3)
        if item is None:
            return
        available = int(item.data(Qt.UserRole + 1) or 0)
        self.quantity.setMaximum(max(1, available))
        self.quantity.setValue(1)
        self.available_label.setText(f"Disponible: {fmt_int(available)}")

    def _accept(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            show_warning(self, "Seleccione un articulo de la lista.")
            return
        name_item = self.table.item(rows[0].row(), 0)
        if name_item is None:
            return
        self.selected_item_id = int(name_item.data(Qt.UserRole + 1))
        self.selected_name = name_item.text()
        self.selected_quantity = self.quantity.value()
        self.accept()


class DeliveryDetailDialog(QDialog):
    def __init__(self, delivery_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle de la entrega")
        self.setModal(True)
        self.resize(960, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("PageTitle")
        self.title_label.setStyleSheet("font-size: 17pt;")
        header.addWidget(self.title_label, 1)
        close = make_button("Cerrar", "secondary")
        close.clicked.connect(self.accept)
        header.addWidget(close)
        root.addLayout(header)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("PageSubtitle")
        root.addWidget(self.subtitle)

        info_card = Card(margins=16, spacing=6)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.RichText)
        info_card.layout.addWidget(self.info_label)
        root.addWidget(info_card)

        items_card = Card(margins=16, spacing=6)
        items_title = QLabel("Articulos entregados")
        items_title.setObjectName("SectionTitle")
        items_card.layout.addWidget(items_title)
        self.items_table = QTableWidget()
        setup_table(
            self.items_table,
            ["Articulo", "Marca", "Cantidad", "Devuelto", "Pendiente", "Tipo"],
            stretch=0,
            column_widths={2: 85, 3: 85, 4: 85},
        )
        items_card.layout.addWidget(self.items_table)
        root.addWidget(items_card, 1)

        history_card = Card(margins=16, spacing=6)
        history_title = QLabel("Historial de estado IClass")
        history_title.setObjectName("SectionTitle")
        history_card.layout.addWidget(history_title)
        self.history_table = QTableWidget()
        setup_table(
            self.history_table,
            ["Fecha", "Accion", "Estado anterior", "Estado nuevo", "Usuario", "Referencia", "Observaciones"],
            stretch=6,
            column_widths={0: 125, 4: 90, 5: 110},
        )
        history_card.layout.addWidget(self.history_table)
        root.addWidget(history_card, 1)
        self._load(delivery_id)

    def _load(self, delivery_id: int) -> None:
        try:
            with session_scope() as session:
                delivery = get_delivery(session, delivery_id)
                status_text = "Anulada" if delivery.status != DELIVERY_ACTIVE else "Activa"
                self.title_label.setText(f"Entrega {delivery.code}")
                self.subtitle.setText(
                    f"{fmt_datetime(delivery.created_at)}  |  {delivery.crew.name}  |  "
                    f"Tecnico: {delivery.technician}  |  Estado: {status_text}"
                )
                loaded_by = delivery.loaded_by_user.username if delivery.loaded_by_user else ""
                loaded_at = fmt_datetime(delivery.iclass_loaded_at)
                info_parts = [
                    f"<b>Entrega:</b> {delivery.code}",
                    f"<b>IClass:</b> {ICLASS_STATUSES.get(delivery.iclass_status, delivery.iclass_status)}",
                    f"<b>Unidades:</b> {fmt_int(delivery.total_units)}",
                ]
                if loaded_at:
                    info_parts.append(f"<b>Cargada:</b> {loaded_at} por {loaded_by}")
                if delivery.iclass_reference:
                    info_parts.append(f"<b>Referencia:</b> {delivery.iclass_reference}")
                if delivery.iclass_notes:
                    info_parts.append(f"<b>Notas IClass:</b> {delivery.iclass_notes}")
                if delivery.notes:
                    info_parts.append(f"<b>Observaciones:</b> {delivery.notes}")
                if delivery.void_reason:
                    info_parts.append(
                        f"<b>Anulada:</b> {fmt_datetime(delivery.voided_at)} - {delivery.void_reason}"
                    )
                self.info_label.setText("<br>".join(info_parts))

                self.items_table.setRowCount(len(delivery.details))
                for row, detail in enumerate(delivery.details):
                    pending = detail.quantity - detail.qty_returned if detail.is_reusable else 0
                    set_row(
                        self.items_table,
                        row,
                        [
                            make_item(detail.item_name_snapshot or detail.item.name),
                            make_item(detail.item_brand_snapshot),
                            make_item(fmt_int(detail.quantity), sort_value=detail.quantity, align=Qt.AlignRight | Qt.AlignVCenter),
                            make_item(fmt_int(detail.qty_returned), sort_value=detail.qty_returned, align=Qt.AlignRight | Qt.AlignVCenter),
                            make_item(
                                fmt_int(pending) if detail.is_reusable else "-",
                                sort_value=pending,
                                align=Qt.AlignRight | Qt.AlignVCenter,
                            ),
                            make_item(ITEM_TYPES["REUSABLE" if detail.is_reusable else "CONSUMABLE"]),
                        ],
                    )
                finish_table(self.items_table, sortable=False)

                registrations = registrations_for_delivery(session, delivery_id)
                self.history_table.setRowCount(len(registrations))
                for row, reg in enumerate(registrations):
                    prev_status = ICLASS_STATUSES.get(reg.previous_status, reg.previous_status or "-")
                    new_status = ICLASS_STATUSES.get(reg.new_status, reg.new_status)
                    set_row(
                        self.history_table,
                        row,
                        [
                            make_item(fmt_datetime(reg.created_at)),
                            make_item(ICLASS_ACTIONS.get(reg.action, reg.action)),
                            make_item(prev_status),
                            make_item(new_status),
                            make_item(reg.user.username if reg.user else ""),
                            make_item(reg.reference),
                            make_item(reg.notes, tooltip=reg.notes),
                        ],
                    )
                finish_table(self.history_table, sortable=False)
        except Exception as exc:
            show_error(self, exc)


class ReturnLineDialog(FormDialog):
    def __init__(self, item_name: str, max_quantity: int, item_id: int, parent=None):
        super().__init__(
            "Agregar devolucion",
            "Indique la cantidad y el estado en que regresan las unidades. "
            "Solo se consideran las unidades asignadas a la cuadrilla.",
            parent,
            width=500,
        )
        self.set_primary_text("Agregar a la devolucion")
        self.item_id = item_id
        self.max_quantity = max_quantity
        self.item_label = QLabel(item_name)
        self.item_label.setStyleSheet("font-weight: 600;")
        self.available_label = QLabel(
            f"Pendiente de devolucion: {fmt_int(max_quantity)} unidad(es)"
        )
        self.quantity = QSpinBox()
        self.quantity.setRange(1, max(1, max_quantity))
        self.condition = QComboBox()
        for key, label in CONDITIONS.items():
            self.condition.addItem(label, key)
        self.notes = QTextEdit()
        self.notes.setFixedHeight(70)
        self.notes.setPlaceholderText("Observaciones opcionales")
        self.form.addRow("Articulo", self.item_label)
        self.form.addRow("Asignado", self.available_label)
        self.form.addRow("Cantidad", self.quantity)
        self.form.addRow("Estado de devolucion", self.condition)
        self.form.addRow("Observaciones", self.notes)

    def values(self) -> dict:
        return {
            "item_id": self.item_id,
            "quantity": self.quantity.value(),
            "condition": self.condition.currentData(),
            "notes": self.notes.toPlainText(),
        }

    def set_validator(self, validator):  # type: ignore[override]
        def wrapped():
            if self.quantity.value() <= 0:
                raise ValidationError("La cantidad debe ser mayor que cero.")
            if self.quantity.value() > self.max_quantity:
                raise ValidationError("La cantidad supera las unidades asignadas.")
            validator()

        super().set_validator(wrapped)
