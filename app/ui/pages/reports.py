"""Generacion y exportacion de informes."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.db.database import session_scope
from app.domain import MOVEMENT_TYPES
from app.services.crews import crew_options
from app.services.reports import (
    report_daily,
    report_historical,
    report_monthly,
    report_weekly,
)
from app.ui.common import (
    Card,
    PageHeader,
    SearchLineEdit,
    clear_table,
    finish_table,
    make_button,
    make_item,
    set_row,
    setup_table,
    show_error,
    show_info,
    fmt_date,
    fmt_datetime,
    fmt_int,
)
from app.ui.pages.base import BasePage
from app.utils.dates import now, week_range
from app.utils.excel import export_report_to_excel

MONTHS = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


class ReportsPage(BasePage):
    page_key = "reports"
    title = "Informes"
    subtitle = "Reportes operativos y exportacion a Excel."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.report: dict | None = None
        header = PageHeader(
            "Informes",
            "Genere reportes diarios, semanales, mensuales o historicos y exportelos a Excel.",
        )
        generate_button = make_button("Generar informe", "primary", "reports")
        generate_button.clicked.connect(self._generate)
        header.add_action(generate_button)
        self.export_button = make_button("Exportar a Excel", "secondary", "download")
        self.export_button.clicked.connect(self._export)
        self.export_button.setEnabled(False)
        header.add_action(self.export_button)
        self.root.addWidget(header)

        filter_card = Card(margins=12, spacing=8)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("Tipo de informe"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Diario", "daily")
        self.kind_combo.addItem("Semanal", "weekly")
        self.kind_combo.addItem("Mensual", "monthly")
        self.kind_combo.addItem("Historico", "historical")
        self.kind_combo.currentIndexChanged.connect(self._update_filters)
        row1.addWidget(self.kind_combo)

        self.daily_group = self._date_group("Fecha", QDate.currentDate())
        row1.addWidget(self.daily_group[0])
        self.daily_date = self.daily_group[1]

        today = date.today()
        week_start, week_end = week_range(today)
        self.week_group_start = self._date_group("Semana desde", QDate(week_start.year, week_start.month, week_start.day))
        row1.addWidget(self.week_group_start[0])
        self.week_start = self.week_group_start[1]
        self.week_group_end = self._date_group("Hasta", QDate(week_end.year, week_end.month, week_end.day))
        row1.addWidget(self.week_group_end[0])
        self.week_end = self.week_group_end[1]

        self.month_group = self._month_group()
        row1.addWidget(self.month_group[0])
        self.month_combo = self.month_group[1]
        self.year_spin = self.month_group[2]

        first = today.replace(day=1)
        self.hist_group_start = self._date_group("Desde", QDate(first.year, first.month, first.day))
        row1.addWidget(self.hist_group_start[0])
        self.hist_from = self.hist_group_start[1]
        self.hist_group_end = self._date_group("Hasta", QDate.currentDate())
        row1.addWidget(self.hist_group_end[0])
        self.hist_to = self.hist_group_end[1]
        row1.addStretch(1)
        filter_card.layout.addLayout(row1)

        self.history_filters = QWidget()
        row2 = QHBoxLayout(self.history_filters)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.addWidget(QLabel("Cuadrilla"))
        self.crew_combo = QComboBox()
        self.crew_combo.addItem("Todas", None)
        row2.addWidget(self.crew_combo)
        row2.addWidget(QLabel("Tipo de movimiento"))
        self.movement_combo = QComboBox()
        self.movement_combo.addItem("Todos", None)
        for key, label in MOVEMENT_TYPES.items():
            self.movement_combo.addItem(label, key)
        row2.addWidget(self.movement_combo)
        self.hist_search = SearchLineEdit("Buscar en observaciones o articulo...")
        row2.addWidget(self.hist_search, 1)
        filter_card.layout.addWidget(self.history_filters)
        self.root.addWidget(filter_card)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("ReportScroll")
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content.setObjectName("ReportContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 6, 0)
        self.content_layout.setSpacing(12)
        self.content_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        self.root.addWidget(self.scroll, 1)
        self._update_filters()

    def _date_group(self, label: str, value: QDate) -> tuple[QWidget, QDateEdit]:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        text = QLabel(label)
        layout.addWidget(text)
        edit = QDateEdit(value)
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(edit)
        return widget, edit

    def _month_group(self) -> tuple[QWidget, QComboBox, QSpinBox]:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        text = QLabel("Mes")
        layout.addWidget(text)
        combo = QComboBox()
        for index, month in enumerate(MONTHS, start=1):
            combo.addItem(month, index)
        combo.setCurrentIndex(date.today().month - 1)
        layout.addWidget(combo)
        year = QSpinBox()
        year.setRange(2000, 2100)
        year.setValue(date.today().year)
        layout.addWidget(year)
        return widget, combo, year

    def _update_filters(self) -> None:
        kind = self.kind_combo.currentData()
        self.daily_group[0].setVisible(kind == "daily")
        self.week_group_start[0].setVisible(kind == "weekly")
        self.week_group_end[0].setVisible(kind == "weekly")
        self.month_group[0].setVisible(kind == "monthly")
        is_hist = kind == "historical"
        self.hist_group_start[0].setVisible(is_hist)
        self.hist_group_end[0].setVisible(is_hist)
        self.history_filters.setVisible(is_hist)

    def refresh(self) -> None:
        self._generate(silent=True)

    def activate(self) -> None:
        current = self.crew_combo.currentData()
        self.crew_combo.blockSignals(True)
        self.crew_combo.clear()
        self.crew_combo.addItem("Todas", None)
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
        self._generate(silent=True)

    def _generate(self, silent: bool = False) -> None:
        kind = self.kind_combo.currentData()
        try:
            with session_scope() as session:
                if kind == "daily":
                    report = report_daily(session, self.daily_date.date().toPython())
                elif kind == "weekly":
                    report = report_weekly(
                        session,
                        self.week_start.date().toPython(),
                        self.week_end.date().toPython(),
                    )
                elif kind == "monthly":
                    report = report_monthly(
                        session,
                        self.year_spin.value(),
                        self.month_combo.currentData(),
                    )
                else:
                    movement_type = self.movement_combo.currentData()
                    report = report_historical(
                        session,
                        start=self.hist_from.date().toPython(),
                        end=self.hist_to.date().toPython(),
                        crew_id=self.crew_combo.currentData(),
                        movement_types=[movement_type] if movement_type else None,
                        search=self.hist_search.text(),
                    )
        except Exception as exc:
            show_error(self, exc)
            return
        self.report = report
        self.export_button.setEnabled(True)
        self._render(report)
        if not silent:
            show_info(self, "El informe fue generado correctamente.")

    def _clear_content(self) -> None:
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render(self, report: dict) -> None:
        self._clear_content()
        header = Card(margins=18, spacing=4)
        title = QLabel(report.get("title", "Informe"))
        title.setObjectName("PageTitle")
        title.setStyleSheet("font-size: 16pt;")
        header.layout.addWidget(title)
        subtitle = QLabel(report.get("subtitle", ""))
        subtitle.setObjectName("PageSubtitle")
        header.layout.addWidget(subtitle)
        filters = report.get("filters") or []
        filter_text = "    ".join(f"{key}: {value}" for key, value in filters)
        details = QLabel(
            filter_text
            + ("    |    " if filter_text else "")
            + f"Generado: {fmt_datetime(report.get('generated_at'))}"
        )
        details.setObjectName("Muted")
        details.setWordWrap(True)
        header.layout.addWidget(details)
        self.content_layout.insertWidget(self.content_layout.count() - 1, header)

        for section in report.get("sections") or []:
            self._render_section(report, section)

    def _render_section(self, report: dict, section: dict) -> None:
        card = Card(margins=14, spacing=6)
        head = QHBoxLayout()
        title = QLabel(section.get("title", "Seccion"))
        title.setObjectName("SectionTitle")
        head.addWidget(title, 1)
        rows = section.get("rows") or []
        count = QLabel(f"{fmt_int(len(rows))} fila(s)")
        count.setObjectName("Muted")
        head.addWidget(count)
        card.layout.addLayout(head)
        if not rows:
            empty = QLabel("Sin registros para el periodo seleccionado.")
            empty.setObjectName("Muted")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(60)
            card.layout.addWidget(empty)
        else:
            table = QTableWidget()
            columns = list(section.get("columns") or [])
            setup_table(table, columns, stretch=max(0, len(columns) - 1), row_height=34)
            table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                items = []
                for col_index, value in enumerate(row):
                    items.append(self._cell(value))
                set_row(table, row_index, items)
            finish_table(table, sortable=False)
            table.setMinimumHeight(120)
            table.setMaximumHeight(min(380, 40 + len(rows) * 35))
            card.layout.addWidget(table)
            totals_text = self._totals_text(section, columns, rows)
            if totals_text:
                total_label = QLabel(totals_text)
                total_label.setObjectName("Muted")
                total_label.setStyleSheet("font-weight: 600; color: #334155;")
                card.layout.addWidget(total_label)
        self.content_layout.insertWidget(self.content_layout.count() - 1, card)

    def _cell(self, value):
        if value is None or value == "":
            return make_item("")
        if isinstance(value, datetime):
            return make_item(
                fmt_datetime(value),
                sort_value=value.timestamp(),
            )
        if isinstance(value, date):
            return make_item(fmt_date(value), sort_value=value.toordinal())
        if isinstance(value, bool):
            return make_item("Si" if value else "No")
        if isinstance(value, (int, float)):
            return make_item(
                fmt_int(value) if isinstance(value, int) else f"{value:,.2f}",
                sort_value=value,
                align=Qt.AlignRight | Qt.AlignVCenter,
            )
        text = str(value)
        if "anulad" in text.lower():
            return make_item(text, color="#dc2626")
        if "pendiente" in text.lower():
            return make_item(text, color="#b45309")
        if "cargada" in text.lower() or "vigente" in text.lower():
            return make_item(text, color="#15803d")
        return make_item(text, tooltip=text)

    @staticmethod
    def _totals_text(section: dict, columns: list[str], rows: list[list]) -> str:
        if not section.get("totals"):
            return ""
        parts = []
        for index, column in enumerate(columns):
            values = [
                row[index]
                for row in rows
                if index < len(row) and isinstance(row[index], (int, float)) and not isinstance(row[index], bool)
            ]
            if values and len(values) == len(rows):
                parts.append(f"{column}: {fmt_int(sum(values))}")
        return "Totales  |  " + "    ".join(parts) if parts else ""

    def _export(self) -> None:
        if self.report is None:
            show_info(self, "Genere un informe antes de exportarlo.")
            return
        default_dir = Path.home() / "Documents"
        default_dir.mkdir(parents=True, exist_ok=True)
        stamp = now().strftime("%Y%m%d_%H%M")
        raw_name = re.sub(r"[^A-Za-z0-9_-]+", "_", self.report.get("title", "informe")).strip("_")
        suggested = default_dir / f"{raw_name}_{stamp}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar informe a Excel",
            str(suggested),
            "Libro de Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            target = export_report_to_excel(self.report, path)
        except Exception as exc:
            show_error(self, exc)
            return
        show_info(self, f"El informe fue exportado a:\n{target}")
