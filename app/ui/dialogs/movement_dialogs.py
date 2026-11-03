"""Detalle de un movimiento de stock."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from app.db.database import session_scope
from app.domain import MOVEMENT_TYPES, STATE_LABELS
from app.services.movements import get_movement
from app.ui.common import Card, make_button, show_error, fmt_datetime, fmt_int, fmt_signed


class MovementDetailDialog(QDialog):
    def __init__(self, movement_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle del movimiento")
        self.setModal(True)
        self.resize(760, 580)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        header = QHBoxLayout()
        self.title_label = QLabel("Movimiento")
        self.title_label.setObjectName("PageTitle")
        self.title_label.setStyleSheet("font-size: 17pt;")
        header.addWidget(self.title_label, 1)
        close = make_button("Cerrar", "secondary")
        close.clicked.connect(self.accept)
        header.addWidget(close)
        root.addLayout(header)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("PageSubtitle")
        root.addWidget(self.subtitle)
        info_card = Card(margins=18, spacing=8)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.RichText)
        info_card.layout.addWidget(self.info_label)
        root.addWidget(info_card, 1)
        self._load(movement_id)

    def _load(self, movement_id: int) -> None:
        try:
            with session_scope() as session:
                movement = get_movement(session, movement_id)
                movement_label = MOVEMENT_TYPES.get(
                    movement.movement_type, movement.movement_type
                )
                self.title_label.setText(movement_label)
                self.subtitle.setText(
                    f"{fmt_datetime(movement.created_at)}  |  Movimiento #{movement.id}"
                )
                parts = [
                    f"<b>Articulo:</b> {movement.item_name_snapshot}",
                    f"<b>Cantidad:</b> {fmt_int(movement.quantity)}",
                    f"<b>Variacion de stock:</b> {fmt_signed(movement.stock_delta)}",
                    f"<b>Stock anterior:</b> {fmt_int(movement.stock_before)}",
                    f"<b>Stock posterior:</b> {fmt_int(movement.stock_after)}",
                ]
                if movement.from_state:
                    parts.append(
                        f"<b>Estado origen:</b> {STATE_LABELS.get(movement.from_state, movement.from_state)}"
                    )
                if movement.to_state:
                    parts.append(
                        f"<b>Estado destino:</b> {STATE_LABELS.get(movement.to_state, movement.to_state)}"
                    )
                if movement.crew:
                    parts.append(f"<b>Cuadrilla:</b> {movement.crew.name}")
                if movement.technician:
                    parts.append(f"<b>Tecnico:</b> {movement.technician}")
                if movement.user:
                    parts.append(f"<b>Usuario:</b> {movement.user.username}")
                if movement.delivery:
                    parts.append(f"<b>Entrega:</b> {movement.delivery.code}")
                if movement.return_record:
                    parts.append(f"<b>Devolucion:</b> {movement.return_record.code}")
                if movement.inventory_count:
                    parts.append(f"<b>Recuento:</b> {movement.inventory_count.code}")
                if movement.observations:
                    parts.append(f"<b>Observaciones:</b> {movement.observations}")
                if movement.is_voided:
                    parts.append(
                        f"<b>Estado:</b> <span style='color:#dc2626;'>Anulado</span>"
                        f" - {fmt_datetime(movement.voided_at)}"
                    )
                    if movement.void_reason:
                        parts.append(f"<b>Motivo de anulacion:</b> {movement.void_reason}")
                else:
                    parts.append("<b>Estado:</b> Vigente")
                self.info_label.setText("<br><br>".join(parts))
        except Exception as exc:
            show_error(self, exc)
