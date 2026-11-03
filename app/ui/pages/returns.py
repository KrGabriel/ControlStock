"""Consulta y registro de devoluciones de cuadrillas."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QTableWidget,
)

from app.db.database import session_scope
from app.domain import DELIVERY_ACTIVE, DELIVERY_VOIDED
from app.errors import AppError
from app.services.crews import crew_options
from app.services.returns import create_return, list_returns, void_return
from app.session import get_current_user
from app.ui.common import (
    Card,
    PageHeader,
    ask_reason,
    clear_table,
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
from app.ui.dialogs.return_dialogs import NewReturnDialog, ReturnDetailDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS


class ReturnsPage(BasePage):
    page_key = "returns"
    title = "Devoluciones"
    subtitle = "Retorno de materiales reutilizables."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Devoluciones de cuadrillas",
            "El material devuelto vuelve al estado indicado y se descuenta del saldo asignado.",
        )
        new_button = make_button("Nueva devolucion", "primary", "plus")
        new_button.clicked.connect(self._new_return)
        header.add_action(new_button)
        detail_button = make_button("Ver detalle", "secondary", "eye")
        detail_button.clicked.connect(self._open_detail)
        header.add_action(detail_button)
        void_button = make_button("Anular", "secondary", "trash")
        void_button.clicked.connect(self._void_return)
        header.add_action(void_button)
        self.root.addWidget(header)

        filters_card = Card(margins=12, spacing=8)
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
        self.status_combo = QComboBox()
        self.status_combo.addItem("Activas", DELIVERY_ACTIVE)
        self.status_combo.addItem("Anuladas", DELIVERY_VOIDED)
        self.status_combo.addItem("Todas", None)
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.status_combo)
        filters.addStretch(1)
        filters_card.layout.addLayout(filters)
        self.root.addWidget(filters_card)

        table_card = Card(margins=16, spacing=8)
        table_head = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        table_head.addWidget(self.count_label, 1)
        table_card.layout.addLayout(table_head)
        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Codigo", "Fecha y hora", "Cuadrilla", "Lineas", "Unidades", "Estado"],
            stretch=2,
            column_widths={0: 150, 1: 125, 3: 75, 4: 80, 5: 85},
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
                records = list_returns(
                    session,
                    crew_id=self.crew_combo.currentData(),
                    date_from=self.date_from.date().toPython(),
                    date_to=self.date_to.date().toPython(),
                    status=self.status_combo.currentData(),
                )
                rows = [
                    {
                        "id": record.id,
                        "code": record.code,
                        "created_at": record.created_at,
                        "crew": record.crew.name,
                        "lines": len(record.details),
                        "units": record.total_units,
                        "status": record.status,
                    }
                    for record in records
                ]
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            if data["status"] == DELIVERY_VOIDED:
                status_text, color, bg = "Anulada", COLORS["danger"], COLORS["danger_soft"]
                row_color = COLORS["muted"]
            else:
                status_text, color, bg = "Activa", COLORS["success"], COLORS["success_soft"]
                row_color = None
            set_row(
                table,
                row,
                [
                    make_item(data["code"], data=data["id"], color=row_color, bold=True),
                    make_item(fmt_datetime(data["created_at"]), color=row_color),
                    make_item(data["crew"], color=row_color),
                    make_item(fmt_int(data["lines"]), sort_value=data["lines"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_int(data["units"]), sort_value=data["units"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(status_text, color=color, bg=bg, bold=True),
                ],
            )
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)} devolucion(es)")

    def _selected(self) -> int | None:
        return_id = selected_id(self.table)
        if return_id is None:
            show_warning(self, "Seleccione una devolucion de la tabla.")
        return return_id

    def _new_return(self) -> None:
        dialog = NewReturnDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                record = create_return(
                    session,
                    user_id=get_current_user().id,
                    **dialog.values(),
                )
                code = record.code
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, f"La devolucion {code} fue registrada correctamente.")

    def _open_detail(self) -> None:
        return_id = self._selected()
        if return_id is None:
            return
        ReturnDetailDialog(return_id, self).exec()

    def _void_return(self) -> None:
        return_id = self._selected()
        if return_id is None:
            return
        reason = ask_reason(
            self,
            "Anular devolucion",
            "Se revertira la devolucion y las unidades volveran al saldo asignado de la cuadrilla.",
            "Motivo de la anulacion",
        )
        if reason is None:
            return
        try:
            with session_scope() as session:
                record = void_return(session, return_id, get_current_user().id, reason)
                code = record.code
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, f"La devolucion {code} fue anulada.")
