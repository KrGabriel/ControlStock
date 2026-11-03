"""Panel principal con indicadores, graficos y resumenes."""
from __future__ import annotations

from datetime import datetime

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.db.database import session_scope
from app.domain import DELIVERY_ACTIVE, ICLASS_PENDING, ICLASS_STATUSES, MOVEMENT_TYPES
from app.services.dashboard import get_dashboard_data
from app.services.iclass import pending_deliveries
from app.ui.common import (
    Card,
    EmptyState,
    PageHeader,
    StatCard,
    clear_table,
    finish_table,
    make_button,
    make_item,
    section_title,
    set_row,
    setup_table,
    show_error,
)
from app.ui.icons import make_icon
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS
from app.utils.dates import fmt_datetime, fmt_time
from app.utils.numbers import fmt_int

pg.setConfigOptions(antialias=True)
pg.setConfigOption("foreground", "#64748b")
pg.setConfigOption("background", "w")


class ChartCard(Card):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent, margins=16, spacing=6)
        header = QHBoxLayout()
        header.setSpacing(8)
        title_box = section_title(title, subtitle)
        header.addWidget(title_box, 1)
        self.legend_layout = QHBoxLayout()
        self.legend_layout.setSpacing(10)
        header.addLayout(self.legend_layout)
        self.layout.addLayout(header)
        self.stack = QStackedLayout()
        self.plot = pg.PlotWidget()
        self.plot.setBackground(QColor(255, 255, 255, 0))
        self.plot.setMinimumHeight(205)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.getPlotItem().hideAxis("top")
        self.plot.getPlotItem().hideAxis("right")
        for axis_name in ("left", "bottom"):
            axis = self.plot.getAxis(axis_name)
            axis.setPen(pg.mkPen("#e2e8f0"))
            axis.setTextPen(pg.mkPen("#64748b"))
            axis.setStyle(tickFont=QFont("Segoe UI", 8))
        self.plot.showGrid(x=False, y=True, alpha=0.15)
        self.empty = QLabel("Sin datos para mostrar")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        holder = QWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(self.stack)
        self.stack.addWidget(self.plot)
        self.stack.addWidget(self.empty)
        self.layout.addWidget(holder, 1)

    def reset(self) -> None:
        self.plot.clear()
        self.plot.getAxis("bottom").setTicks(None)
        self.plot.getAxis("left").setTicks(None)

    def add_legend(self, items: list[tuple[str, str]]) -> None:
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for label, color in items:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
            text = QLabel(label)
            text.setStyleSheet("color: #64748b; font-size: 8pt;")
            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lay.addWidget(dot)
            lay.addWidget(text)
            self.legend_layout.addWidget(wrap)

    def show_plot(self) -> None:
        self.stack.setCurrentWidget(self.plot)

    def show_empty(self, text: str = "Sin datos para mostrar") -> None:
        self.empty.setText(text)
        self.stack.setCurrentWidget(self.empty)


class DashboardPage(BasePage):
    page_key = "dashboard"
    title = "Dashboard"
    subtitle = "Vision general del inventario y la operacion diaria."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setObjectName("DashboardContent")
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setContentsMargins(26, 22, 26, 26)
        self.container_layout.setSpacing(16)
        scroll.setWidget(container)
        self.root.addWidget(scroll)

        header = PageHeader("Dashboard", "Estado general del stock, entregas y pendientes.")
        self.updated_label = QLabel("")
        self.updated_label.setObjectName("TinyMuted")
        header.add_action(self.updated_label)
        refresh_button = make_button("Actualizar", "secondary", "refresh")
        refresh_button.clicked.connect(self.refresh)
        header.add_action(refresh_button)
        self.container_layout.addWidget(header)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(14)
        cards_grid.setVerticalSpacing(14)
        self.stat_cards: dict[str, StatCard] = {}
        card_defs = [
            ("articles", "Articulos registrados", "inventory", COLORS["primary"], "Activos en catalogo"),
            ("available", "Unidades disponibles", "box", COLORS["success"], "Stock principal"),
            ("assigned", "Unidades entregadas", "delivery", COLORS["purple"], "En poder de cuadrillas"),
            ("low_stock", "Articulos con stock bajo", "warning", COLORS["warning"], "En o por debajo del minimo"),
            ("movements_today", "Movimientos de hoy", "movements", COLORS["teal"], "Operaciones registradas"),
            ("pending_iclass", "Pendientes de IClass", "iclass", COLORS["danger"], "Entregas sin cargar"),
            ("repair_out", "Reparacion / fuera de servicio", "settings", "#b45309", "Unidades no disponibles"),
        ]
        for index, (key, title, icon, accent, hint) in enumerate(card_defs):
            card = StatCard(title, icon, accent, hint)
            self.stat_cards[key] = card
            cards_grid.addWidget(card, index // 4, index % 4)
        self.container_layout.addLayout(cards_grid)

        charts = QGridLayout()
        charts.setHorizontalSpacing(14)
        charts.setVerticalSpacing(14)
        self.chart_movements = ChartCard(
            "Movimientos de stock", "Unidades entregadas y devueltas - ultimos 7 dias"
        )
        self.chart_crew = ChartCard("Distribucion por cuadrilla", "Unidades reutilizables asignadas")
        self.chart_top = ChartCard("Articulos con mayor movimiento", "Ultimos 30 dias")
        self.chart_month = ChartCard("Evolucion de entregas", "Cantidad de entregas en el mes actual")
        charts.addWidget(self.chart_movements, 0, 0)
        charts.addWidget(self.chart_crew, 0, 1)
        charts.addWidget(self.chart_top, 1, 0)
        charts.addWidget(self.chart_month, 1, 1)
        charts.setColumnStretch(0, 1)
        charts.setColumnStretch(1, 1)
        self.container_layout.addLayout(charts)

        bottom = QGridLayout()
        bottom.setHorizontalSpacing(14)
        bottom.setVerticalSpacing(14)
        bottom.setColumnStretch(0, 3)
        bottom.setColumnStretch(1, 2)

        movements_card = Card(margins=16, spacing=8)
        movements_header = QHBoxLayout()
        movements_header.addWidget(section_title("Ultimos movimientos", "Actividad reciente del inventario"), 1)
        movements_card.layout.addLayout(movements_header)
        self.movements_table = self._make_table(
            ["Hora", "Tipo", "Articulo", "Cant.", "Cuadrilla"], 2
        )
        movements_card.layout.addWidget(self.movements_table)
        bottom.addWidget(movements_card, 0, 0)

        alerts_card = Card(margins=16, spacing=8)
        alerts_card.layout.addWidget(section_title("Alertas de stock", "Articulos que requieren reposicion"))
        self.alerts_table = self._make_table(["Articulo", "Disp.", "Min.", "Estado"], 0)
        alerts_card.layout.addWidget(self.alerts_table)
        bottom.addWidget(alerts_card, 0, 1)

        deliveries_card = Card(margins=16, spacing=8)
        deliveries_card.layout.addWidget(section_title("Ultimas entregas", "Movimientos hacia cuadrillas"))
        self.deliveries_table = self._make_table(
            ["Hora", "Codigo", "Cuadrilla", "Unid.", "IClass"], 2
        )
        deliveries_card.layout.addWidget(self.deliveries_table)
        bottom.addWidget(deliveries_card, 1, 0)

        pending_card = Card(margins=16, spacing=8)
        pending_card.layout.addWidget(
            section_title("Pendientes de IClass", "Requieren carga en el sistema principal")
        )
        self.pending_table = self._make_table(["Hora", "Codigo", "Cuadrilla", "Unid."], 2)
        pending_card.layout.addWidget(self.pending_table)
        bottom.addWidget(pending_card, 1, 1)
        self.container_layout.addLayout(bottom)
        self.container_layout.addStretch(1)

    def _make_table(self, headers: list[str], stretch: int):
        from PySide6.QtWidgets import QTableWidget

        table = QTableWidget()
        setup_table(table, headers, stretch=stretch)
        table.setMinimumHeight(190)
        table.setMaximumHeight(240)
        table.setSelectionMode(table.SelectionMode.NoSelection)
        return table

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                data = get_dashboard_data(session)
        except Exception as exc:
            show_error(self, exc)
            return
        cards = data["cards"]
        for key, card in self.stat_cards.items():
            value = cards.get(key, 0)
            card.set_value(fmt_int(value))
        self.updated_label.setText(f"Actualizado {fmt_datetime(data['generated_at'])}")
        self._render_movements_chart(data)
        self._render_crew_chart(data)
        self._render_top_chart(data)
        self._render_month_chart(data)
        self._render_tables(data)

    def _render_movements_chart(self, data: dict) -> None:
        chart = self.chart_movements
        chart.reset()
        chart.add_legend(
            [("Entregadas", COLORS["primary"]), ("Devueltas", COLORS["success"])]
        )
        delivered = data["delivered_by_day"]
        returned = data["returned_by_day"]
        if not any(delivered) and not any(returned):
            chart.show_empty()
            return
        chart.show_plot()
        import numpy as np

        x = np.arange(len(data["days"]))
        chart.plot.addItem(
            pg.BarGraphItem(
                x=x - 0.19,
                height=delivered,
                width=0.36,
                brush=pg.mkBrush(COLORS["primary"]),
                pen=pg.mkPen(None),
                name="Entregadas",
            )
        )
        chart.plot.addItem(
            pg.BarGraphItem(
                x=x + 0.19,
                height=returned,
                width=0.36,
                brush=pg.mkBrush(COLORS["success"]),
                pen=pg.mkPen(None),
                name="Devueltas",
            )
        )
        labels = [(i, day.strftime("%d/%m")) for i, day in enumerate(data["days"])]
        chart.plot.getAxis("bottom").setTicks([labels])
        chart.plot.getPlotItem().getViewBox().setLimits(xMin=-0.6, xMax=len(x) - 0.4)

    def _render_crew_chart(self, data: dict) -> None:
        chart = self.chart_crew
        chart.reset()
        chart.add_legend([("Unidades asignadas", COLORS["purple"])])
        rows = data["crew_distribution"]
        if not rows:
            chart.show_empty("No hay materiales asignados")
            return
        chart.show_plot()
        rows = rows[:8]
        names = [crew.name for crew, _ in rows]
        values = [value for _, value in rows]
        y = list(range(len(rows)))
        chart.plot.addItem(
            pg.BarGraphItem(
                x0=0,
                y0=y,
                width=values,
                height=0.55,
                brush=pg.mkBrush(COLORS["purple"]),
                pen=pg.mkPen(None),
            )
        )
        chart.plot.getAxis("left").setTicks(
            [[(i, name) for i, name in enumerate(names)]]
        )
        chart.plot.getPlotItem().getViewBox().invertY(True)
        chart.plot.getPlotItem().getViewBox().setLimits(xMin=0)

    def _render_top_chart(self, data: dict) -> None:
        chart = self.chart_top
        chart.reset()
        chart.add_legend([("Unidades movidas", COLORS["teal"])])
        rows = data["top_items"]
        if not rows:
            chart.show_empty("Sin movimientos en el periodo")
            return
        chart.show_plot()
        names = [
            (name[:24] + "...") if len(name) > 27 else name for name, _ in rows
        ]
        values = [value for _, value in rows]
        y = list(range(len(rows)))
        chart.plot.addItem(
            pg.BarGraphItem(
                x0=0,
                y0=y,
                width=values,
                height=0.55,
                brush=pg.mkBrush(COLORS["teal"]),
                pen=pg.mkPen(None),
            )
        )
        chart.plot.getAxis("left").setTicks(
            [[(i, name) for i, name in enumerate(names)]]
        )
        chart.plot.getPlotItem().getViewBox().invertY(True)
        chart.plot.getPlotItem().getViewBox().setLimits(xMin=0)

    def _render_month_chart(self, data: dict) -> None:
        chart = self.chart_month
        chart.reset()
        chart.add_legend([("Entregas por dia", COLORS["primary"])])
        values = data["deliveries_by_day"]
        if not any(values):
            chart.show_empty("Sin entregas registradas este mes")
            return
        chart.show_plot()
        days = data["month_days"]
        x = list(range(1, len(days) + 1))
        curve = chart.plot.plot(
            x,
            values,
            pen=pg.mkPen(COLORS["primary"], width=2),
            symbol="o",
            symbolSize=4,
            symbolBrush=pg.mkBrush(COLORS["primary"]),
            symbolPen=pg.mkPen(None),
            fillLevel=0,
            brush=pg.mkBrush(37, 99, 235, 35),
        )
        ticks = [
            (i, days[i - 1].strftime("%d")) for i in range(1, len(days) + 1, 5)
        ]
        if (len(days), days[-1].strftime("%d")) not in ticks:
            ticks.append((len(days), days[-1].strftime("%d")))
        chart.plot.getAxis("bottom").setTicks([ticks])

    def _render_tables(self, data: dict) -> None:
        table = self.movements_table
        clear_table(table)
        movements = data["latest_movements"]
        table.setRowCount(len(movements))
        for row, movement in enumerate(movements):
            type_label = MOVEMENT_TYPES.get(movement.movement_type, movement.movement_type)
            crew_name = movement.crew.name if movement.crew else ""
            set_row(
                table,
                row,
                [
                    make_item(fmt_time(movement.created_at), sort_value=movement.created_at),
                    make_item(type_label),
                    make_item(movement.item_name_snapshot),
                    make_item(
                        fmt_int(movement.quantity),
                        sort_value=movement.quantity,
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                    make_item(crew_name),
                ],
            )
        finish_table(table, sortable=False)

        table = self.alerts_table
        clear_table(table)
        alerts = data["alerts"]
        table.setRowCount(len(alerts))
        for row, item in enumerate(alerts):
            if item.qty_available <= 0:
                status, color, bg = "Sin stock", COLORS["danger"], COLORS["danger_soft"]
            else:
                status, color, bg = "Stock bajo", COLORS["warning"], COLORS["warning_soft"]
            set_row(
                table,
                row,
                [
                    make_item(item.name),
                    make_item(
                        fmt_int(item.qty_available),
                        sort_value=item.qty_available,
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                    make_item(
                        fmt_int(item.stock_min),
                        sort_value=item.stock_min,
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                    make_item(status, color=color, bg=bg, bold=True),
                ],
            )
        finish_table(table, sortable=False)

        table = self.deliveries_table
        clear_table(table)
        deliveries = data["latest_deliveries"]
        table.setRowCount(len(deliveries))
        for row, delivery in enumerate(deliveries):
            status = ICLASS_STATUSES.get(delivery.iclass_status, delivery.iclass_status)
            color = COLORS["warning"] if delivery.iclass_status == ICLASS_PENDING else COLORS["success"]
            set_row(
                table,
                row,
                [
                    make_item(fmt_time(delivery.created_at), sort_value=delivery.created_at),
                    make_item(delivery.code),
                    make_item(delivery.crew.name),
                    make_item(
                        fmt_int(delivery.total_units),
                        sort_value=delivery.total_units,
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                    make_item(status, color=color),
                ],
            )
        finish_table(table, sortable=False)

        table = self.pending_table
        clear_table(table)
        pending = data["pending_iclass"]
        table.setRowCount(len(pending))
        for row, delivery in enumerate(pending):
            set_row(
                table,
                row,
                [
                    make_item(fmt_time(delivery.created_at), sort_value=delivery.created_at),
                    make_item(delivery.code),
                    make_item(delivery.crew.name),
                    make_item(
                        fmt_int(delivery.total_units),
                        sort_value=delivery.total_units,
                        align=Qt.AlignRight | Qt.AlignVCenter,
                    ),
                ],
            )
        finish_table(table, sortable=False)
