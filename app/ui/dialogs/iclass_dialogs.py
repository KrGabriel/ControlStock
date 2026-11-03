"""Formulario para marcar una entrega como cargada en IClass."""
from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QTextEdit

from app.ui.common import FormDialog


class IClassMarkDialog(FormDialog):
    def __init__(self, code: str, parent=None):
        super().__init__(
            "Marcar entrega en IClass",
            f"La entrega {code} se marcara como cargada en IClass. "
            "Esta accion no modifica el stock.",
            parent,
            width=520,
        )
        self.set_primary_text("Marcar como cargada")
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("Referencia o numero de carga (opcional)")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(90)
        self.notes.setPlaceholderText("Observaciones de la carga en IClass")
        self.form.addRow("Referencia", self.reference)
        self.form.addRow("Observaciones", self.notes)

    def values(self) -> dict:
        return {
            "reference": self.reference.text(),
            "notes": self.notes.toPlainText(),
        }
