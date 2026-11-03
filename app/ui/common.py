"""Componentes visuales reutilizables."""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.errors import AppError
from app.ui.icons import make_icon
from app.ui.theme import COLORS, MESSAGE_BOX_STYLE
from app.utils.dates import fmt_date, fmt_datetime
from app.utils.numbers import fmt_int, fmt_signed

__all__ = [
    "AppMessageBox",
    "Card",
    "StatCard",
    "PageHeader",
    "SortItem",
    "SearchLineEdit",
    "make_button",
    "make_item",
    "set_row",
    "setup_table",
    "finish_table",
    "clear_table",
    "selected_ids",
    "selected_id",
    "show_error",
    "show_info",
    "show_warning",
    "confirm",
    "ask_reason",
    "FormDialog",
    "EmptyState",
    "chip",
    "section_title",
    "hline",
    "format_value",
    "COLORS",
    "fmt_date",
    "fmt_datetime",
    "fmt_int",
    "fmt_signed",
]


class AppMessageBox(QMessageBox):
    """Mensaje modal con contraste y apariencia independientes del tema de Windows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AppMessageBox")
        self.setStyleSheet(MESSAGE_BOX_STYLE)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#ffffff"))
        palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.Text, QColor(COLORS["text"]))
        palette.setColor(QPalette.Button, QColor("#ffffff"))
        palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
        palette.setColor(QPalette.Highlight, QColor("#bfdbfe"))
        palette.setColor(QPalette.HighlightedText, QColor(COLORS["text"]))
        self.setPalette(palette)


class Card(QFrame):
    def __init__(self, parent=None, margins: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(margins, margins, margins, margins)
        self.layout.setSpacing(spacing)


class StatCard(QFrame):
    clicked = Signal()

    def __init__(self, title: str, icon: str, accent: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(104)
        self._accent = accent
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(14)

        icon_box = QFrame()
        icon_box.setFixedSize(46, 46)
        icon_box.setStyleSheet(
            f"background: {accent}18; border-radius: 12px; border: none;"
        )
        icon_layout = QVBoxLayout(icon_box)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel()
        icon_label.setPixmap(make_icon(icon, accent, 24).pixmap(24, 24))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(icon_label)
        self._layout.addWidget(icon_box, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("StatTitle")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("StatValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("StatHint")
        self.hint_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.value_label)
        text_layout.addWidget(self.hint_label)
        self._layout.addLayout(text_layout, 1)

    def set_value(self, value, hint: str | None = None) -> None:
        self.value_label.setText(str(value))
        if hint is not None:
            self.hint_label.setText(hint)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        text.addWidget(self.title_label)
        if subtitle:
            text.addWidget(self.subtitle_label)
        layout.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions, 0)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


class SortItem(QTableWidgetItem):
    def __init__(self, text: str, sort_value=None):
        super().__init__(text)
        self.setData(Qt.UserRole, sort_value if sort_value is not None else text)

    def __lt__(self, other):  # noqa: N802
        left = self.data(Qt.UserRole)
        right = other.data(Qt.UserRole)
        try:
            return left < right
        except TypeError:
            return str(left or "") < str(right or "")


def make_item(
    text,
    *,
    sort_value=None,
    color: str | None = None,
    bg: str | None = None,
    bold: bool = False,
    align=None,
    tooltip: str | None = None,
    data=None,
) -> QTableWidgetItem:
    item = SortItem("" if text is None else str(text), sort_value)
    if color:
        item.setForeground(QColor(color))
    if bg:
        item.setBackground(QColor(bg))
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if align is not None:
        item.setTextAlignment(align)
    if tooltip:
        item.setToolTip(tooltip)
    if data is not None:
        item.setData(Qt.UserRole + 1, data)
    return item


def set_row(table: QTableWidget, row: int, values: list[QTableWidgetItem]) -> None:
    for column, item in enumerate(values):
        table.setItem(row, column, item)


def setup_table(
    table: QTableWidget,
    headers: list[str],
    *,
    stretch: int = 0,
    column_widths: dict[int, int] | None = None,
    row_height: int = 38,
) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(False)
    table.setWordWrap(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for index in range(len(headers)):
        if column_widths and index in column_widths:
            header.setSectionResizeMode(index, QHeaderView.Fixed)
            table.setColumnWidth(index, column_widths[index])
        elif index == stretch:
            header.setSectionResizeMode(index, QHeaderView.Stretch)
        else:
            header.setSectionResizeMode(index, QHeaderView.ResizeToContents)


def finish_table(table: QTableWidget, sortable: bool = True) -> None:
    table.setSortingEnabled(sortable)
    if sortable and table.rowCount() > 0:
        table.sortItems(0, Qt.AscendingOrder)


def clear_table(table: QTableWidget) -> None:
    table.setSortingEnabled(False)
    table.setRowCount(0)


def selected_id(table: QTableWidget) -> int | None:
    rows = table.selectionModel().selectedRows() if table.selectionModel() else []
    if not rows:
        return None
    item = table.item(rows[0].row(), 0)
    if item is None:
        return None
    value = item.data(Qt.UserRole + 1)
    if value is None:
        try:
            return int(item.text())
        except (TypeError, ValueError):
            return None
    return int(value)


def selected_ids(table: QTableWidget, id_column: int = 0) -> list[int]:
    ids = []
    for index in table.selectionModel().selectedRows():
        item = table.item(index.row(), id_column)
        if item is not None and item.data(Qt.UserRole + 1) is not None:
            ids.append(int(item.data(Qt.UserRole + 1)))
    return ids


def make_button(
    text: str,
    kind: str = "secondary",
    icon: str | None = None,
    icon_color: str | None = None,
    parent=None,
) -> QPushButton:
    button = QPushButton(text, parent)
    button.setProperty("class", kind)
    if kind == "primary":
        icon_color = icon_color or "#ffffff"
    icon_color = icon_color or "#475569"
    if icon:
        button.setIcon(make_icon(icon, icon_color, 16))
        button.setIconSize(QSize(16, 16))
    button.setCursor(Qt.PointingHandCursor)
    return button


class SearchLineEdit(QLineEdit):
    def __init__(self, placeholder: str = "Buscar...", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setProperty("search", "true")
        self.addAction(make_icon("search", "#64748b", 16), QLineEdit.LeadingPosition)
        self.setClearButtonEnabled(True)


class FormDialog(QDialog):
    def __init__(self, title: str, subtitle: str = "", parent=None, width: int = 520):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        root.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("PageSubtitle")
            sub.setWordWrap(True)
            root.addWidget(sub)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e2e8f0;")
        root.addWidget(line)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        root.addLayout(self.body, 1)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(10)
        root.addLayout(self.form)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.footer.addStretch(1)
        self.cancel_button = make_button("Cancelar", "secondary")
        self.cancel_button.clicked.connect(self.reject)
        self.primary_button = make_button("Guardar", "primary")
        self.primary_button.clicked.connect(self._try_accept)
        self.footer.addWidget(self.cancel_button)
        self.footer.addWidget(self.primary_button)
        root.addLayout(self.footer)
        self._validator: Callable[[], None] | None = None

    def set_validator(self, validator: Callable[[], None]) -> None:
        self._validator = validator

    def set_primary_text(self, text: str) -> None:
        self.primary_button.setText(text)

    def _try_accept(self) -> None:
        if self._validator:
            try:
                self._validator()
            except AppError as exc:
                show_error(self, exc)
                return
        self.accept()


class EmptyState(QWidget):
    def __init__(self, title: str, text: str = "", icon: str = "box", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(make_icon(icon, "#cbd5e1", 36).pixmap(36, 36))
        icon_label.setAlignment(Qt.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("EmptyTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        if text:
            text_label = QLabel(text)
            text_label.setObjectName("EmptyText")
            text_label.setAlignment(Qt.AlignCenter)
            text_label.setWordWrap(True)
            layout.addWidget(text_label)


def chip(text: str, kind: str = "info") -> QLabel:
    label = QLabel(text)
    mapping = {
        "info": "BadgeInfo",
        "warning": "BadgeWarning",
        "success": "BadgeSuccess",
        "danger": "BadgeDanger",
    }
    label.setObjectName(mapping.get(kind, "BadgeInfo"))
    label.setAlignment(Qt.AlignCenter)
    return label


def section_title(text: str, subtitle: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(1)
    title = QLabel(text)
    title.setObjectName("SectionTitle")
    layout.addWidget(title)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("TinyMuted")
        layout.addWidget(sub)
    return widget


def hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("border: none; border-top: 1px solid #e2e8f0;")
    return line


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return fmt_datetime(value)
    if isinstance(value, date):
        return fmt_date(value)
    if isinstance(value, bool):
        return "Si" if value else "No"
    if isinstance(value, int):
        return fmt_int(value)
    return str(value)


def show_error(parent, error: Exception) -> None:
    if isinstance(error, AppError):
        message = str(error)
    else:
        message = f"Ocurrio un error inesperado:\n{error}"
    box = AppMessageBox(parent)
    box.setWindowTitle("No se pudo completar la operacion")
    box.setIcon(QMessageBox.Warning)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec()


def show_info(parent, message: str, title: str = "Operacion completada") -> None:
    box = AppMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Information)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec()


def show_warning(parent, message: str, title: str = "Atencion") -> None:
    box = AppMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Warning)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec()


def confirm(parent, title: str, message: str, confirm_text: str = "Confirmar", danger: bool = False) -> bool:
    box = AppMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    yes = box.button(QMessageBox.Yes)
    no = box.button(QMessageBox.No)
    if yes:
        yes.setText(confirm_text)
        if danger:
            yes.setProperty("class", "danger")
    if no:
        no.setText("Cancelar")
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


class ReasonDialog(FormDialog):
    def __init__(self, title: str, message: str, label: str = "Motivo", parent=None):
        super().__init__(title, message, parent, width=500)
        self.reason = QTextEdit()
        self.reason.setPlaceholderText("Describa el motivo...")
        self.reason.setFixedHeight(100)
        self.form.addRow(label, self.reason)
        self.set_primary_text("Continuar")
        self.set_validator(self._validate)

    def _validate(self) -> None:
        if not self.reason.toPlainText().strip():
            from app.errors import ValidationError

            raise ValidationError("El motivo es obligatorio.")

    def value(self) -> str:
        return self.reason.toPlainText().strip()


def ask_reason(parent, title: str, message: str, label: str = "Motivo") -> str | None:
    dialog = ReasonDialog(title, message, label, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.value()
    return None
