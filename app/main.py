"""Punto de entrada de ControlStock."""
from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME
from app.config import app_data_dir, logs_dir
from app.db.database import init_db
from app.ui.app_controller import ApplicationController
from app.ui.common import AppMessageBox
from app.ui.icons import make_icon
from app.ui.theme import COLORS, apply_theme


def configure_logging() -> None:
    log_file = logs_dir() / "control_stock.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=4, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False) and sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(console)


def install_exception_hook() -> None:
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger(__name__).critical("Error no controlado:\n%s", text)
        try:
            box = AppMessageBox()
            box.setWindowTitle("Error inesperado")
            box.setIcon(QMessageBox.Critical)
            box.setText(
                "Ocurrio un error inesperado. La informacion guardada no se vio afectada.\n\n"
                f"{exc_value}\n\n"
                f"Detalle tecnico registrado en:\n{logs_dir() / 'control_stock.log'}"
            )
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Iniciando %s", APP_NAME)

    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("ControlStock")
    app.setWindowIcon(make_icon("box", COLORS["primary"], 64))
    apply_theme(app)
    install_exception_hook()

    try:
        init_db()
    except Exception as exc:
        logger.exception("No se pudo abrir la base de datos")
        box = AppMessageBox()
        box.setWindowTitle("No se pudo iniciar")
        box.setIcon(QMessageBox.Critical)
        box.setText(
            f"No fue posible abrir la base de datos.\n\n{exc}\n\n"
            f"Carpeta de datos: {app_data_dir()}"
        )
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()
        return 1

    controller = ApplicationController(app)
    app._controller = controller  # type: ignore[attr-defined]
    app.setQuitOnLastWindowClosed(False)
    return app.exec()
