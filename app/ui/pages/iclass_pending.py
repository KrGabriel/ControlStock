"""Seguimiento administrativo de cargas en IClass."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QTableWidget

from app.db.database import session_scope
from app.db.models import Delivery
from app.domain import (
    DELIVERY_ACTIVE,
    ICLASS_LOADED,
    ICLASS_PENDING,
    ICLASS_STATUSES,
)
from app.errors import AppError
from app.services.deliveries import list_deliveries
from app.services.iclass import mark_loaded, pending_deliveries, revert_loaded
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
from app.ui.dialogs.delivery_dialogs import DeliveryDetailDialog
from app.ui.dialogs.iclass_dialogs import IClassMarkDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS


class IClassPendingPage(BasePage):
    page_key = "iclass"
    title = "Pendientes de IClass"
    subtitle = "Control de cargas administrativas."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Pendientes de IClass",
            "Marque las entregas cargadas en IClass. Este control no modifica el stock.",
        )
        self.mark_button = make_button("Marcar cargada", "primary", "check")
        self.mark_button.clicked.connect(self._mark_loaded)
        header.add_action(self.mark_button)
        self.revert_button = make_button("Revertir carga", "secondary", "refresh")
        self.revert_button.clicked.connect(self._revert_loaded)
        header.add_action(self.revert_button)
        detail_button = make_button("Ver entrega", "secondary", "eye")
        detail_button.clicked.connect(self._open_detail)
        header.add_action(detail_button)
        self.root.addWidget(header)

        filter_card = Card(margins=12, spacing=8)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.status_combo = QComboBox()
        self.status_combo.addItem("Pendientes", ICLASS_PENDING)
        self.status_combo.addItem("Cargadas", ICLASS_LOADED)
        self.status_combo.addItem("Todas", None)
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.status_combo)
        self.search = SearchLineEdit("Codigo o tecnico...")
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
        filter_card.layout.addLayout(filters)
        self.root.addWidget(filter_card)

        summary_card = Card(margins=14, spacing=4)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("Muted")
        summary_card.layout.addWidget(self.summary_label)
        self.root.addWidget(summary_card)

        table_card = Card(margins=16, spacing=8)
        table_head = QHBoxLayout()
        title = QLabel("Entregas")
        title.setObjectName("SectionTitle")
        table_head.addWidget(title, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        table_head.addWidget(self.count_label)
        table_card.layout.addLayout(table_head)
        self.table = QTableWidget()
        setup_table(
            self.table,
            [
                "Codigo",
                "Fecha y hora",
                "Cuadrilla",
                "Tecnico",
                "Unidades",
                "Estado IClass",
                "Cargada",
                "Referencia",
            ],
            stretch=3,
            column_widths={0: 150, 1: 125, 4: 80, 5: 145, 6: 125, 7: 120},
        )
        self.table.doubleClicked.connect(self._open_detail)
        table_card.layout.addWidget(self.table, 1)
        self.root.addWidget(table_card, 1)

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                pending = pending_deliveries(session)
                pending_count = len(pending)
                iclass_filter = self.status_combo.currentData()
                deliveries = list_deliveries(
                    session,
                    status=DELIVERY_ACTIVE,
                    iclass_status=iclass_filter,
                    search=self.search.text(),
                )
                rows = [
                    {
                        "id": delivery.id,
                        "code": delivery.code,
                        "created_at": delivery.created_at,
                        "crew": delivery.crew.name,
                        "technician": delivery.technician,
                        "units": delivery.total_units,
                        "iclass": delivery.iclass_status,
                        "loaded_at": delivery.iclass_loaded_at,
                        "reference": delivery.iclass_reference,
                    }
                    for delivery in deliveries
                ]
                loaded_count = len(
                    [d for d in list_deliveries(session, status=DELIVERY_ACTIVE, iclass_status=ICLASS_LOADED)]
                )
        except Exception as exc:
            show_error(self, exc)
            return
        self.summary_label.setText(
            f"Entregas pendientes de IClass: {fmt_int(pending_count)}"
            f"  |  Entregas cargadas: {fmt_int(loaded_count)}"
        )
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            if data["iclass"] == ICLASS_LOADED:
                iclass_text, color, bg = ICLASS_STATUSES[ICLASS_LOADED], COLORS["success"], COLORS["success_soft"]
            else:
                iclass_text, color, bg = ICLASS_STATUSES[ICLASS_PENDING], COLORS["warning"], COLORS["warning_soft"]
            set_row(
                table,
                row,
                [
                    make_item(data["code"], data=data["id"], bold=True),
                    make_item(fmt_datetime(data["created_at"])),
                    make_item(data["crew"]),
                    make_item(data["technician"]),
                    make_item(fmt_int(data["units"]), sort_value=data["units"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(iclass_text, color=color, bg=bg, bold=True),
                    make_item(fmt_datetime(data["loaded_at"]) if data["loaded_at"] else ""),
                    make_item(data["reference"]),
                ],
            )
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)} entrega(s)")

    def _selected(self) -> int | None:
        delivery_id = selected_id(self.table)
        if delivery_id is None:
            show_warning(self, "Seleccione una entrega de la tabla.")
        return delivery_id

    def _open_detail(self) -> None:
        delivery_id = self._selected()
        if delivery_id is None:
            return
        DeliveryDetailDialog(delivery_id, self).exec()

    def _mark_loaded(self) -> None:
        delivery_id = self._selected()
        if delivery_id is None:
            return
        try:
            with session_scope() as session:
                delivery = session.get(Delivery, delivery_id)
                if delivery is None:
                    show_warning(self, "La entrega no existe.")
                    return
                code = delivery.code
                if delivery.iclass_status == ICLASS_LOADED:
                    show_warning(self, f"La entrega {code} ya esta cargada en IClass.")
                    return
        except Exception as exc:
            show_error(self, exc)
            return
        dialog = IClassMarkDialog(code, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                mark_loaded(
                    session,
                    delivery_id,
                    user_id=get_current_user().id,
                    **dialog.values(),
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, f"La entrega {code} fue marcada como cargada en IClass.")

    def _revert_loaded(self) -> None:
        delivery_id = self._selected()
        if delivery_id is None:
            return
        try:
            with session_scope() as session:
                delivery = session.get(Delivery, delivery_id)
                if delivery is None:
                    show_warning(self, "La entrega no existe.")
                    return
                code = delivery.code
                if delivery.iclass_status != ICLASS_LOADED:
                    show_warning(self, f"La entrega {code} no esta marcada como cargada.")
                    return
        except Exception as exc:
            show_error(self, exc)
            return
        reason = ask_reason(
            self,
            "Revertir carga IClass",
            f"La entrega {code} volvera al estado pendiente de IClass. El stock no cambia.",
            "Motivo de la reversion",
        )
        if reason is None:
            return
        try:
            with session_scope() as session:
                revert_loaded(
                    session,
                    delivery_id,
                    user_id=get_current_user().id,
                    reason=reason,
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, f"La marca de IClass de {code} fue revertida.")
