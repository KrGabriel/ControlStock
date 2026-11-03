"""Recuento fisico de inventario."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidget

from app.db.database import session_scope
from app.domain import COUNT_CONFIRMED, COUNT_DRAFT
from app.errors import AppError
from app.services.counts import (
    discard_draft,
    get_count,
    get_draft,
    list_counts,
    start_count,
)
from app.session import get_current_user
from app.ui.common import (
    Card,
    PageHeader,
    clear_table,
    confirm,
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
from app.ui.dialogs.count_dialogs import CountEditorDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS


class CountsPage(BasePage):
    page_key = "counts"
    title = "Recuento fisico"
    subtitle = "Comparacion entre stock del sistema y conteo real."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Recuento fisico",
            "Cuente las unidades reales y confirme para generar los ajustes de stock.",
        )
        self.start_button = make_button("Iniciar recuento", "primary", "plus")
        self.start_button.clicked.connect(self._start_count)
        header.add_action(self.start_button)
        self.continue_button = make_button("Continuar borrador", "secondary", "edit")
        self.continue_button.clicked.connect(self._continue_draft)
        header.add_action(self.continue_button)
        detail_button = make_button("Ver detalle", "secondary", "eye")
        detail_button.clicked.connect(self._open_detail)
        header.add_action(detail_button)
        self.discard_button = make_button("Descartar borrador", "secondary", "trash")
        self.discard_button.clicked.connect(self._discard_draft)
        header.add_action(self.discard_button)
        self.root.addWidget(header)

        info_card = Card(margins=14, spacing=4)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("Muted")
        info_card.layout.addWidget(self.info_label)
        self.root.addWidget(info_card)

        table_card = Card(margins=16, spacing=8)
        table_head = QHBoxLayout()
        title = QLabel("Historial de recuentos")
        title.setObjectName("SectionTitle")
        table_head.addWidget(title, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        table_head.addWidget(self.count_label)
        table_card.layout.addLayout(table_head)
        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Codigo", "Inicio", "Confirmado", "Articulos", "Diferencias", "Estado"],
            stretch=0,
            column_widths={0: 150, 1: 130, 2: 130, 3: 85, 4: 90, 5: 100},
        )
        self.table.doubleClicked.connect(self._open_detail)
        table_card.layout.addWidget(self.table, 1)
        self.root.addWidget(table_card, 1)
        self._draft_id: int | None = None

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                draft = get_draft(session)
                self._draft_id = draft.id if draft else None
                counts = list_counts(session)
                rows = [
                    {
                        "id": count.id,
                        "code": count.code,
                        "started": count.started_at,
                        "confirmed": count.confirmed_at,
                        "items": len(count.details),
                        "differences": count.total_differences,
                        "status": count.status,
                        "notes": count.notes,
                    }
                    for count in counts
                ]
        except Exception as exc:
            show_error(self, exc)
            return
        self.continue_button.setEnabled(self._draft_id is not None)
        self.discard_button.setEnabled(self._draft_id is not None)
        if self._draft_id is not None:
            self.info_label.setText(
                "Existe un recuento en borrador. Puede continuarlo, guardar cambios o descartarlo."
            )
        else:
            self.info_label.setText(
                "No hay recuentos en borrador. Inicie uno nuevo para comparar el stock fisico."
            )
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            if data["status"] == COUNT_CONFIRMED:
                status_text, color, bg = "Confirmado", COLORS["success"], COLORS["success_soft"]
                differences = fmt_int(data["differences"])
            else:
                status_text, color, bg = "Borrador", COLORS["warning"], COLORS["warning_soft"]
                differences = "-"
            set_row(
                table,
                row,
                [
                    make_item(data["code"], data=data["id"], bold=True),
                    make_item(fmt_datetime(data["started"])),
                    make_item(fmt_datetime(data["confirmed"]) if data["confirmed"] else ""),
                    make_item(fmt_int(data["items"]), sort_value=data["items"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(differences, sort_value=data["differences"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(status_text, color=color, bg=bg, bold=True),
                ],
            )
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)} recuento(s)")

    def _start_count(self) -> None:
        if self._draft_id is not None:
            if confirm(
                self,
                "Recuento en curso",
                "Ya existe un recuento en borrador. Desea continuarlo en lugar de iniciar otro?",
                "Continuar borrador",
            ):
                self._open_editor(self._draft_id)
            return
        if not confirm(
            self,
            "Iniciar recuento",
            "Se cargaran todos los articulos activos con su stock actual. "
            "El recuento quedara en borrador hasta que lo confirme.",
            "Iniciar",
        ):
            return
        try:
            with session_scope() as session:
                count = start_count(session, user_id=get_current_user().id)
                count_id = count.id
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self._open_editor(count_id)

    def _continue_draft(self) -> None:
        if self._draft_id is None:
            show_warning(self, "No hay recuentos en borrador.")
            return
        self._open_editor(self._draft_id)

    def _open_editor(self, count_id: int, read_only: bool = False) -> None:
        dialog = CountEditorDialog(count_id, self, read_only=read_only)
        dialog.exec()
        self.refresh()
        if dialog.confirmed:
            self.mark_changed()

    def _selected(self) -> int | None:
        count_id = selected_id(self.table)
        if count_id is None:
            show_warning(self, "Seleccione un recuento de la tabla.")
        return count_id

    def _open_detail(self) -> None:
        count_id = self._selected()
        if count_id is None:
            return
        try:
            with session_scope() as session:
                count = get_count(session, count_id)
                read_only = count.status == COUNT_CONFIRMED
        except Exception as exc:
            show_error(self, exc)
            return
        self._open_editor(count_id, read_only=read_only)

    def _discard_draft(self) -> None:
        if self._draft_id is None:
            show_warning(self, "No hay recuentos en borrador.")
            return
        if not confirm(
            self,
            "Descartar borrador",
            "Se eliminara el recuento en borrador y las cantidades ingresadas. "
            "El stock no se modifica.",
            "Descartar",
            danger=True,
        ):
            return
        try:
            with session_scope() as session:
                discard_draft(session, self._draft_id)
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        show_info(self, "El borrador fue descartado.")
