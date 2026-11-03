"""Dialogos de ingresos de stock."""
from __future__ import annotations

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
)

from app.db.database import session_scope
from app.errors import ValidationError
from app.services.inventory import get_item, list_items
from app.ui.common import FormDialog, show_error, fmt_int


class IncomeDialog(FormDialog):
    def __init__(self, parent=None, item_id: int | None = None):
        super().__init__(
            "Registrar ingreso de stock",
            "El ingreso aumenta las unidades disponibles y queda registrado en el historial.",
            parent,
            width=540,
        )
        self.set_primary_text("Registrar ingreso")
        self.item_combo = QComboBox()
        try:
            with session_scope() as session:
                for item in list_items(session, include_inactive=False):
                    label = item.name
                    if item.brand:
                        label += f" - {item.brand}"
                    self.item_combo.addItem(label, item.id)
        except Exception as exc:
            show_error(self, exc)
        if item_id is not None:
            index = self.item_combo.findData(item_id)
            if index >= 0:
                self.item_combo.setCurrentIndex(index)
        self.current_label = QLabel("")
        self.current_label.setStyleSheet("font-weight: 600; color: #334155;")
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 1_000_000)
        self.quantity.setValue(1)
        self.supplier = QLineEdit()
        self.supplier.setPlaceholderText("Proveedor o procedencia (opcional)")
        self.when = QDateTimeEdit(QDateTime.currentDateTime())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.observations = QTextEdit()
        self.observations.setFixedHeight(70)
        self.observations.setPlaceholderText("Observaciones opcionales")
        self.form.addRow("Articulo *", self.item_combo)
        self.form.addRow("Stock actual", self.current_label)
        self.form.addRow("Cantidad *", self.quantity)
        self.form.addRow("Proveedor", self.supplier)
        self.form.addRow("Fecha y hora", self.when)
        self.form.addRow("Observaciones", self.observations)
        self.item_combo.currentIndexChanged.connect(self._update_current)
        self.set_validator(self._validate)
        self._update_current()

    def _update_current(self) -> None:
        item_id = self.item_combo.currentData()
        if item_id is None:
            self.current_label.setText("Sin articulos activos")
            return
        try:
            with session_scope() as session:
                item = get_item(session, item_id)
                unit = item.unit or "unidades"
                self.current_label.setText(
                    f"{fmt_int(item.qty_available)} {unit} disponibles"
                )
        except Exception:
            self.current_label.setText("")

    def _validate(self) -> None:
        if self.item_combo.currentData() is None:
            raise ValidationError("Seleccione un articulo activo.")
        if self.quantity.value() <= 0:
            raise ValidationError("La cantidad debe ser mayor que cero.")

    def values(self) -> dict:
        return {
            "item_id": self.item_combo.currentData(),
            "quantity": self.quantity.value(),
            "supplier": self.supplier.text(),
            "observations": self.observations.toPlainText(),
            "occurred_at": self.when.dateTime().toPython(),
        }
