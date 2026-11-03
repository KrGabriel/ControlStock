"""Formularios y dialogos relacionados con articulos."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.database import session_scope
from app.domain import (
    ITEM_CONSUMABLE,
    ITEM_REUSABLE,
    ITEM_TYPES,
    MANUAL_STATES,
    MOVEMENT_TYPES,
    STATE_AVAILABLE,
    STATE_FIELDS,
    STATE_LABELS,
)
from app.errors import ValidationError
from app.services.inventory import get_item, item_history
from app.ui.common import (
    Card,
    FormDialog,
    clear_table,
    finish_table,
    make_button,
    make_item,
    set_row,
    setup_table,
    show_error,
    fmt_int,
    fmt_datetime,
    fmt_signed,
)
from app.ui.theme import COLORS


class ItemFormDialog(FormDialog):
    def __init__(self, categories: list[tuple[int, str]], item_id: int | None = None, parent=None):
        editing = item_id is not None
        super().__init__(
            "Editar articulo" if editing else "Nuevo articulo",
            "Los datos de stock se modifican mediante ingresos, entregas, devoluciones, "
            "recuentos o ajustes para mantener la trazabilidad."
            if editing
            else "Registre el articulo. Si indica stock inicial se generara automaticamente "
            "un movimiento de ingreso.",
            parent,
            width=560,
        )
        self.set_primary_text("Guardar cambios" if editing else "Crear articulo")
        self.item_id = item_id
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ej.: Router TP-Link")
        self.brand_edit = QLineEdit()
        self.brand_edit.setPlaceholderText("Marca o fabricante")
        self.category_combo = QComboBox()
        for category_id, name in categories:
            self.category_combo.addItem(name, category_id)
        self.type_combo = QComboBox()
        self.type_combo.addItem(ITEM_TYPES[ITEM_REUSABLE], ITEM_REUSABLE)
        self.type_combo.addItem(ITEM_TYPES[ITEM_CONSUMABLE], ITEM_CONSUMABLE)
        self.unit_edit = QLineEdit("unidades")
        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 1_000_000)
        self.initial_spin = QSpinBox()
        self.initial_spin.setRange(0, 1_000_000)
        self.current_label = QLabel("")
        self.observations = QTextEdit()
        self.observations.setPlaceholderText("Observaciones opcionales")
        self.observations.setFixedHeight(74)

        self.form.addRow("Nombre *", self.name_edit)
        self.form.addRow("Marca", self.brand_edit)
        self.form.addRow("Categoria *", self.category_combo)
        self.form.addRow("Tipo *", self.type_combo)
        self.form.addRow("Unidad de medida", self.unit_edit)
        self.form.addRow("Stock minimo", self.min_spin)
        if editing:
            self.form.addRow("Stock actual", self.current_label)
        else:
            self.form.addRow("Stock inicial", self.initial_spin)
        self.form.addRow("Observaciones", self.observations)
        self.set_validator(self._validate)

        if editing:
            self._load()

    def _validate(self) -> None:
        if len(self.name_edit.text().strip()) < 2:
            raise ValidationError("El nombre del articulo es obligatorio.")
        if self.category_combo.currentData() is None:
            raise ValidationError("Seleccione una categoria valida.")

    def _load(self) -> None:
        try:
            with session_scope() as session:
                item = get_item(session, self.item_id)
                self.name_edit.setText(item.name)
                self.brand_edit.setText(item.brand)
                index = self.category_combo.findData(item.category_id)
                if index >= 0:
                    self.category_combo.setCurrentIndex(index)
                index = self.type_combo.findData(item.item_type)
                if index >= 0:
                    self.type_combo.setCurrentIndex(index)
                self.unit_edit.setText(item.unit)
                self.min_spin.setValue(item.stock_min)
                self.observations.setPlainText(item.observations)
                self.current_label.setText(
                    f"{fmt_int(item.qty_available)} disponible(s) de {fmt_int(item.total_units)} total(es)"
                )
                self.current_label.setStyleSheet("font-weight: 600; color: #334155;")
        except Exception as exc:
            show_error(self, exc)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text(),
            "brand": self.brand_edit.text(),
            "category_id": self.category_combo.currentData(),
            "item_type": self.type_combo.currentData(),
            "unit": self.unit_edit.text(),
            "stock_min": self.min_spin.value(),
            "observations": self.observations.toPlainText(),
            "initial_stock": self.initial_spin.value() if self.item_id is None else 0,
        }


class ItemDetailDialog(QDialog):
    def __init__(self, item_id: int, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.setWindowTitle("Detalle del articulo")
        self.setModal(True)
        self.resize(980, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("PageTitle")
        self.title_label.setStyleSheet("font-size: 17pt;")
        header.addWidget(self.title_label, 1)
        close = make_button("Cerrar", "secondary")
        close.clicked.connect(self.accept)
        header.addWidget(close)
        root.addLayout(header)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("PageSubtitle")
        root.addWidget(self.subtitle_label)

        info_card = Card(margins=16, spacing=10)
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(24)
        self.info_grid.setVerticalSpacing(8)
        info_card.layout.addLayout(self.info_grid)
        root.addWidget(info_card)

        history_card = Card(margins=16, spacing=8)
        history_title = QLabel("Historial de movimientos")
        history_title.setObjectName("SectionTitle")
        history_card.layout.addWidget(history_title)
        self.history_table = QTableWidget()
        setup_table(
            self.history_table,
            ["Fecha", "Tipo", "Cant.", "Variacion", "Antes", "Despues", "Cuadrilla", "Usuario", "Observaciones"],
            stretch=8,
            column_widths={0: 125, 2: 60, 3: 75, 4: 60, 5: 65, 6: 100, 7: 90},
        )
        history_card.layout.addWidget(self.history_table)
        root.addWidget(history_card, 1)
        self._load()

    def _load(self) -> None:
        try:
            with session_scope() as session:
                item = get_item(session, self.item_id)
                self.title_label.setText(item.name)
                brand = f" - {item.brand}" if item.brand else ""
                self.subtitle_label.setText(
                    f"{item.category.name}{brand}  |  {ITEM_TYPES.get(item.item_type, item.item_type)}"
                )
                fields = [
                    ("Estado", self._status_text(item)),
                    ("Disponible", item.qty_available),
                    ("Entregado", item.qty_assigned),
                    ("En reparacion", item.qty_repair),
                    ("Da?ado", item.qty_damaged),
                    ("Extraviado", item.qty_lost),
                    ("Fuera de servicio", item.qty_out_of_service),
                    ("Total unidades", item.total_units),
                    ("Stock minimo", item.stock_min),
                    ("Unidad", item.unit),
                ]
                for index, (label, value) in enumerate(fields):
                    row = index // 5
                    col = (index % 5) * 2
                    title = QLabel(label.upper())
                    title.setStyleSheet("color: #94a3b8; font-size: 7.5pt; font-weight: 700;")
                    value_label = QLabel(str(value))
                    value_label.setStyleSheet("font-size: 12pt; font-weight: 700; color: #0f172a;")
                    self.info_grid.addWidget(title, row * 2, col)
                    self.info_grid.addWidget(value_label, row * 2 + 1, col)
                if item.observations:
                    obs_title = QLabel("OBSERVACIONES")
                    obs_title.setStyleSheet(
                        "color: #94a3b8; font-size: 7.5pt; font-weight: 700;"
                    )
                    obs = QLabel(item.observations)
                    obs.setWordWrap(True)
                    self.info_grid.addWidget(obs_title, 4, 0)
                    self.info_grid.addWidget(obs, 5, 0, 1, 10)
                movements = item_history(session, item.id)
                self.history_table.setRowCount(len(movements))
                for row, movement in enumerate(movements):
                    color = COLORS["muted"] if movement.is_voided else None
                    set_row(
                        self.history_table,
                        row,
                        [
                            make_item(fmt_datetime(movement.created_at), color=color),
                            make_item(
                                MOVEMENT_TYPES.get(movement.movement_type, movement.movement_type),
                                color=color,
                            ),
                            make_item(fmt_int(movement.quantity), sort_value=movement.quantity, align=Qt.AlignRight | Qt.AlignVCenter, color=color),
                            make_item(fmt_signed(movement.stock_delta), sort_value=movement.stock_delta, align=Qt.AlignRight | Qt.AlignVCenter, color=color),
                            make_item(fmt_int(movement.stock_before), align=Qt.AlignRight | Qt.AlignVCenter, color=color),
                            make_item(fmt_int(movement.stock_after), align=Qt.AlignRight | Qt.AlignVCenter, color=color),
                            make_item(movement.crew.name if movement.crew else "", color=color),
                            make_item(movement.user.username if movement.user else "", color=color),
                            make_item(movement.observations, tooltip=movement.observations, color=color),
                        ],
                    )
                finish_table(self.history_table, sortable=False)
        except Exception as exc:
            show_error(self, exc)

    def _status_text(self, item) -> str:
        mapping = {
            "OK": "Disponible",
            "LOW": "Stock bajo",
            "NO_STOCK": "Sin stock",
            "REPAIR": "Con unidades en reparacion",
            "OUT_OF_SERVICE": "Con unidades fuera de servicio",
            "DAMAGED": "Con unidades da?adas",
            "LOST": "Con unidades extraviadas",
        }
        return mapping.get(item.primary_status, item.primary_status)


class StateChangeDialog(FormDialog):
    def __init__(self, item_id: int, parent=None):
        super().__init__(
            "Cambio de estado",
            "Mueva unidades entre estados del inventario. Las unidades entregadas a cuadrillas "
            "solo se modifican mediante devoluciones.",
            parent,
            width=500,
        )
        self.set_primary_text("Registrar cambio")
        self.item_id = item_id
        self.quantities: dict[str, int] = {}
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                self.item_name = item.name
                self.quantities = {
                    state: int(getattr(item, STATE_FIELDS[state])) for state in MANUAL_STATES
                }
        except Exception as exc:
            show_error(self, exc)
            self.item_name = ""
        self.from_combo = QComboBox()
        for state in MANUAL_STATES:
            self.from_combo.addItem(
                f"{STATE_LABELS[state]} ({self.quantities.get(state, 0)})", state
            )
        self.to_combo = QComboBox()
        for state in MANUAL_STATES:
            self.to_combo.addItem(STATE_LABELS[state], state)
        default_to = STATE_AVAILABLE if self.from_combo.currentData() != STATE_AVAILABLE else "REPAIR"
        index = self.to_combo.findData(default_to)
        if index >= 0:
            self.to_combo.setCurrentIndex(index)
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 1_000_000)
        self.quantity.setValue(1)
        self.reason = QTextEdit()
        self.reason.setFixedHeight(70)
        self.reason.setPlaceholderText("Motivo del cambio de estado (opcional)")
        self.item_label = QLabel(self.item_name)
        self.item_label.setStyleSheet("font-weight: 600;")
        self.form.addRow("Articulo", self.item_label)
        self.form.addRow("Estado de origen", self.from_combo)
        self.form.addRow("Estado de destino", self.to_combo)
        self.form.addRow("Cantidad", self.quantity)
        self.form.addRow("Motivo", self.reason)
        self.from_combo.currentIndexChanged.connect(self._update_max)
        self._update_max()

    def _update_max(self) -> None:
        available = self.quantities.get(self.from_combo.currentData(), 0)
        self.quantity.setMaximum(max(1, available))
        self.quantity.setValue(min(self.quantity.value(), max(1, available)))
        if available == 0:
            self.quantity.setEnabled(False)
        else:
            self.quantity.setEnabled(True)

    def values(self) -> dict:
        return {
            "item_id": self.item_id,
            "from_state": self.from_combo.currentData(),
            "to_state": self.to_combo.currentData(),
            "quantity": self.quantity.value(),
            "reason": self.reason.toPlainText(),
        }

    def set_validator(self, validator):  # type: ignore[override]
        def wrapped():
            if self.from_combo.currentData() == self.to_combo.currentData():
                raise ValidationError("El estado de origen y destino deben ser diferentes.")
            if self.quantity.value() > self.quantities.get(self.from_combo.currentData(), 0):
                raise ValidationError("La cantidad supera las unidades disponibles en ese estado.")
            validator()

        super().set_validator(wrapped)


class WriteOffDialog(FormDialog):
    def __init__(self, item_id: int, parent=None):
        super().__init__(
            "Baja de material",
            "La baja descuenta unidades del stock disponible y conserva el registro en el historial.",
            parent,
            width=500,
        )
        self.set_primary_text("Registrar baja")
        self.item_id = item_id
        self.available = 0
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                self.available = item.qty_available
                self.item_name = item.name
        except Exception as exc:
            show_error(self, exc)
            self.item_name = ""
        self.item_label = QLabel(self.item_name)
        self.item_label.setStyleSheet("font-weight: 600;")
        self.available_label = QLabel(f"{fmt_int(self.available)} unidad(es) disponibles")
        self.quantity = QSpinBox()
        self.quantity.setRange(1, max(1, self.available))
        self.reason = QTextEdit()
        self.reason.setFixedHeight(80)
        self.reason.setPlaceholderText("Motivo obligatorio de la baja")
        self.form.addRow("Articulo", self.item_label)
        self.form.addRow("Disponible", self.available_label)
        self.form.addRow("Cantidad", self.quantity)
        self.form.addRow("Motivo *", self.reason)

    def values(self) -> dict:
        return {
            "item_id": self.item_id,
            "quantity": self.quantity.value(),
            "reason": self.reason.toPlainText(),
        }

    def set_validator(self, validator):  # type: ignore[override]
        def wrapped():
            if not self.reason.toPlainText().strip():
                raise ValidationError("Debe indicar el motivo de la baja.")
            if self.quantity.value() > self.available:
                raise ValidationError("La cantidad supera el stock disponible.")
            validator()

        super().set_validator(wrapped)
