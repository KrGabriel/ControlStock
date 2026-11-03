"""Ingresos de stock y anulacion de ingresos."""
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
from app.domain import MOVE_INCOME
from app.errors import AppError
from app.services.movements import get_movement, list_movements
from app.services.stock import register_income, void_income
from app.session import get_current_user
from app.ui.common import (
    Card,
    PageHeader,
    SearchLineEdit,
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
from app.ui.dialogs.stock_dialogs import IncomeDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS


class StockInPage(BasePage):
    page_key = "stock_in"
    title = "Ingresos de stock"
    subtitle = "Altas de material al inventario."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Ingresos de stock",
            "Registre compras o reposiciones. Cada ingreso conserva stock anterior y posterior.",
        )
        new_button = make_button("Registrar ingreso", "primary", "plus")
        new_button.clicked.connect(self._new_income)
        header.add_action(new_button)
        void_button = make_button("Anular ingreso", "secondary", "trash")
        void_button.clicked.connect(self._void_income)
        header.add_action(void_button)
        self.root.addWidget(header)

        filter_card = Card(margins=12, spacing=8)
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
        self.status_combo = QComboBox()
        self.status_combo.addItem("Todos", None)
        self.status_combo.addItem("Vigentes", "ACTIVE")
        self.status_combo.addItem("Anulados", "VOIDED")
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.status_combo)
        self.search = SearchLineEdit("Articulo, proveedor u observaciones...")
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
        filter_card.layout.addLayout(filters)
        self.root.addWidget(filter_card)

        table_card = Card(margins=16, spacing=8)
        table_head = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        table_head.addWidget(self.count_label, 1)
        table_card.layout.addLayout(table_head)
        self.table = QTableWidget()
        setup_table(
            self.table,
            [
                "Fecha y hora",
                "Articulo",
                "Cantidad",
                "Stock anterior",
                "Stock posterior",
                "Usuario",
                "Observaciones",
                "Estado",
            ],
            stretch=6,
            column_widths={0: 125, 2: 80, 3: 100, 4: 100, 5: 90, 7: 80},
        )
        self.table.doubleClicked.connect(self._show_observations)
        table_card.layout.addWidget(self.table, 1)
        self.root.addWidget(table_card, 1)

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                movements = list_movements(
                    session,
                    date_from=self.date_from.date().toPython(),
                    date_to=self.date_to.date().toPython(),
                    movement_types=[MOVE_INCOME],
                    search=self.search.text(),
                )
                rows = []
                for movement in movements:
                    if self.status_combo.currentData() == "ACTIVE" and movement.is_voided:
                        continue
                    if self.status_combo.currentData() == "VOIDED" and not movement.is_voided:
                        continue
                    rows.append(
                        {
                            "id": movement.id,
                            "created_at": movement.created_at,
                            "item": movement.item_name_snapshot,
                            "quantity": movement.quantity,
                            "before": movement.stock_before,
                            "after": movement.stock_after,
                            "user": movement.user.username if movement.user else "",
                            "observations": movement.observations,
                            "voided": movement.is_voided,
                            "void_reason": movement.void_reason,
                        }
                    )
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            if data["voided"]:
                state_text, color, bg = "Anulado", COLORS["danger"], COLORS["danger_soft"]
                row_color = COLORS["muted"]
                tooltip = data["void_reason"]
            else:
                state_text, color, bg = "Vigente", COLORS["success"], COLORS["success_soft"]
                row_color = None
                tooltip = data["observations"]
            set_row(
                table,
                row,
                [
                    make_item(fmt_datetime(data["created_at"]), data=data["id"], color=row_color),
                    make_item(data["item"], color=row_color),
                    make_item(fmt_int(data["quantity"]), sort_value=data["quantity"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_int(data["before"]), sort_value=data["before"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_int(data["after"]), sort_value=data["after"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(data["user"], color=row_color),
                    make_item(data["observations"], tooltip=tooltip, color=row_color),
                    make_item(state_text, color=color, bg=bg, bold=True),
                ],
            )
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)} ingreso(s)")

    def _new_income(self) -> None:
        dialog = IncomeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                register_income(
                    session,
                    user_id=get_current_user().id,
                    **dialog.values(),
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "El ingreso de stock fue registrado correctamente.")

    def _selected_movement_id(self) -> int | None:
        movement_id = selected_id(self.table)
        if movement_id is None:
            show_warning(self, "Seleccione un ingreso de la tabla.")
        return movement_id

    def _void_income(self) -> None:
        movement_id = self._selected_movement_id()
        if movement_id is None:
            return
        reason = ask_reason(
            self,
            "Anular ingreso",
            "El ingreso se marcara como anulado y se descontaran sus unidades del stock disponible.",
            "Motivo de la anulacion",
        )
        if reason is None:
            return
        try:
            with session_scope() as session:
                movement = get_movement(session, movement_id)
                void_income(session, movement, get_current_user().id, reason)
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "El ingreso fue anulado correctamente.")

    def _show_observations(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 6)
        if item and item.toolTip():
            from app.ui.common import show_info

            show_info(self, item.toolTip(), "Observaciones")
