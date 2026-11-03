"""Configuracion, copias de seguridad, categorias y cuenta."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.db.database import current_database_path, session_scope
from app.db.models import Category, Item
from app.domain import BACKUP_KINDS
from app.errors import AppError, ValidationError
from app.services import backups
from app.services.auth import change_password
from app.services.backups import (
    create_backup,
    list_backups,
    restore_backup,
    validate_backup_file,
)
from app.services.inventory import (
    create_category,
    delete_category,
    list_categories,
    update_category,
)
from app.services.settings import (
    get_backup_folder,
    get_bool,
    get_int,
    get_setting,
    set_bool,
    set_setting,
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
from app.ui.dialogs.reference_dialogs import CategoryFormDialog
from app.ui.pages.base import BasePage


def _fmt_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


class SettingsPage(BasePage):
    page_key = "settings"
    title = "Configuracion"
    subtitle = "Copias de seguridad, categorias y cuenta."

    def __init__(self, parent=None):
        super().__init__(parent)
        header = PageHeader(
            "Configuracion",
            "Administre las copias de seguridad, las categorias y las credenciales de acceso.",
        )
        self.root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_backup_tab(), "Copias de seguridad")
        self.tabs.addTab(self._build_categories_tab(), "Categorias")
        self.tabs.addTab(self._build_account_tab(), "Cuenta")
        self.tabs.addTab(self._build_info_tab(), "Acerca de")
        self.root.addWidget(self.tabs, 1)
        self._load_settings()
        self._refresh_backups()
        self._refresh_categories()
        self._refresh_info()

    # ------------------------------------------------------------- backups
    def _build_backup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        config_card = Card(margins=16, spacing=10)
        title = QLabel("Preferencias de copia")
        title.setObjectName("SectionTitle")
        config_card.layout.addWidget(title)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        folder_label = QLabel("Carpeta de copias")
        folder_label.setMinimumWidth(150)
        folder_row.addWidget(folder_label)
        self.folder_edit = QLineEdit()
        folder_row.addWidget(self.folder_edit, 1)
        browse = make_button("Examinar", "secondary", "folder")
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse)
        open_folder = make_button("Abrir carpeta", "secondary")
        open_folder.clicked.connect(self._open_folder)
        folder_row.addWidget(open_folder)
        config_card.layout.addLayout(folder_row)

        options = QHBoxLayout()
        options.setSpacing(18)
        self.auto_close = QCheckBox("Copia automatica al cerrar la aplicacion")
        options.addWidget(self.auto_close)
        self.daily = QCheckBox("Copia automatica diaria")
        options.addWidget(self.daily)
        options.addWidget(QLabel("Conservar"))
        self.retention = QSpinBox()
        self.retention.setRange(1, 365)
        self.retention.setFixedWidth(80)
        options.addWidget(self.retention)
        options.addWidget(QLabel("copias automaticas"))
        options.addStretch(1)
        save = make_button("Guardar preferencias", "primary", "save")
        save.clicked.connect(self._save_settings)
        options.addWidget(save)
        config_card.layout.addLayout(options)
        layout.addWidget(config_card)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        create = make_button("Crear copia ahora", "primary", "backup")
        create.clicked.connect(self._create_backup)
        actions.addWidget(create)
        restore = make_button("Restaurar seleccionada", "secondary", "restore")
        restore.clicked.connect(self._restore_selected)
        actions.addWidget(restore)
        restore_file = make_button("Restaurar desde archivo...", "secondary")
        restore_file.clicked.connect(self._restore_file)
        actions.addWidget(restore_file)
        actions.addStretch(1)
        self.backup_count_label = QLabel("")
        self.backup_count_label.setObjectName("Muted")
        actions.addWidget(self.backup_count_label)
        layout.addLayout(actions)

        table_card = Card(margins=14, spacing=6)
        self.backups_table = QTableWidget()
        setup_table(
            self.backups_table,
            ["Archivo", "Fecha", "Tipo", "TamaÃ±o", "Observaciones"],
            stretch=0,
            column_widths={0: 270, 1: 130, 2: 110, 3: 90},
        )
        self.backups_table.doubleClicked.connect(self._restore_selected)
        table_card.layout.addWidget(self.backups_table)
        layout.addWidget(table_card, 1)
        warning = QLabel(
            "Restaurar una copia reemplaza la base actual. Se crea automaticamente una copia "
            "de seguridad previa. Se recomienda reiniciar la aplicacion despues de restaurar."
        )
        warning.setObjectName("Muted")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        return page

    def _load_settings(self) -> None:
        try:
            with session_scope() as session:
                self.folder_edit.setText(get_backup_folder(session))
                self.auto_close.setChecked(get_bool(session, "backup_auto_close", True))
                self.daily.setChecked(get_bool(session, "backup_daily", True))
                self.retention.setValue(get_int(session, "backup_retention", 15))
        except Exception as exc:
            show_error(self, exc)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de copias", self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    def _open_folder(self) -> None:
        try:
            backups.open_folder(self.folder_edit.text().strip())
        except Exception as exc:
            show_error(self, exc)

    def _save_settings(self) -> None:
        folder = self.folder_edit.text().strip()
        try:
            if folder:
                Path(folder).mkdir(parents=True, exist_ok=True)
            with session_scope() as session:
                set_setting(session, "backup_folder", folder)
                set_bool(session, "backup_auto_close", self.auto_close.isChecked())
                set_bool(session, "backup_daily", self.daily.isChecked())
                set_setting(session, "backup_retention", str(self.retention.value()))
        except Exception as exc:
            show_error(self, exc)
            return
        show_info(self, "Las preferencias de copia fueron guardadas.")

    def _refresh_backups(self) -> None:
        try:
            with session_scope() as session:
                rows = [
                    {
                        "path": backup.path,
                        "filename": backup.filename,
                        "created_at": backup.created_at,
                        "kind": backup.kind,
                        "size": backup.size_bytes,
                        "notes": backup.notes,
                    }
                    for backup in list_backups(session)
                ]
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.backups_table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            set_row(
                table,
                row,
                [
                    make_item(data["filename"], data=data["path"], bold=True),
                    make_item(fmt_datetime(data["created_at"])),
                    make_item(BACKUP_KINDS.get(data["kind"], data["kind"])),
                    make_item(_fmt_size(data["size"]), sort_value=data["size"], align=Qt.AlignRight | Qt.AlignVCenter),
                    make_item(data["notes"], tooltip=data["notes"]),
                ],
            )
        finish_table(table, sortable=False)
        self.backup_count_label.setText(f"{len(rows)} copia(s) registrada(s)")

    def _selected_backup_path(self) -> str | None:
        rows = self.backups_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.backups_table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole + 1) if item else None

    def _create_backup(self) -> None:
        try:
            with session_scope() as session:
                backup = create_backup(
                    session,
                    user_id=get_current_user().id,
                    notes="Copia manual creada desde configuracion",
                )
                path = backup.path
        except AppError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc)
            return
        self._refresh_backups()
        show_info(self, f"La copia de seguridad fue creada en:\n{path}")

    def _restore_selected(self, _index=None) -> None:
        path = self._selected_backup_path()
        if not path:
            show_warning(self, "Seleccione una copia de seguridad de la tabla.")
            return
        self._restore(path)

    def _restore_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar copia de seguridad", self.folder_edit.text(), "Base SQLite (*.db)"
        )
        if path:
            self._restore(path)

    def _restore(self, path: str) -> None:
        try:
            info = validate_backup_file(path)
        except AppError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc)
            return
        if not confirm(
            self,
            "Restaurar copia de seguridad",
            f"Se reemplazara la base de datos actual por:\n{Path(path).name}\n\n"
            f"Usuarios: {info['users']}  |  Articulos: {info['items']}\n\n"
            "Se creara una copia previa automaticamente. Despues de restaurar, reinicie la aplicacion.",
            "Restaurar",
            danger=True,
        ):
            return
        try:
            restore_backup(path, get_current_user().id)
        except AppError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc)
            return
        self._refresh_backups()
        self._refresh_info()
        self._refresh_categories()
        self.mark_changed()
        show_info(
            self,
            "La copia fue restaurada correctamente.\n\nReinicie la aplicacion para "
            "asegurar que todas las pantallas usen los datos restaurados.",
            "Restauracion completada",
        )

    # ---------------------------------------------------------- categories
    def _build_categories_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        add = make_button("Nueva categoria", "primary", "plus")
        add.clicked.connect(self._new_category)
        actions.addWidget(add)
        edit = make_button("Editar", "secondary", "edit")
        edit.clicked.connect(self._edit_category)
        actions.addWidget(edit)
        delete = make_button("Eliminar", "secondary", "trash")
        delete.clicked.connect(self._delete_category)
        actions.addWidget(delete)
        actions.addStretch(1)
        self.category_count_label = QLabel("")
        self.category_count_label.setObjectName("Muted")
        actions.addWidget(self.category_count_label)
        layout.addLayout(actions)
        table_card = Card(margins=14, spacing=6)
        self.category_table = QTableWidget()
        setup_table(
            self.category_table,
            ["Categoria", "Descripcion", "Articulos"],
            stretch=1,
            column_widths={2: 100},
        )
        self.category_table.doubleClicked.connect(self._edit_category)
        table_card.layout.addWidget(self.category_table)
        layout.addWidget(table_card, 1)
        info = QLabel(
            "Una categoria con articulos asociados no puede eliminarse, para conservar el historial."
        )
        info.setObjectName("Muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        return page

    def _refresh_categories(self) -> None:
        try:
            with session_scope() as session:
                rows = []
                for category in list_categories(session):
                    item_count = int(
                        session.scalar(
                            select(func.count())
                            .select_from(Item)
                            .where(Item.category_id == category.id)
                        )
                        or 0
                    )
                    rows.append(
                        {
                            "id": category.id,
                            "name": category.name,
                            "description": category.description,
                            "items": item_count,
                        }
                    )
        except Exception as exc:
            show_error(self, exc)
            return
        table = self.category_table
        clear_table(table)
        table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            set_row(
                table,
                row,
                [
                    make_item(data["name"], data=data["id"], bold=True),
                    make_item(data["description"], tooltip=data["description"]),
                    make_item(fmt_int(data["items"]), sort_value=data["items"], align=Qt.AlignRight | Qt.AlignVCenter),
                ],
            )
        finish_table(table, sortable=False)
        self.category_count_label.setText(f"{len(rows)} categoria(s)")

    def _new_category(self) -> None:
        dialog = CategoryFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                create_category(session, **dialog.values())
        except AppError as exc:
            show_error(self, exc)
            return
        self._refresh_categories()
        self.mark_changed()
        show_info(self, "La categoria fue creada correctamente.")

    def _edit_category(self, _index=None) -> None:
        category_id = selected_id(self.category_table)
        if category_id is None:
            show_warning(self, "Seleccione una categoria.")
            return
        try:
            with session_scope() as session:
                category = session.get(Category, category_id)
                if category is None:
                    show_warning(self, "La categoria no existe.")
                    return
                values = {"name": category.name, "description": category.description}
        except Exception as exc:
            show_error(self, exc)
            return

        class _Snapshot:
            pass

        snapshot = _Snapshot()
        snapshot.name = values["name"]
        snapshot.description = values["description"]
        dialog = CategoryFormDialog(snapshot, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_values = dialog.values()
        try:
            with session_scope() as session:
                update_category(
                    session,
                    category_id,
                    name=new_values["name"],
                    description=new_values["description"],
                )
        except AppError as exc:
            show_error(self, exc)
            return
        self._refresh_categories()
        self.mark_changed()
        show_info(self, "La categoria fue actualizada.")

    def _delete_category(self) -> None:
        category_id = selected_id(self.category_table)
        if category_id is None:
            show_warning(self, "Seleccione una categoria.")
            return
        try:
            with session_scope() as session:
                category = session.get(Category, category_id)
                if category is None:
                    show_warning(self, "La categoria no existe.")
                    return
                name = category.name
        except Exception as exc:
            show_error(self, exc)
            return
        if not confirm(
            self,
            "Eliminar categoria",
            f"Se intentara eliminar la categoria '{name}'. "
            "Solo es posible si no tiene articulos asociados.",
            "Eliminar",
            danger=True,
        ):
            return
        try:
            with session_scope() as session:
                delete_category(session, category_id)
        except AppError as exc:
            show_error(self, exc)
            return
        self._refresh_categories()
        self.mark_changed()
        show_info(self, "La categoria fue eliminada.")

    # -------------------------------------------------------------- account
    def _build_account_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        user = get_current_user()
        account_card = Card(margins=18, spacing=8)
        title = QLabel("Cuenta de administrador")
        title.setObjectName("SectionTitle")
        account_card.layout.addWidget(title)
        user_label = QLabel(f"Usuario: {user.username}    |    Nombre: {user.full_name}")
        user_label.setObjectName("Muted")
        account_card.layout.addWidget(user_label)
        layout.addWidget(account_card)

        password_card = Card(margins=18, spacing=10)
        password_title = QLabel("Cambiar contraseÃ±a")
        password_title.setObjectName("SectionTitle")
        password_card.layout.addWidget(password_title)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.current_password = QLineEdit()
        self.current_password.setEchoMode(QLineEdit.Password)
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.Password)
        form.addRow("ContraseÃ±a actual *", self.current_password)
        form.addRow("Nueva contraseÃ±a *", self.new_password)
        form.addRow("Confirmar nueva contraseÃ±a *", self.confirm_password)
        password_card.layout.addLayout(form)
        helper = QLabel("La nueva contraseÃ±a debe tener al menos 8 caracteres.")
        helper.setObjectName("Muted")
        password_card.layout.addWidget(helper)
        change = make_button("Cambiar contraseÃ±a", "primary", "login")
        change.clicked.connect(self._change_password)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(change)
        password_card.layout.addLayout(row)
        layout.addWidget(password_card)
        layout.addStretch(1)
        return page

    def _change_password(self) -> None:
        if not self.current_password.text():
            show_warning(self, "Ingrese la contraseÃ±a actual.")
            return
        if self.new_password.text() != self.confirm_password.text():
            show_warning(self, "La nueva contraseÃ±a y su confirmacion no coinciden.")
            return
        try:
            with session_scope() as session:
                change_password(
                    session,
                    get_current_user().id,
                    self.current_password.text(),
                    self.new_password.text(),
                )
        except AppError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc)
            return
        self.current_password.clear()
        self.new_password.clear()
        self.confirm_password.clear()
        show_info(self, "La contraseÃ±a fue actualizada correctamente.")

    # ----------------------------------------------------------------- info
    def _build_info_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        card = Card(margins=18, spacing=8)
        title = QLabel(APP_NAME)
        title.setObjectName("PageTitle")
        title.setStyleSheet("font-size: 16pt;")
        card.layout.addWidget(title)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.RichText)
        card.layout.addWidget(self.info_label)
        layout.addWidget(card)
        description = Card(margins=18, spacing=6)
        desc_title = QLabel("Acerca de esta aplicacion")
        desc_title.setObjectName("SectionTitle")
        description.layout.addWidget(desc_title)
        desc = QLabel(
            "ControlStock es una aplicacion local para la gestion de inventario de una empresa "
            "de telecomunicaciones. Los datos se almacenan exclusivamente en este equipo y no "
            "se envian a ningun servidor externo.\n\n"
            "La aplicacion permite administrar articulos reutilizables y consumibles, entregas "
            "a cuadrillas, devoluciones, recuentos fisicos, seguimiento IClass, informes en Excel "
            "y copias de seguridad."
        )
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        description.layout.addWidget(desc)
        layout.addWidget(description)
        layout.addStretch(1)
        return page

    def _refresh_info(self) -> None:
        try:
            db_path = Path(current_database_path())
            size = db_path.stat().st_size if db_path.exists() else 0
            with session_scope() as session:
                folder = get_backup_folder(session)
                last_auto = get_setting(session, "last_auto_backup", "")
                last_restore = get_setting(session, "last_restore", "")
                categories = len(list_categories(session))
                items = int(
                    session.scalar(select(func.count()).select_from(Item)) or 0
                )
            parts = [
                f"<b>Version:</b> {__version__}",
                f"<b>Base de datos:</b> {db_path}",
                f"<b>TamaÃ±o de la base:</b> {_fmt_size(size)}",
                f"<b>Carpeta de copias:</b> {folder}",
                f"<b>Articulos registrados:</b> {fmt_int(items)}",
                f"<b>Categorias:</b> {fmt_int(categories)}",
                f"<b>Ultima copia automatica:</b> {last_auto or 'Sin registros'}",
                f"<b>Ultima restauracion:</b> {last_restore or 'Sin registros'}",
            ]
            self.info_label.setText("<br>".join(parts))
        except Exception as exc:
            show_error(self, exc)

    # ------------------------------------------------------------ lifecycle
    def activate(self) -> None:
        self._load_settings()
        self._refresh_backups()
        self._refresh_categories()
        self._refresh_info()
