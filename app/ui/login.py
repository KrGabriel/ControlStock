"""Pantalla de inicio de sesion y configuracion inicial del administrador."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.db.database import session_scope
from app.errors import AppError
from app.services import auth
from app.session import set_current_user
from app.ui.common import FormDialog, make_button, show_error, show_info
from app.ui.icons import make_icon
from app.ui.theme import COLORS


class BrandPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LoginBrand")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 40)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(make_icon("box", "#60a5fa", 46).pixmap(46, 46))
        layout.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setObjectName("LoginBrandTitle")
        layout.addWidget(title)
        subtitle = QLabel("Gestion de inventario para telecomunicaciones")
        subtitle.setObjectName("LoginBrandSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(26)
        line = QFrame()
        line.setObjectName("LoginBrandDivider")
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(20)
        for text in (
            "Stock principal y estados por articulo",
            "Entregas y devoluciones por cuadrilla",
            "Recuentos fisicos y ajustes auditables",
            "Informes diarios, semanales y mensuales",
            "Copias de seguridad locales",
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QLabel()
            check.setPixmap(make_icon("check", "#60a5fa", 18).pixmap(18, 18))
            row.addWidget(check, 0, Qt.AlignTop)
            label = QLabel(text)
            label.setObjectName("LoginBenefit")
            row.addWidget(label, 1)
            layout.addLayout(row)
        layout.addStretch(1)
        local = QLabel("Aplicacion 100% local  |  Sin conexion a Internet")
        local.setObjectName("LoginFooter")
        layout.addWidget(local)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("LoginVersion")
        layout.addWidget(version)


class LoginWindow(QWidget):
    logged_in = Signal(object)
    closed = Signal()

    def __init__(self, default_username: str = ""):
        super().__init__()
        self.setObjectName("LoginWindow")
        self.setWindowTitle(f"{APP_NAME} - Iniciar sesion")
        self.setWindowIcon(make_icon("box", COLORS["primary"], 32))
        self.setMinimumSize(960, 620)
        self.resize(1080, 680)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        brand = BrandPanel()
        brand.setMinimumWidth(420)
        brand.setMaximumWidth(520)
        root.addWidget(brand, 5)

        right = QWidget()
        right.setObjectName("LoginRight")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(70, 60, 70, 40)
        right_layout.setAlignment(Qt.AlignCenter)
        card = QFrame()
        card.setObjectName("LoginCard")
        card.setMaximumWidth(430)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 32, 34, 30)
        card_layout.setSpacing(12)

        title = QLabel("Iniciar sesion")
        title.setObjectName("LoginTitle")
        card_layout.addWidget(title)
        subtitle = QLabel("Ingrese sus credenciales de administrador para continuar.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(10)

        user_label = QLabel("Usuario")
        user_label.setObjectName("LoginFieldLabel")
        card_layout.addWidget(user_label)
        self.username = QLineEdit()
        self.username.setPlaceholderText("Nombre de usuario")
        self.username.addAction(make_icon("user", "#64748b", 16), QLineEdit.LeadingPosition)
        self.username.setText(default_username)
        card_layout.addWidget(self.username)

        pass_label = QLabel("Contrasena")
        pass_label.setObjectName("LoginFieldLabel")
        card_layout.addWidget(pass_label)
        self.password = QLineEdit()
        self.password.setPlaceholderText("Contrasena")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.addAction(make_icon("lock", "#64748b", 16), QLineEdit.LeadingPosition)
        card_layout.addWidget(self.password)

        self.show_password = QCheckBox("Mostrar contrasena")
        self.show_password.toggled.connect(
            lambda checked: self.password.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        card_layout.addWidget(self.show_password)

        self.error_label = QLabel("")
        self.error_label.setObjectName("LoginError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        card_layout.addWidget(self.error_label)

        self.enter_button = make_button("Ingresar", "primary")
        self.enter_button.setMinimumHeight(42)
        self.enter_button.setIcon(make_icon("logout", "#ffffff", 17))
        self.enter_button.clicked.connect(self._login)
        card_layout.addWidget(self.enter_button)
        card_layout.addSpacing(4)
        hint = QLabel("La sesion permanece activa mientras la aplicacion este abierta.")
        hint.setObjectName("TinyMuted")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)

        right_layout.addWidget(card)
        footer = QLabel("Los datos se almacenan unicamente en este equipo.")
        footer.setObjectName("TinyMuted")
        footer.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(footer)
        root.addWidget(right, 6)

        self.password.returnPressed.connect(self._login)
        self.username.returnPressed.connect(self._login)

    def showEvent(self, event):
        super().showEvent(event)
        if self.username.text():
            self.password.setFocus()
        else:
            self.username.setFocus()

    def _login(self) -> None:
        self.error_label.hide()
        username = self.username.text().strip()
        password = self.password.text()
        if not username or not password:
            self._show_error("Ingrese usuario y contrasena.")
            return
        try:
            with session_scope() as session:
                user = auth.authenticate(session, username, password)
                session_user = set_current_user(user)
        except AppError as exc:
            self._show_error(str(exc))
            return
        self.logged_in.emit(session_user)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    def closeEvent(self, event):  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)


class AdminSetupDialog(FormDialog):
    def __init__(self, parent=None):
        super().__init__(
            "Configuracion inicial",
            "Cree las credenciales del administrador. Esta es la unica cuenta del sistema "
            "y permitira acceder a todos los modulos.",
            parent,
            width=540,
        )
        self.set_primary_text("Crear administrador")
        self.username = QLineEdit("admin")
        self.username.setPlaceholderText("Usuario")
        self.full_name = QLineEdit()
        self.full_name.setPlaceholderText("Nombre y apellido (opcional)")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Minimo 8 caracteres")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.Password)
        self.confirm.setPlaceholderText("Repita la contrasena")
        self.show_password = QCheckBox("Mostrar contrasenas")
        self.show_password.toggled.connect(self._toggle_password)
        self.form.addRow("Usuario", self.username)
        self.form.addRow("Nombre completo", self.full_name)
        self.form.addRow("Contrasena", self.password)
        self.form.addRow("Confirmar contrasena", self.confirm)
        self.form.addRow("", self.show_password)
        self.set_validator(self._create)

    def _toggle_password(self, checked: bool) -> None:
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self.password.setEchoMode(mode)
        self.confirm.setEchoMode(mode)

    def _create(self) -> None:
        if self.password.text() != self.confirm.text():
            from app.errors import ValidationError

            raise ValidationError("Las contrasenas no coinciden.")
        with session_scope() as session:
            auth.create_admin(
                session,
                self.username.text(),
                self.password.text(),
                self.full_name.text(),
            )
