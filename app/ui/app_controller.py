"""Coordinacion entre inicio de sesion, ventana principal y cierre."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QDialog

from app.db.database import session_scope
from app.services import auth
from app.session import clear_current_user
from app.ui.common import show_info
from app.ui.login import AdminSetupDialog, LoginWindow
from app.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class ApplicationController(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.login: LoginWindow | None = None
        self.main: MainWindow | None = None
        self._switching = False
        self.show_login()

    def show_login(self) -> None:
        with session_scope() as session:
            user_count = auth.count_users(session)
        if user_count == 0:
            setup = AdminSetupDialog()
            if setup.exec() != QDialog.DialogCode.Accepted:
                self.app.quit()
                return
            show_info(
                None,
                "Administrador creado correctamente. Ahora puede iniciar sesion.",
                "Configuracion completada",
            )
        default_username = ""
        with session_scope() as session:
            from sqlalchemy import select

            from app.db.models import User

            first = session.scalar(select(User).order_by(User.id).limit(1))
            if first:
                default_username = first.username
        self.login = LoginWindow(default_username)
        self.login.logged_in.connect(self._on_login)
        self.login.closed.connect(self._on_login_closed)
        self.login.show()
        self.login.raise_()
        self.login.activateWindow()

    def _on_login(self, user) -> None:
        self._switching = True
        if self.login is not None:
            self.login.hide()
            self.login.deleteLater()
            self.login = None
        self.main = MainWindow(user)
        self.main.logged_out.connect(self._on_logout)
        self.main.closed.connect(self.app.quit)
        self.main.showMaximized()
        self.main.raise_()
        self.main.activateWindow()
        self._switching = False

    def _on_login_closed(self) -> None:
        if not self._switching:
            self.app.quit()

    def _on_logout(self) -> None:
        if self.main is not None:
            self.main.deleteLater()
            self.main = None
        clear_current_user()
        self.show_login()
