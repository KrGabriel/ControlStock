"""Ventana principal con menu lateral y paginas integradas."""
from __future__ import annotations

import importlib
import logging

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.db.database import session_scope
from app.services import backups
from app.services.iclass import pending_deliveries
from app.services.settings import get_bool
from app.session import SessionUser
from app.ui.common import confirm, show_warning
from app.ui.icons import make_icon
from app.ui.pages.base import BasePage
from app.ui.theme import COLORS
from app.utils.dates import now

logger = logging.getLogger(__name__)

PAGE_SPECS = [
    ("dashboard", "Dashboard", "dashboard", "app.ui.pages.dashboard", "DashboardPage"),
    ("inventory", "Inventario", "inventory", "app.ui.pages.inventory", "InventoryPage"),
    ("deliveries", "Entregas", "delivery", "app.ui.pages.deliveries", "DeliveriesPage"),
    ("returns", "Devoluciones", "return", "app.ui.pages.returns", "ReturnsPage"),
    ("crews", "Cuadrillas", "crews", "app.ui.pages.crews", "CrewsPage"),
    ("movements", "Movimientos", "movements", "app.ui.pages.movements", "MovementsPage"),
    ("stock_in", "Ingresos de stock", "income", "app.ui.pages.stock_in", "StockInPage"),
    ("counts", "Recuento fisico", "count", "app.ui.pages.counts", "CountsPage"),
    ("reports", "Informes", "reports", "app.ui.pages.reports", "ReportsPage"),
    (
        "iclass",
        "Pendientes de IClass",
        "iclass",
        "app.ui.pages.iclass_pending",
        "IClassPendingPage",
    ),
    ("settings", "Configuracion", "settings", "app.ui.pages.settings", "SettingsPage"),
]

GROUPS = [
    ("OPERACION", ["dashboard", "inventory", "deliveries", "returns", "crews"]),
    ("CONTROL", ["movements", "stock_in", "counts", "reports", "iclass"]),
    ("SISTEMA", ["settings"]),
]


class NavButton(QPushButton):
    def __init__(self, text: str, icon_name: str, parent=None):
        super().__init__(text, parent)
        self.setProperty("class", "nav")
        self.setCheckable(True)
        self.setIcon(make_icon(icon_name, "#94a3b8", 18))
        self.setIconSize(self.iconSize().expandedTo(self.iconSize()))
        from PySide6.QtCore import QSize

        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)


class MainWindow(QMainWindow):
    logged_out = Signal()
    closed = Signal()

    def __init__(self, user: SessionUser):
        super().__init__()
        self.user = user
        self.pages: dict[str, BasePage] = {}
        self.buttons: dict[str, NavButton] = {}
        self._logout_in_progress = False
        self._close_confirmed = False
        self.setWindowTitle(f"{APP_NAME} - Gestion de inventario")
        self.setWindowIcon(make_icon("box", COLORS["primary"], 32))
        self.setMinimumSize(1180, 760)
        self.resize(1440, 900)

        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), 1)

        self._build_navigation()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._update_clock)
        self._clock.start(30_000)
        self._update_clock()
        QTimer.singleShot(1200, self._daily_backup)

    # ------------------------------------------------------------------ UI
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(11)
        logo = QLabel()
        logo.setFixedSize(42, 42)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            "background: #2563eb; border-radius: 11px; color: white;"
            "font-size: 15pt; font-weight: 800;"
        )
        logo.setText("CS")
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("ControlStock")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("GESTION DE INVENTARIO")
        subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addLayout(brand_text, 1)
        layout.addLayout(brand)
        layout.addSpacing(10)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #1e293b;")
        layout.addWidget(line)
        layout.addSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_widget = QWidget()
        nav_widget.setObjectName("NavContainer")
        self.nav_layout = QVBoxLayout(nav_widget)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(2)
        scroll.setWidget(nav_widget)
        layout.addWidget(scroll, 1)

        line2 = QFrame()
        line2.setFixedHeight(1)
        line2.setStyleSheet("background: #1e293b;")
        layout.addWidget(line2)
        layout.addSpacing(6)

        user_box = QFrame()
        user_box.setObjectName("SidebarUserBox")
        user_layout = QHBoxLayout(user_box)
        user_layout.setContentsMargins(10, 8, 8, 8)
        user_layout.setSpacing(9)
        initials = QLabel(self._initials(self.user.full_name or self.user.username))
        initials.setObjectName("UserInitials")
        initials.setFixedSize(36, 36)
        initials.setAlignment(Qt.AlignCenter)
        user_layout.addWidget(initials)
        user_text = QVBoxLayout()
        user_text.setSpacing(0)
        name = QLabel(self.user.full_name or self.user.username)
        name.setObjectName("SidebarUser")
        name.setStyleSheet("color: #e2e8f0; font-weight: 600; font-size: 9pt;")
        role = QLabel("Administrador")
        role.setObjectName("SidebarRole")
        user_text.addWidget(name)
        user_text.addWidget(role)
        user_layout.addLayout(user_text, 1)
        logout = QPushButton()
        logout.setProperty("class", "ghost")
        logout.setIcon(make_icon("logout", "#94a3b8", 17))
        logout.setFixedSize(30, 30)
        logout.setToolTip("Cerrar sesion")
        logout.setCursor(Qt.PointingHandCursor)
        logout.clicked.connect(self._logout)
        user_layout.addWidget(logout)
        layout.addWidget(user_box)
        version = QLabel(f"v{__version__}  |  Datos locales")
        version.setObjectName("BrandSubtitle")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("ContentArea")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(62)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 0, 26, 0)
        header_layout.setSpacing(12)
        self.breadcrumb = QLabel("CONTROLSTOCK / DASHBOARD")
        self.breadcrumb.setStyleSheet(
            "color: #64748b; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px;"
        )
        header_layout.addWidget(self.breadcrumb)
        header_layout.addStretch(1)
        self.pending_chip = QLabel("0 pendientes IClass")
        self.pending_chip.setObjectName("BadgeWarning")
        self.pending_chip.setToolTip("Entregas pendientes de registrar en IClass")
        header_layout.addWidget(self.pending_chip)
        local_chip = QLabel("Base local SQLite")
        local_chip.setObjectName("BadgeSuccess")
        header_layout.addWidget(local_chip)
        self.clock_label = QLabel("")
        self.clock_label.setObjectName("Muted")
        self.clock_label.setStyleSheet("color: #475569; font-weight: 600;")
        header_layout.addWidget(self.clock_label)
        layout.addWidget(header)

        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        layout.addWidget(self.stack, 1)
        return content

    def _build_navigation(self) -> None:
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for group_name, keys in GROUPS:
            label = QLabel(group_name)
            label.setStyleSheet(
                "color: #475569; font-size: 7.5pt; font-weight: 700;"
                "letter-spacing: 1.2px; padding: 10px 8px 3px 8px;"
            )
            self.nav_layout.addWidget(label)
            for key in keys:
                spec = next(item for item in PAGE_SPECS if item[0] == key)
                button = NavButton(spec[1], spec[2])
                button.clicked.connect(lambda checked=False, k=key: self.navigate(k))
                self.group.addButton(button)
                self.buttons[key] = button
                self.nav_layout.addWidget(button)
        self.nav_layout.addStretch(1)
        self.navigate("dashboard", force=True)

    # ------------------------------------------------------------- behavior
    def _create_page(self, key: str) -> BasePage:
        spec = next(item for item in PAGE_SPECS if item[0] == key)
        module = importlib.import_module(spec[3])
        cls = getattr(module, spec[4])
        page = cls()
        page.changed.connect(self._on_data_changed)
        page.navigate_requested.connect(self.navigate)
        self.pages[key] = page
        self.stack.addWidget(page)
        return page

    def navigate(self, key: str, force: bool = False) -> None:
        button = self.buttons.get(key)
        if button is not None:
            button.setChecked(True)
        page = self.pages.get(key)
        if page is None:
            try:
                page = self._create_page(key)
            except Exception as exc:  # pragma: no cover - defensive UI
                logger.exception("No se pudo abrir la pagina %s", key)
                show_warning(self, f"No se pudo abrir la seccion:\n{exc}")
                return
        if not force and self.stack.currentWidget() is page:
            page.activate()
            return
        self.stack.setCurrentWidget(page)
        spec = next(item for item in PAGE_SPECS if item[0] == key)
        self.breadcrumb.setText(f"CONTROLSTOCK / {spec[1].upper()}")
        page.activate()

    def _on_data_changed(self) -> None:
        dashboard = self.pages.get("dashboard")
        if dashboard is not None:
            dashboard.refresh()
        self._refresh_pending_chip()

    def _refresh_pending_chip(self) -> None:
        try:
            with session_scope() as session:
                count = len(pending_deliveries(session))
        except Exception:
            count = 0
        self.pending_chip.setText(f"{count} pendientes IClass")
        self.pending_chip.setObjectName("BadgeWarning" if count else "BadgeSuccess")
        self.pending_chip.style().unpolish(self.pending_chip)
        self.pending_chip.style().polish(self.pending_chip)

    def _update_clock(self) -> None:
        self.clock_label.setText(now().strftime("%d/%m/%Y  %H:%M"))
        self._refresh_pending_chip()

    def _daily_backup(self) -> None:
        try:
            backups.create_daily_backup_if_needed(self.user.id)
        except Exception:
            logger.exception("No se pudo crear la copia automatica diaria")

    def _logout(self) -> None:
        if not confirm(
            self,
            "Cerrar sesion",
            "Se cerrara la sesion actual. Los datos ya guardados permanecen en la base local.",
            "Cerrar sesion",
        ):
            return
        self._logout_in_progress = True
        self.close()

    def closeEvent(self, event):  # noqa: N802
        if self._logout_in_progress:
            self.logged_out.emit()
            event.accept()
            return
        if not self._close_confirmed:
            message = "Desea cerrar ControlStock?"
            try:
                with session_scope() as session:
                    auto_close = get_bool(session, "backup_auto_close", True)
                if auto_close:
                    message += "\n\nSe creara una copia de seguridad automatica al cerrar."
            except Exception:
                auto_close = True
            if not confirm(self, "Cerrar aplicacion", message, "Cerrar aplicacion"):
                event.ignore()
                return
            self._close_confirmed = True
            if auto_close:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    backups.create_automatic_on_close(self.user.id)
                except Exception as exc:
                    logger.exception("No se pudo crear la copia automatica al cerrar")
                    QApplication.restoreOverrideCursor()
                    show_warning(
                        self,
                        f"No se pudo crear la copia automatica de cierre:\n{exc}\n\n"
                        "La aplicacion se cerrara de todos modos.",
                    )
                else:
                    QApplication.restoreOverrideCursor()
            event.accept()
            self.closed.emit()
            return
        event.accept()

    @staticmethod
    def _initials(name: str) -> str:
        parts = [part for part in name.split() if part]
        if not parts:
            return "CS"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()
