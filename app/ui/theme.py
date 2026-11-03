"""Tema visual unificado de la aplicacion."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#f1f5f9",
    "surface": "#ffffff",
    "surface_alt": "#f8fafc",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
    "primary": "#2563eb",
    "primary_dark": "#1d4ed8",
    "primary_soft": "#eff6ff",
    "success": "#16a34a",
    "success_soft": "#dcfce7",
    "warning": "#d97706",
    "warning_soft": "#fef3c7",
    "danger": "#dc2626",
    "danger_soft": "#fee2e2",
    "purple": "#7c3aed",
    "purple_soft": "#f3e8ff",
    "teal": "#0d9488",
    "teal_soft": "#ccfbf1",
    "sidebar": "#0f172a",
    "sidebar_hover": "#1e293b",
    "sidebar_text": "#94a3b8",
    "sidebar_active": "#2563eb",
    "text_on_dark": "#f8fafc",
    "sidebar_muted": "#94a3b8",
}

STYLESHEET = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
    outline: none;
}
QWidget {
    color: #0f172a;
}
QLabel {
    background: transparent;
}
QMainWindow, QWidget#AppRoot, QWidget#ContentArea, QWidget#LoginWindow, QWidget#LoginRight {
    background: #f1f5f9;
}
QWidget#NavContainer, QWidget#DashboardContent, QWidget#ReportContent,
QStackedWidget#PageStack {
    background: transparent;
}
QDialog {
    background: #f8fafc;
    color: #0f172a;
}
QDialog QLabel {
    background: transparent;
    color: #0f172a;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QFrame#Card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QFrame#Sidebar {
    background: #0f172a;
    border: none;
}
QFrame#HeaderBar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}
QLabel#BrandTitle {
    color: #f8fafc;
    font-size: 15pt;
    font-weight: 700;
}
QLabel#BrandSubtitle {
    color: #94a3b8;
    font-size: 8pt;
    letter-spacing: 1px;
}
QFrame#LoginBrand {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f172a, stop:1 #172554);
    border: none;
    border-radius: 0px;
}
QFrame#LoginBrandDivider {
    background: #1e3a8a;
    border: none;
}
QLabel#LoginBrandTitle {
    color: #f8fafc;
    font-size: 28pt;
    font-weight: 800;
}
QLabel#LoginBrandSubtitle {
    color: #93c5fd;
    font-size: 11.5pt;
}
QLabel#LoginBenefit {
    color: #cbd5e1;
    font-size: 10pt;
}
QLabel#LoginFooter {
    color: #94a3b8;
    font-size: 8.5pt;
}
QLabel#LoginVersion {
    color: #94a3b8;
    font-size: 8pt;
}
QFrame#LoginCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}
QLabel#LoginTitle {
    color: #0f172a;
    font-size: 20pt;
    font-weight: 700;
}
QLabel#LoginFieldLabel {
    color: #334155;
    font-size: 9.5pt;
    font-weight: 600;
}
QLabel#LoginError {
    color: #991b1b;
    background: #fee2e2;
    border: 1px solid #fecaca;
    border-radius: 6px;
    padding: 8px;
}
QFrame#SidebarUserBox {
    background: #1e293b;
    border-radius: 10px;
}
QLabel#PageTitle {
    font-size: 20pt;
    font-weight: 700;
    color: #0f172a;
}
QLabel#PageSubtitle {
    color: #64748b;
    font-size: 9.5pt;
}
QLabel#SectionTitle {
    font-size: 12pt;
    font-weight: 700;
    color: #0f172a;
}
QLabel#Muted {
    color: #64748b;
}
QLabel#TinyMuted {
    color: #94a3b8;
    font-size: 8.5pt;
}
QLabel#StatTitle {
    color: #64748b;
    font-size: 8.5pt;
    font-weight: 600;
}
QLabel#StatValue {
    color: #0f172a;
    font-size: 22pt;
    font-weight: 700;
}
QLabel#StatHint {
    color: #94a3b8;
    font-size: 8pt;
}
QLabel#UserInitials {
    background: #2563eb;
    color: #ffffff;
    border-radius: 18px;
    font-weight: 700;
    font-size: 12pt;
}
QLabel#SidebarUser {
    color: #e2e8f0;
    font-weight: 600;
}
QLabel#SidebarRole {
    color: #94a3b8;
    font-size: 8pt;
}
QLabel#BadgeInfo {
    background: #e0eaff;
    color: #1d4ed8;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#BadgeWarning {
    background: #fef3c7;
    color: #92400e;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#BadgeSuccess {
    background: #dcfce7;
    color: #166534;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#BadgeDanger {
    background: #fee2e2;
    color: #991b1b;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#EmptyTitle {
    color: #475569;
    font-weight: 600;
}
QLabel#EmptyText {
    color: #94a3b8;
    font-size: 9pt;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 7px 14px;
    color: #0f172a;
    font-weight: 600;
}
QPushButton:hover {
    background: #f8fafc;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background: #e2e8f0;
}
QPushButton:disabled {
    color: #94a3b8;
    background: #f1f5f9;
    border-color: #e2e8f0;
}
QPushButton[class="primary"] {
    background: #2563eb;
    color: #ffffff;
    border: 1px solid #2563eb;
}
QPushButton[class="primary"]:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}
QPushButton[class="primary"]:pressed {
    background: #1e40af;
}
QPushButton[class="success"] {
    background: #16a34a;
    color: #ffffff;
    border: 1px solid #16a34a;
}
QPushButton[class="success"]:hover {
    background: #15803d;
}
QPushButton[class="danger"] {
    background: #dc2626;
    color: #ffffff;
    border: 1px solid #dc2626;
}
QPushButton[class="danger"]:hover {
    background: #b91c1c;
}
QPushButton[class="ghost"] {
    background: transparent;
    border: 1px solid transparent;
    color: #475569;
}
QPushButton[class="ghost"]:hover {
    background: #e2e8f0;
    color: #0f172a;
}
QPushButton[class="nav"] {
    background: transparent;
    border: none;
    border-radius: 9px;
    color: #94a3b8;
    text-align: left;
    padding: 10px 12px;
    font-size: 9.5pt;
    font-weight: 600;
}
QPushButton[class="nav"]:hover {
    background: #1e293b;
    color: #e2e8f0;
}
QPushButton[class="nav"]:checked {
    background: #2563eb;
    color: #ffffff;
}
QPushButton[class="icon"] {
    padding: 6px;
    border-radius: 7px;
}
QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: #bfdbfe;
    selection-color: #0f172a;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #2563eb;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateTimeEdit:disabled {
    background: #f1f5f9;
    color: #94a3b8;
}
QLineEdit[search="true"] {
    padding-left: 30px;
}
QLineEdit#PhysicalQtyEditor {
    min-height: 26px;
    padding: 1px 30px 1px 12px;
    background: #eff6ff;
    border: 1px solid #93c5fd;
    border-radius: 7px;
    font-size: 9pt;
    font-weight: 600;
}
QLineEdit#PhysicalQtyEditor:focus {
    background: #ffffff;
    border: 1px solid #2563eb;
}
QLineEdit#PhysicalQtyEditor:disabled {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
    width: 0;
    height: 0;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    selection-background-color: #eff6ff;
    selection-color: #1d4ed8;
    padding: 4px;
}
QTableWidget, QTableView {
    background: #ffffff;
    border: none;
    border-radius: 8px;
    gridline-color: #f1f5f9;
    selection-background-color: #eff6ff;
    selection-color: #0f172a;
    alternate-background-color: #f8fafc;
}
QTableWidget::item, QTableView::item {
    padding: 7px 8px;
    border-bottom: 1px solid #f1f5f9;
}
QTableWidget::item:selected, QTableView::item:selected {
    background: #dbeafe;
    color: #0f172a;
}
QHeaderView::section {
    background: #f8fafc;
    color: #475569;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    padding: 8px;
    font-weight: 700;
    font-size: 8.5pt;
}
QTableCornerButton::section {
    background: #f8fafc;
    border: none;
}
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #64748b;
    padding: 9px 18px;
    margin-right: 4px;
    border-radius: 8px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1d4ed8;
    border: 1px solid #e2e8f0;
}
QTabBar::tab:hover:!selected {
    background: #e2e8f0;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QCheckBox, QRadioButton {
    spacing: 8px;
    color: #0f172a;
    background: transparent;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #94a3b8;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: #2563eb;
    border: 1px solid #2563eb;
}
QProgressBar {
    background: #e2e8f0;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #2563eb;
    border-radius: 4px;
}
QToolTip {
    background: #0f172a;
    color: #ffffff;
    border: none;
    padding: 5px 8px;
}
QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: #eff6ff;
    color: #1d4ed8;
}
QSplitter::handle {
    background: #e2e8f0;
}
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #475569;
}
QCalendarWidget QWidget {
    alternate-background-color: #ffffff;
}
QCalendarWidget QAbstractItemView:enabled {
    background: #ffffff;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
"""

MESSAGE_BOX_STYLE = """
QMessageBox {
    background: #ffffff;
    color: #0f172a;
}
QMessageBox QLabel {
    background: transparent;
    color: #0f172a;
}
QMessageBox QLabel#qt_msgbox_label {
    font-size: 10pt;
}
QMessageBox QLabel#qt_msgbox_informativelabel {
    color: #475569;
}
QMessageBox QTextEdit {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #e2e8f0;
}
QMessageBox QDialogButtonBox {
    background: transparent;
}
QMessageBox QPushButton {
    min-width: 90px;
    min-height: 30px;
}
"""

STYLESHEET += MESSAGE_BOX_STYLE


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["surface_alt"]))
    palette.setColor(QPalette.ToolTipBase, QColor(COLORS["sidebar"]))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text_on_dark"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, QColor(COLORS["primary"]))
    palette.setColor(QPalette.Highlight, QColor("#bfdbfe"))
    palette.setColor(QPalette.HighlightedText, QColor(COLORS["text"]))
    palette.setColor(QPalette.PlaceholderText, QColor(COLORS["muted"]))
    palette.setColor(QPalette.Light, QColor("#ffffff"))
    palette.setColor(QPalette.Midlight, QColor("#f1f5f9"))
    palette.setColor(QPalette.Mid, QColor("#cbd5e1"))
    palette.setColor(QPalette.Dark, QColor("#94a3b8"))
    palette.setColor(QPalette.Shadow, QColor("#64748b"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#94a3b8"))
    palette.setColor(QPalette.Disabled, QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor(COLORS["bg"]))
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor("#f1f5f9"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
