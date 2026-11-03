"""Dialogos para registrar y consultar devoluciones."""
from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
)

from app.db.database import session_scope
from app.domain import CONDITIONS, DELIVERY_ACTIVE, DELIVERY_VOIDED
from app.errors import ValidationError
from app.services.balances import crew_balances
from app.services.crews import list_crews
from app.services.returns import get_return
from app.ui.common import (
    Card,
    FormDialog,
    clear_table,
    finish_table,
    make_button,
    make_item,
    selected_id,
    set_row,
    setup_table,
    show_error,
    show_warning,
    fmt_datetime,
    fmt_int,
)
from app.ui.dialogs.delivery_dialogs import ReturnLineDialog
from app.ui.theme import COLORS


class NewReturnDialog(FormDialog):
    def __init__(self, parent=None):
        super().__init__(
            "Nueva devolucion",
            "Registre el retorno de materiales reutilizables. Cada linea se aplica "
            "a las entregas pendientes mas antiguas de la cuadrilla.",
            parent,
            width=800,
        )
        self.set_primary_text("Registrar devolucion")
        self.lines: dict[tuple[int, str], dict] = {}
        self.balances: dict[int, dict] = {}
        self.crew_combo = QComboBox()
        try:
            with session_scope() as session:
                for crew in list_crews(session):
                    self.crew_combo.addItem(crew.name, crew.id)
        except Exception as exc:
            show_error(self, exc)
        self.when = QDateTimeEdit(QDateTime.currentDateTime())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(60)
        self.notes.setPlaceholderText("Observaciones generales de la devolucion")
        self.form.addRow("Cuadrilla *", self.crew_combo)
        self.form.addRow("Fecha y hora", self.when)
        self.form.addRow("Observaciones", self.notes)

        balances_head = QHBoxLayout()
        balances_title = QLabel("Materiales asignados pendientes")
        balances_title.setObjectName("SectionTitle")
        balances_head.addWidget(balances_title, 1)
        self.add_button = make_button("Agregar devolucion", "secondary", "plus")
        self.add_button.clicked.connect(self._add_line)
        balances_head.addWidget(self.add_button)
        self.body.addLayout(balances_head)
        self.balances_table = QTableWidget()
        setup_table(
            self.balances_table,
            ["Articulo", "Pendiente"],
            stretch=0,
            column_widths={1: 100},
        )
        self.balances_table.setMinimumHeight(160)
        self.balances_table.doubleClicked.connect(self._add_line)
        self.body.addWidget(self.balances_table)

        lines_head = QHBoxLayout()
        lines_title = QLabel("Lineas de la devolucion")
        lines_title.setObjectName("SectionTitle")
        lines_head.addWidget(lines_title, 1)
        remove_button = make_button("Quitar linea", "secondary", "trash")
        remove_button.clicked.connect(self._remove_line)
        lines_head.addWidget(remove_button)
        self.body.addLayout(lines_head)
        self.lines_table = QTableWidget()
        setup_table(
            self.lines_table,
            ["Articulo", "Cantidad", "Estado", "Observaciones"],
            stretch=3,
            column_widths={1: 90, 2: 150},
        )
        self.lines_table.setMinimumHeight(150)
        self.body.addWidget(self.lines_table)
        self.total_label = QLabel("Sin unidades para devolver")
        self.total_label.setObjectName("Muted")
        self.body.addWidget(self.total_label)

        self.crew_combo.currentIndexChanged.connect(self._crew_changed)
        self.set_validator(self._validate)
        self._load_balances()

    def _crew_changed(self) -> None:
        self.lines.clear()
        self._load_balances()
        self._render_lines()

    def _load_balances(self) -> None:
        crew_id = self.crew_combo.currentData()
        self.balances = {}
        if crew_id is None:
            self.balances_table.setRowCount(0)
            return
        try:
            with session_scope() as session:
                for balance in crew_balances(session, crew_id):
                    self.balances[balance["item_id"]] = {
                        "name": balance["name"],
                        "quantity": balance["quantity"],
                    }
        except Exception as exc:
            show_error(self, exc)
        table = self.balances_table
        clear_table(table)
        rows = list(self.balances.items())
        table.setRowCount(len(rows))
        for row, (item_id, data) in enumerate(rows):
            set_row(
                table,
                row,
                [
                    make_item(data["name"], data=item_id),
                    make_item(
                        fmt_int(data["quantity"]),
                        sort_value=data["quantity"],
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                ],
            )
        finish_table(table, sortable=False)
        if rows:
            table.selectRow(0)
        else:
            self.total_label.setText("La cuadrilla no tiene materiales pendientes de devolucion.")

    def _used_quantity(self, item_id: int) -> int:
        return sum(
            data["quantity"]
            for (line_item_id, _), data in self.lines.items()
            if line_item_id == item_id
        )

    def _add_line(self) -> None:
        if not self.balances:
            return
        item_id = selected_id(self.balances_table)
        if item_id is None:
            show_warning(self, "Seleccione un material de la lista.")
            return
        balance = self.balances[item_id]
        remaining = balance["quantity"] - self._used_quantity(item_id)
        if remaining <= 0:
            show_warning(self, "Ya agrego todas las unidades pendientes de este material.")
            return
        dialog = ReturnLineDialog(balance["name"], remaining, item_id, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        key = (item_id, values["condition"])
        if key in self.lines:
            self.lines[key]["quantity"] += values["quantity"]
            if values["notes"]:
                existing = self.lines[key]["notes"]
                self.lines[key]["notes"] = (
                    f"{existing} | {values['notes']}" if existing else values["notes"]
                )
        else:
            self.lines[key] = {
                "name": balance["name"],
                "quantity": values["quantity"],
                "condition": values["condition"],
                "notes": values["notes"],
            }
        self._render_lines()

    def _remove_line(self) -> None:
        rows = self.lines_table.selectionModel().selectedRows()
        if not rows:
            return
        key_text = self.lines_table.item(rows[0].row(), 0).data(Qt.UserRole + 1)
        for key in list(self.lines):
            if f"{key[0]}:{key[1]}" == key_text:
                self.lines.pop(key, None)
                break
        self._render_lines()

    def _render_lines(self) -> None:
        table = self.lines_table
        clear_table(table)
        rows = list(self.lines.items())
        table.setRowCount(len(rows))
        for row, ((item_id, condition), data) in enumerate(rows):
            set_row(
                table,
                row,
                [
                    make_item(data["name"], data=f"{item_id}:{condition}"),
                    make_item(
                        fmt_int(data["quantity"]),
                        sort_value=data["quantity"],
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                    make_item(CONDITIONS.get(condition, condition)),
                    make_item(data["notes"], tooltip=data["notes"]),
                ],
            )
        finish_table(table, sortable=False)
        units = sum(data["quantity"] for data in self.lines.values())
        self.total_label.setText(
            f"{len(rows)} linea(s) | {fmt_int(units)} unidad(es) a devolver"
            if rows
            else "Sin unidades para devolver"
        )

    def _validate(self) -> None:
        if self.crew_combo.currentData() is None:
            raise ValidationError("Seleccione una cuadrilla.")
        if not self.lines:
            raise ValidationError("Agregue al menos un material a la devolucion.")

    def values(self) -> dict:
        return {
            "crew_id": self.crew_combo.currentData(),
            "lines": [
                (item_id, data["quantity"], condition, data["notes"])
                for (item_id, condition), data in self.lines.items()
            ],
            "notes": self.notes.toPlainText(),
            "occurred_at": self.when.dateTime().toPython(),
        }


class ReturnDetailDialog(QDialog):
    def __init__(self, return_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle de la devolucion")
        self.setModal(True)
        self.resize(900, 620)
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
        table_card = Card(margins=16, spacing=6)
        table_title = QLabel("Materiales devueltos")
        table_title.setObjectName("SectionTitle")
        table_card.layout.addWidget(table_title)
        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Articulo", "Cantidad", "Estado", "Entrega", "Observaciones"],
            stretch=4,
            column_widths={1: 90, 2: 160, 3: 150},
        )
        table_card.layout.addWidget(self.table)
        root.addWidget(table_card, 1)
        self._load(return_id)

    def _load(self, return_id: int) -> None:
        try:
            with session_scope() as session:
                record = get_return(session, return_id)
                status_text = "Anulada" if record.status == DELIVERY_VOIDED else "Activa"
                self.title_label.setText(f"Devolucion {record.code}")
                self.subtitle.setText(
                    f"{fmt_datetime(record.created_at)}  |  {record.crew.name}  |  Estado: {status_text}"
                )
                parts = [
                    f"<b>Codigo:</b> {record.code}",
                    f"<b>Cuadrilla:</b> {record.crew.name}",
                    f"<b>Unidades:</b> {fmt_int(record.total_units)}",
                ]
                if record.notes:
                    parts.append(f"<b>Observaciones:</b> {record.notes}")
                if record.void_reason:
                    parts.append(
                        f"<b>Anulada:</b> {fmt_datetime(record.voided_at)} - {record.void_reason}"
                    )
                self.info_label.setText("<br>".join(parts))
                self.table.setRowCount(len(record.details))
                for row, detail in enumerate(record.details):
                    delivery_code = ""
                    if detail.delivery_detail and detail.delivery_detail.delivery:
                        delivery_code = detail.delivery_detail.delivery.code
                    set_row(
                        self.table,
                        row,
                        [
                            make_item(detail.item.name if detail.item else ""),
                            make_item(
                                fmt_int(detail.quantity),
                                sort_value=detail.quantity,
                                align=Qt.AlignRight | Qt.AlignVCenter,
                            ),
                            make_item(CONDITIONS.get(detail.condition, detail.condition)),
                            make_item(delivery_code),
                            make_item(detail.notes, tooltip=detail.notes),
                        ],
                    )
                finish_table(self.table, sortable=False)
        except Exception as exc:
            show_error(self, exc)
