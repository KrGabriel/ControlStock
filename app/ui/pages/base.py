"""Clase base para las paginas del sistema."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget


class BasePage(QWidget):
    changed = Signal()
    navigate_requested = Signal(str)
    page_key = ""
    title = ""
    subtitle = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(16)
        self._loaded = False

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        pass

    def mark_changed(self) -> None:
        self.changed.emit()
