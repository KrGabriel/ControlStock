"""Fichas de cuadrillas y materiales asignados."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QVBoxLayout,
)

from app.db.database import session_scope
from app.domain import DELIVERY_ACTIVE, DELIVERY_VOIDED, ICLASS_LOADED
from app.errors import AppError
from app.services.crews import (
    create_crew,
    crew_summary,
    get_crew,
    list_crews,
    set_crew_active,
    update_crew,
)
from app.ui.common import (
    Card,
    PageHeader,
    SearchLineEdit,
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
from app.ui.dialogs.reference_dialogs import CrewFormDialog
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS


class CrewsPage(BasePage):
    page_key = "crews"
    title = "Cuadrillas"
    subtitle = "Equipos de trabajo y saldos pendientes."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Cuadrillas",
            "Consulte entregas, devoluciones y materiales pendientes por cuadrilla.",
        )
        new_button = make_button("Nueva cuadrilla", "primary", "plus")
        new_button.clicked.connect(self._new_crew)
        header.add_action(new_button)
        self.edit_button = make_button("Editar", "secondary", "edit")
        self.edit_button.clicked.connect(self._edit_crew)
        header.add_action(self.edit_button)
        self.toggle_button = make_button("Desactivar", "secondary")
        self.toggle_button.clicked.connect(self._toggle_crew)
        header.add_action(self.toggle_button)
        self.root.addWidget(header)

        filters_card = Card(margins=12, spacing=8)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = SearchLineEdit("Buscar cuadrilla...")
        self.search.textChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.search, 1)
        self.include_inactive = QCheckBox("Incluir inactivas")
        self.include_inactive.setChecked(False)
        self.include_inactive.toggled.connect(lambda _: self.refresh())
        filters.addWidget(self.include_inactive)
        filters_card.layout.addLayout(filters)
        self.root.addWidget(filters_card)

        content = QHBoxLayout()
        content.setSpacing(14)
        left_card = Card(margins=14, spacing=8)
        left_head = QHBoxLayout()
        left_title = QLabel("Listado")
        left_title.setObjectName("SectionTitle")
        left_head.addWidget(left_title, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        left_head.addWidget(self.count_label)
        left_card.layout.addLayout(left_head)
        self.table = QTableWidget()
        setup_table(
            self.table,
            ["Cuadrilla", "Estado", "Asignadas", "Entregas"],
            stretch=0,
            column_widths={1: 80, 2: 80, 3: 80},
        )
        self.table.itemSelectionChanged.connect(self._load_detail)
        left_card.layout.addWidget(self.table, 1)
        content.addWidget(left_card, 1)

        right_card = Card(margins=16, spacing=10)
        detail_head = QHBoxLayout()
        self.detail_title = QLabel("Seleccione una cuadrilla")
        self.detail_title.setObjectName("PageTitle")
        self.detail_title.setStyleSheet("font-size: 15pt;")
        detail_head.addWidget(self.detail_title, 1)
        right_card.layout.addLayout(detail_head)
        self.detail_subtitle = QLabel("")
        self.detail_subtitle.setObjectName("PageSubtitle")
        right_card.layout.addWidget(self.detail_subtitle)
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.units_card = self._metric_card("Unidades asignadas", "0")
        self.articles_card = self._metric_card("Articulos pendientes", "0")
        self.deliveries_card = self._metric_card("Entregas activas", "0")
        metrics.addWidget(self.units_card)
        metrics.addWidget(self.articles_card)
        metrics.addWidget(self.deliveries_card)
        right_card.layout.addLayout(metrics)

        balance_title = QLabel("Materiales pendientes de devolucion")
        balance_title.setObjectName("SectionTitle")
        right_card.layout.addWidget(balance_title)
        self.balance_table = QTableWidget()
        setup_table(
            self.balance_table,
            ["Articulo", "Cantidad pendiente"],
            stretch=0,
            column_widths={1: 140},
        )
        self.balance_table.setMinimumHeight(150)
        right_card.layout.addWidget(self.balance_table, 1)

        history_title = QLabel("Ultimas entregas")
        history_title.setObjectName("SectionTitle")
        right_card.layout.addWidget(history_title)
        self.history_table = QTableWidget()
        setup_table(
            self.history_table,
            ["Codigo", "Fecha", "Unidades", "IClass", "Estado"],
            stretch=0,
            column_widths={0: 145, 1: 120, 2: 75, 3: 95, 4: 80},
        )
        self.history_table.setMinimumHeight(150)
        right_card.layout.addWidget(self.history_table, 1)
        content.addWidget(right_card, 2)
        self.root.addLayout(content, 1)

    def _metric_card(self, title: str, value: str) -> Card:
        card = Card(margins=12, spacing=2)
        label = QLabel(title)
        label.setObjectName("TinyMuted")
        number = QLabel(value)
        number.setObjectName("SectionTitle")
        number.setStyleSheet("font-size: 16pt;")
        card.layout.addWidget(label)
        card.layout.addWidget(number)
        card.value_label = number
        return card

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        previous = selected_id(self.table)
        try:
            with session_scope() as session:
                crews = list_crews(session, include_inactive=self.include_inactive.isChecked())
                search = self.search.text().strip().lower()
                if search:
                    crews = [crew for crew in crews if search in crew.name.lower()]
                rows = []
                for crew in crews:
                    summary = crew_summary(session, crew.id)
                    rows.append(
                        {
                            "id": crew.id,
                            "name": crew.name,
                            "active": crew.is_active,
                            "assigned": summary["assigned_units"],
                            "articles": summary["assigned_articles"],
                            "deliveries": summary["delivery_count"],
                        }
                    )
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.table
        clear_table(table)
        table.setRowCount(len(rows))
        selected_row = -1
        for row, data in enumerate(rows):
            status_text, color, bg = (
                ("Activa", COLORS["success"], COLORS["success_soft"])
                if data["active"]
                else ("Inactiva", COLORS["muted"], "#e2e8f0")
            )
            set_row(
                table,
                row,
                [
                    make_item(data["name"], data=data["id"], bold=True),
                    make_item(status_text, color=color, bg=bg, bold=True),
                    make_item(fmt_int(data["assigned"]), sort_value=data["assigned"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(fmt_int(data["deliveries"]), sort_value=data["deliveries"], align=Qt.AlignRight | Qt.AlignVCenter),
                ],
            )
            if data["id"] == previous:
                selected_row = row
        finish_table(table, sortable=False)
        self.count_label.setText(f"{len(rows)}")
        if rows:
            table.selectRow(selected_row if selected_row >= 0 else 0)
        else:
            self._clear_detail()
        self._update_toggle_button()

    def _selected_crew_id(self) -> int | None:
        return selected_id(self.table)

    def _clear_detail(self) -> None:
        self.detail_title.setText("Seleccione una cuadrilla")
        self.detail_subtitle.setText("")
        self.units_card.value_label.setText("0")
        self.articles_card.value_label.setText("0")
        self.deliveries_card.value_label.setText("0")
        self.balance_table.setRowCount(0)
        self.history_table.setRowCount(0)
        self.edit_button.setEnabled(False)
        self.toggle_button.setEnabled(False)

    def _load_detail(self) -> None:
        crew_id = self._selected_crew_id()
        if crew_id is None:
            self._clear_detail()
            return
        try:
            with session_scope() as session:
                summary = crew_summary(session, crew_id)
                crew = summary["crew"]
                balances = [
                    {"name": row["name"], "quantity": row["quantity"]}
                    for row in summary["balances"]
                ]
                deliveries = [
                    {
                        "code": delivery.code,
                        "created_at": delivery.created_at,
                        "units": delivery.total_units,
                        "iclass": delivery.iclass_status,
                        "status": delivery.status,
                    }
                    for delivery in summary["deliveries"][:10]
                ]
                self.detail_title.setText(crew.name)
                notes = f"  |  {crew.notes}" if crew.notes else ""
                self.detail_subtitle.setText(
                    ("Activa" if crew.is_active else "Inactiva") + notes
                )
                self.units_card.value_label.setText(fmt_int(summary["assigned_units"]))
                self.articles_card.value_label.setText(fmt_int(summary["assigned_articles"]))
                self.deliveries_card.value_label.setText(fmt_int(summary["delivery_count"]))
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.balance_table
        clear_table(table)
        table.setRowCount(len(balances))
        for row, data in enumerate(balances):
            set_row(
                table,
                row,
                [
                    make_item(data["name"]),
                    make_item(fmt_int(data["quantity"]), sort_value=data["quantity"], align=Qt.AlignRight | Qt.AlignVCenter),
                ],
            )
        finish_table(table, sortable=False)
        history = self.history_table
        clear_table(history)
        history.setRowCount(len(deliveries))
        for row, data in enumerate(deliveries):
            iclass_text = "Cargada" if data["iclass"] == ICLASS_LOADED else "Pendiente"
            iclass_color = COLORS["success"] if data["iclass"] == ICLASS_LOADED else COLORS["warning"]
            if data["status"] == DELIVERY_VOIDED:
                state_text = "Anulada"
                state_color = COLORS["danger"]
                row_color = COLORS["muted"]
            else:
                state_text = "Activa"
                state_color = COLORS["success"]
                row_color = None
            set_row(
                history,
                row,
                [
                    make_item(data["code"], color=row_color, bold=True),
                    make_item(fmt_datetime(data["created_at"]), color=row_color),
                    make_item(fmt_int(data["units"]), sort_value=data["units"], align=Qt.AlignRight | Qt.AlignVCenter, color=row_color),
                    make_item(iclass_text, color=iclass_color),
                    make_item(state_text, color=state_color),
                ],
            )
        finish_table(history, sortable=False)
        self._update_toggle_button()

    def _update_toggle_button(self) -> None:
        crew_id = self._selected_crew_id()
        self.edit_button.setEnabled(crew_id is not None)
        self.toggle_button.setEnabled(crew_id is not None)
        if crew_id is None:
            self.toggle_button.setText("Desactivar")
            return
        try:
            with session_scope() as session:
                crew = get_crew(session, crew_id)
                self.toggle_button.setText("Activar" if not crew.is_active else "Desactivar")
        except Exception:
            pass

    def _new_crew(self) -> None:
        dialog = CrewFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            with session_scope() as session:
                create_crew(session, name=values["name"], notes=values["notes"])
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "La cuadrilla fue creada correctamente.")

    def _edit_crew(self) -> None:
        crew_id = self._selected_crew_id()
        if crew_id is None:
            show_warning(self, "Seleccione una cuadrilla.")
            return
        try:
            with session_scope() as session:
                crew = get_crew(session, crew_id)
                name = crew.name
                notes = crew.notes
                is_active = crew.is_active
        except Exception as exc:
            show_error(self, exc)
            return

        class _Snapshot:
            pass

        snapshot = _Snapshot()
        snapshot.name = name
        snapshot.notes = notes
        snapshot.is_active = is_active
        dialog = CrewFormDialog(snapshot, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            with session_scope() as session:
                update_crew(session, crew_id, values["name"], values["notes"])
                if values["is_active"] != is_active:
                    set_crew_active(session, crew_id, values["is_active"])
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()

    def _toggle_crew(self) -> None:
        crew_id = self._selected_crew_id()
        if crew_id is None:
            return
        try:
            with session_scope() as session:
                crew = get_crew(session, crew_id)
                activate = not crew.is_active
                name = crew.name
        except Exception as exc:
            show_error(self, exc)
            return
        if not activate and not confirm(
            self,
            "Desactivar cuadrilla",
            f"La cuadrilla '{name}' dejara de estar disponible para nuevas entregas. "
            "Debe tener todos los materiales devueltos.",
            "Desactivar",
        ):
            return
        try:
            with session_scope() as session:
                set_crew_active(session, crew_id, activate)
        except AppError as exc:
            show_error(self, exc)
            return
        self.refresh()
        self.mark_changed()
        show_info(self, "Cuadrilla activada." if activate else "Cuadrilla desactivada.")
