"""Formularios de categorias y cuadrillas."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLineEdit, QTextEdit

from app.db.database import session_scope
from app.errors import ValidationError
from app.services.inventory import get_item  # noqa: F401
from app.ui.common import FormDialog, show_error


class CategoryFormDialog(FormDialog):
    def __init__(self, category=None, parent=None):
        editing = category is not None
        super().__init__(
            "Editar categoria" if editing else "Nueva categoria",
            "Las categorias organizan el catalogo y pueden ampliarse en cualquier momento.",
            parent,
            width=480,
        )
        self.set_primary_text("Guardar cambios" if editing else "Crear categoria")
        self.category = category
        self.name_edit = QLineEdit(category.name if category else "")
        self.name_edit.setPlaceholderText("Nombre de la categoria")
        self.description = QTextEdit()
        self.description.setFixedHeight(80)
        self.description.setPlaceholderText("Descripcion opcional")
        if category:
            self.description.setPlainText(category.description)
        self.form.addRow("Nombre *", self.name_edit)
        self.form.addRow("Descripcion", self.description)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text(),
            "description": self.description.toPlainText(),
        }

    def set_validator(self, validator):  # type: ignore[override]
        def wrapped():
            if len(self.name_edit.text().strip()) < 2:
                raise ValidationError("Ingrese un nombre de categoria valido.")
            validator()

        super().set_validator(wrapped)


class CrewFormDialog(FormDialog):
    def __init__(self, crew=None, parent=None):
        editing = crew is not None
        super().__init__(
            "Editar cuadrilla" if editing else "Nueva cuadrilla",
            "Las cuadrillas se identifican por nombre. Los tecnicos se registran en cada entrega.",
            parent,
            width=480,
        )
        self.set_primary_text("Guardar cambios" if editing else "Crear cuadrilla")
        self.crew = crew
        self.name_edit = QLineEdit(crew.name if crew else "")
        self.name_edit.setPlaceholderText("Ej.: Cuadrilla 12")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(80)
        self.notes.setPlaceholderText("Observaciones opcionales")
        if crew:
            self.notes.setPlainText(crew.notes)
        self.active = QCheckBox("Cuadrilla activa")
        self.active.setChecked(crew.is_active if crew else True)
        self.form.addRow("Nombre *", self.name_edit)
        self.form.addRow("Observaciones", self.notes)
        if editing:
            self.form.addRow("", self.active)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text(),
            "notes": self.notes.toPlainText(),
            "is_active": self.active.isChecked(),
        }

    def set_validator(self, validator):  # type: ignore[override]
        def wrapped():
            if len(self.name_edit.text().strip()) < 2:
                raise ValidationError("Ingrese un nombre de cuadrilla valido.")
            validator()

        super().set_validator(wrapped)
