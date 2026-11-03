"""Editor de recuentos fisicos."""
from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
)

from app.db.database import session_scope
from app.domain import COUNT_CONFIRMED, COUNT_DRAFT
from app.errors import AppError
from app.services.counts import (
    confirm_count,
    count_rows,
    get_count,
    save_count_draft,
)
from app.session import get_current_user
from app.ui.common import (
    Card,
    clear_table,
    confirm,
    finish_table,
    make_button,
    make_item,
    set_row,
    setup_table,
    show_error,
    show_info,
    fmt_datetime,
    fmt_int,
    fmt_signed,
)
from app.ui.theme import COLORS


class CountEditorDialog(QDialog):
    def __init__(self, count_id: int, parent=None, read_only: bool = False):
        super().__init__(parent)
        self.count_id = count_id
        self.read_only = read_only
        self.confirmed = False
        self._loading = False
        self._physical_editors: dict[int, QLineEdit] = {}
        self.setWindowTitle("Recuento fisico")
        self.setModal(True)
        self.resize(1060, 760)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("PageTitle")
        self.title_label.setStyleSheet("font-size: 17pt;")
        header.addWidget(self.title_label, 1)
        self.status_label = QLabel("")
        self.status_label.setObjectName("BadgeWarning")
        header.addWidget(self.status_label)
        root.addLayout(header)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("PageSubtitle")
        root.addWidget(self.subtitle)

        info_card = Card(margins=14, spacing=6)
        notes_row = QHBoxLayout()
        notes_row.setSpacing(10)
        notes_label = QLabel("Observaciones generales")
        notes_label.setStyleSheet("font-weight: 600;")
        notes_row.addWidget(notes_label)
        self.notes = QTextEdit()
        self.notes.setFixedHeight(52)
        self.notes.setPlaceholderText("Observaciones del recuento (opcional)")
        notes_row.addWidget(self.notes, 1)
        info_card.layout.addLayout(notes_row)
        self.help_label = QLabel(
            "Escriba directamente en los campos de Cantidad fisica. "
            "Deje una fila vacia para no contarla; ingrese 0 si no hay unidades."
        )
        self.help_label.setObjectName("Muted")
        info_card.layout.addWidget(self.help_label)
        root.addWidget(info_card)

        table_card = Card(margins=12, spacing=6)
        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Articulo", "Stock sistema", "Cantidad fisica", "Diferencia", "Observaciones"],
            stretch=0,
            column_widths={1: 105, 2: 150, 3: 95},
            row_height=36,
        )
        if not read_only:
            self.table.setEditTriggers(
                QTableWidget.DoubleClicked
                | QTableWidget.EditKeyPressed
                | QTableWidget.AnyKeyPressed
            )
        table_card.layout.addWidget(self.table, 1)
        root.addWidget(table_card, 1)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("Muted")
        root.addWidget(self.summary_label)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)
        self.close_button = make_button("Cerrar" if read_only else "Cancelar", "secondary")
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        self.save_button = None
        self.confirm_button = None
        if not read_only:
            self.save_button = make_button("Guardar borrador", "secondary", "save")
            self.save_button.clicked.connect(self._save)
            footer.addWidget(self.save_button)
            self.confirm_button = make_button("Confirmar recuento", "primary", "check")
            self.confirm_button.clicked.connect(self._confirm)
            footer.addWidget(self.confirm_button)
        root.addLayout(footer)
        self._load()

    def _load(self) -> None:
        try:
            with session_scope() as session:
                count = get_count(session, self.count_id)
                status = count.status
                rows = count_rows(count)
                self.notes.setPlainText(count.notes)
                self.title_label.setText(f"Recuento {count.code}")
                parts = [f"Iniciado: {fmt_datetime(count.started_at)}"]
                if count.confirmed_at:
                    parts.append(f"Confirmado: {fmt_datetime(count.confirmed_at)}")
                parts.append(f"Articulos: {len(rows)}")
                self.subtitle.setText("  |  ".join(parts))
        except Exception as exc:
            show_error(self, exc)
            return
        if status == COUNT_CONFIRMED:
            self.read_only = True
            self.status_label.setText("Confirmado")
            self.status_label.setObjectName("BadgeSuccess")
            self.notes.setReadOnly(True)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.close_button.setText("Cerrar")
            if self.save_button is not None:
                self.save_button.hide()
            if self.confirm_button is not None:
                self.confirm_button.hide()
        else:
            self.status_label.setText("Borrador")
            self.status_label.setObjectName("BadgeWarning")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.help_label.setVisible(not self.read_only)

        self._loading = True
        self._physical_editors = {}
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            physical = "" if data["physical"] is None else str(data["physical"])
            difference = data["difference"]
            name_item = make_item(data["name"], data=data["detail"].item_id)
            system_item = make_item(
                fmt_int(data["system"]),
                sort_value=data["system"],
                align=Qt.AlignRight | Qt.AlignVCenter,
            )
            physical_item = make_item(
                physical,
                align=Qt.AlignRight | Qt.AlignVCenter,
            )
            diff_item = make_item(
                "",
                sort_value=difference if difference is not None else 0,
                align=Qt.AlignRight | Qt.AlignVCenter,
            )
            notes_item = make_item(data["notes"], tooltip=data["notes"])
            for item in (name_item, system_item, physical_item, diff_item):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if self.read_only:
                notes_item.setFlags(notes_item.flags() & ~Qt.ItemIsEditable)
            else:
                notes_item.setFlags(notes_item.flags() | Qt.ItemIsEditable)
            set_row(
                table,
                row,
                [name_item, system_item, physical_item, diff_item, notes_item],
            )
            self._apply_difference(diff_item, physical, data["system"])
            if not self.read_only:
                editor = self._make_physical_editor(row, physical)
                table.setCellWidget(row, 2, editor)
                self._physical_editors[row] = editor
        finish_table(table, sortable=False)
        self._loading = False
        self._update_summary()

    def _make_physical_editor(self, row: int, text: str) -> QLineEdit:
        editor = QLineEdit()
        editor.setObjectName("PhysicalQtyEditor")
        editor.setPlaceholderText("Ingresar cantidad")
        editor.setToolTip(
            "Ingrese la cantidad contada. Use 0 si no hay unidades; "
            "deje vacio para no contar esta fila."
        )
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        editor.setMaxLength(10)
        editor.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"[0-9]*"), editor)
        )
        editor.setClearButtonEnabled(True)
        editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        editor.setFixedHeight(30)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setText(text)
        editor.textChanged.connect(
            lambda value, row=row: self._on_physical_changed(row, value)
        )
        return editor

    def _apply_difference(
        self, diff_item, text: str, system: int
    ) -> int | None:
        text = (text or "").strip()
        if not text:
            diff_item.setText("")
            diff_item.setForeground(QColor(COLORS["muted"]))
            font = diff_item.font()
            font.setBold(False)
            diff_item.setFont(font)
            return None
        try:
            physical = int(text)
        except ValueError:
            diff_item.setText("Invalida")
            diff_item.setForeground(QColor(COLORS["danger"]))
            font = diff_item.font()
            font.setBold(False)
            diff_item.setFont(font)
            return None
        difference = physical - system
        diff_item.setText(fmt_signed(difference))
        color = (
            COLORS["success"]
            if difference > 0
            else COLORS["danger"]
            if difference < 0
            else COLORS["muted"]
        )
        diff_item.setForeground(QColor(color))
        font = diff_item.font()
        font.setBold(difference != 0)
        diff_item.setFont(font)
        return difference

    def _on_physical_changed(self, row: int, text: str) -> None:
        if self._loading or self.read_only:
            return
        system_item = self.table.item(row, 1)
        diff_item = self.table.item(row, 3)
        if system_item is None or diff_item is None:
            return
        system = int(system_item.data(Qt.UserRole) or 0)
        self._apply_difference(diff_item, text, system)
        self._update_summary()

    def _physical_text(self, row: int) -> str:
        editor = self._physical_editors.get(row)
        if editor is not None:
            return editor.text().strip()
        item = self.table.item(row, 2)
        return item.text().strip() if item else ""

    def _update_summary(self) -> None:
        entered = 0
        differences = 0
        units = 0
        for row in range(self.table.rowCount()):
            text = self._physical_text(row)
            if not text:
                continue
            try:
                physical = int(text)
            except ValueError:
                continue
            system_item = self.table.item(row, 1)
            system = int(system_item.data(Qt.UserRole) or 0) if system_item else 0
            entered += 1
            if physical != system:
                differences += 1
            units += physical
        self.summary_label.setText(
            f"Filas contadas: {fmt_int(entered)} de {fmt_int(self.table.rowCount())}"
            f"  |  Con diferencia: {fmt_int(differences)}  |  Unidades fisicas: {fmt_int(units)}"
        )

    def values(self) -> dict:
        data = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            notes_item = self.table.item(row, 4)
            if name_item is None:
                continue
            item_id = name_item.data(Qt.UserRole + 1)
            if item_id is None:
                continue
            physical = self._physical_text(row)
            notes = notes_item.text().strip() if notes_item else ""
            data[int(item_id)] = (physical, notes)
        return data

    def _save(self) -> None:
        try:
            with session_scope() as session:
                save_count_draft(
                    session,
                    self.count_id,
                    self.values(),
                    notes=self.notes.toPlainText(),
                )
        except AppError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc)
            return
        show_info(self, "El borrador del recuento fue guardado.")

    def _confirm(self) -> None:
        if not confirm(
            self,
            "Confirmar recuento",
            "Se ajustara el stock disponible para las diferencias encontradas. "
            "Esta operacion no puede deshacerse; solo puede corregirse con otro recuento.",
            "Confirmar y ajustar",
            danger=True,
        ):
            return
        try:
            with session_scope() as session:
                count = confirm_count(
                    session,
                    self.count_id,
                    user_id=get_current_user().id,
                    values=self.values(),
                    notes=self.notes.toPlainText(),
                )
                differences = count.total_differences
        except AppError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc)
            return
        self.confirmed = True
        show_info(
            self,
            f"El recuento fue confirmado. Se ajustaron {fmt_int(differences)} articulo(s) con diferencia.",
        )
        self.accept()
