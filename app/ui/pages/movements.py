"""Historial general y anulacion controlada de movimientos."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QTableWidget,
)

from app.db.database import session_scope
from app.domain import (
    MOVE_ADJUSTMENT,
    MOVE_DELIVERY,
    MOVE_INCOME,
    MOVE_RETURN,
    MOVE_STATE_CHANGE,
    MOVE_WRITE_OFF,
    MOVEMENT_TYPES,
)
from app.errors import AppError
from app.services.crews import crew_options
from app.services.movements import get_movement, list_movements
from app.services.stock import void_movement
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
    fmt_signed,
)
from app.ui.dialogs.movement_dialogs import MovementDetailDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS

VOIDABLE = {
    MOVE_INCOME,
    MOVE_DELIVERY,
    MOVE_RETURN,
    MOVE_WRITE_OFF,
    MOVE_STATE_CHANGE,
}


class MovementsPage(BasePage):
    page_key = "movements"
    title = "Movimientos"
    subtitle = "Trazabilidad completa del inventario."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Movimientos de stock",
            "Historial inmutable de ingresos, entregas, devoluciones, ajustes y anulaciones.",
        )
        detail_button = make_button("Ver detalle", "secondary", "eye")
        detail_button.clicked.connect(self._open_detail)
        header.add_action(detail_button)
        void_button = make_button("Anular movimiento", "secondary", "trash")
        void_button.clicked.connect(self._void_movement)
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
        self.type_combo = QComboBox()
        self.type_combo.addItem("Todos los tipos", None)
        for key, label in MOVEMENT_TYPES.items():
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.type_combo)
        self.crew_combo = QComboBox()
        self.crew_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.crew_combo)
        self.search = SearchLineEdit("Articulo, tecnico u observaciones...")
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
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
            [
                "Fecha y hora",
                "Tipo",
                "Articulo",
                "Cant.",
                "Variacion",
                "Antes",
                "Despues",
                "Cuadrilla",
                "Usuario",
                "Observaciones",
                "Estado",
            ],
            stretch=9,
            column_widths={0: 125, 1: 145, 3: 60, 4: 75, 5: 60, 6: 65, 7: 110, 8: 90, 10: 80},
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
        movement_type = self.type_combo.currentData()
        try:
            with session_scope() as session:
                movements = list_movements(
                    session,
                    date_from=self.date_from.date().toPython(),
                    date_to=self.date_to.date().toPython(),
                    crew_id=self.crew_combo.currentData(),
                    movement_types=[movement_type] if movement_type else None,
                    search=self.search.text(),
                )
                rows = [
                    {
                        "id": movement.id,
                        "created_at": movement.created_at,
                        "type": movement.movement_type,
                        "item": movement.item_name_snapshot,
                        "quantity": movement.quantity,
                        "delta": movement.stock_delta,
                        "before": movement.stock_before,
                        "after": movement.stock_after,
                        "crew": movement.crew.name if movement.crew else "",
                        "user": movement.user.username if movement.user else "",
                        "observations": movement.observations,
                        "voided": movement.is_voided,
                    }
                    for movement in movements
                ]
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            row_color = COLORS["muted"] if data["voided"] else None
            delta_color = COLORS["muted"] if data["voided"] else (
                COLORS["success"] if data["delta"] > 0 else COLORS["danger"] if data["delta"] < 0 else COLORS["muted"]
            )
            state_text = "Anulado" if data["voided"] else "Vigente"
            state_color = COLORS["danger"] if data["voided"] else COLORS["success"]
            state_bg = COLORS["danger_soft"] if data["voided"] else COLORS["success_soft"]
            set_row(
                table,
                row,
                [
                    make_item(fmt_datetime(data["created_at"]), data=data["id"], color=row_color),
                    make_item(MOVEMENT_TYPES.get(data["type"], data["type"]), color=row_color),
                    make_item(data["item"], color=row_color),
                    make_item(fmt_int(data["quantity"]), sort_value=data["quantity"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_signed(data["delta"]), sort_value=data["delta"], align=Qt.AlignRight | Qt.AlignVCenter, color=delta_color, bold=True),
                    make_item(fmt_int(data["before"]), sort_value=data["before"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(fmt_int(data["after"]), sort_value=data["after"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(data["crew"], color=row_color),
                    make_item(data["user"], color=row_color),
                    make_item(data["observations"], tooltip=data["observations"], color=row_color),
                    make_item(state_text, color=state_color, bg=state_bg, bold=True),
                ],
            )
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)} movimiento(s)")

    def _selected(self) -> int | None:
        movement_id = selected_id(self.table)
        if movement_id is None:
            show_warning(self, "Seleccione un movimiento de la tabla.")
        return movement_id

    def _open_detail(self) -> None:
        movement_id = self._selected()
        if movement_id is None:
            return
        MovementDetailDialog(movement_id, self).exec()

    def _void_movement(self) -> None:
        movement_id = self._selected()
        if movement_id is None:
            return
        try:
            with session_scope() as session:
                movement = get_movement(session, movement_id)
                movement_type = movement.movement_type
                is_voided = movement.is_voided
        except Exception as exc:
            show_error(self, exc)
            return
        if is_voided:
            show_warning(self, "El movimiento seleccionado ya esta anulado.")
            return
        if movement_type not in VOIDABLE:
            show_warning(
                self,
                "Este tipo de movimiento no admite anulacion directa. "
                "Para ajustes de recuento realice un nuevo recuento fisico.",
            )
            return
        reason = ask_reason(
            self,
            "Anular movimiento",
            "La anulacion genera un movimiento compensatorio y conserva el historial original.",
            "Motivo de la anulacion",
        )
        if reason is None:
            return
        try:
            with session_scope() as session:
                void_movement(session, movement_id, get_current_user().id, reason)
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "El movimiento fue anulado correctamente.")
