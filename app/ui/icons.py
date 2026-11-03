"""Iconografia vectorial dibujada con QPainter (sin archivos externos)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def make_icon(name: str, color: str = "#475569", size: int = 20) -> QIcon:
    scale = max(2, size)
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale((size * 2) / 24.0, (size * 2) / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    _draw(painter, name)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def _line(painter: QPainter, x1, y1, x2, y2) -> None:
    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw(painter: QPainter, name: str) -> None:
    if name == "dashboard":
        for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
            painter.drawRoundedRect(QRectF(x, y, 7, 7), 1.5, 1.5)
    elif name == "inventory":
        painter.drawRoundedRect(QRectF(3, 7, 18, 14), 1.5, 1.5)
        _line(painter, 3, 7, 8, 3)
        _line(painter, 21, 7, 16, 3)
        _line(painter, 8, 3, 16, 3)
        _line(painter, 8, 3, 8, 10)
        _line(painter, 16, 3, 16, 10)
        _line(painter, 8, 10, 16, 10)
    elif name == "delivery":
        painter.drawPath(_tray())
        _line(painter, 12, 16, 12, 4)
        _line(painter, 8, 8, 12, 4)
        _line(painter, 16, 8, 12, 4)
    elif name == "return":
        painter.drawPath(_tray())
        _line(painter, 12, 4, 12, 16)
        _line(painter, 8, 12, 12, 16)
        _line(painter, 16, 12, 12, 16)
    elif name == "crews":
        painter.drawEllipse(QRectF(4, 4, 6, 6))
        painter.drawArc(QRectF(2, 12, 10, 9), 15 * 16, 150 * 16)
        painter.drawEllipse(QRectF(14, 5, 5, 5))
        painter.drawArc(QRectF(12, 12, 10, 9), 15 * 16, 150 * 16)
    elif name == "movements":
        for y in (6, 12, 18):
            painter.drawEllipse(QRectF(3, y - 1.4, 2.8, 2.8))
            _line(painter, 9, y, 21, y)
    elif name == "income":
        painter.drawPath(_tray())
        _line(painter, 12, 4, 12, 15)
        _line(painter, 8, 11, 12, 15)
        _line(painter, 16, 11, 12, 15)
    elif name == "count":
        painter.drawRoundedRect(QRectF(5, 4, 14, 17), 2, 2)
        painter.drawRoundedRect(QRectF(8, 2, 8, 4), 1.5, 1.5)
        _line(painter, 8, 9, 16, 9)
        _line(painter, 8, 13, 12, 13)
        _line(painter, 12, 17, 14, 19)
        _line(painter, 14, 19, 18, 14)
    elif name == "reports":
        _line(painter, 3, 21, 21, 21)
        painter.drawRoundedRect(QRectF(5, 13, 3, 8), 0.8, 0.8)
        painter.drawRoundedRect(QRectF(10.5, 8, 3, 13), 0.8, 0.8)
        painter.drawRoundedRect(QRectF(16, 3, 3, 18), 0.8, 0.8)
    elif name == "iclass":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        _line(painter, 12, 7, 12, 12)
        _line(painter, 12, 12, 16, 14)
    elif name == "settings":
        painter.drawEllipse(QRectF(8, 8, 8, 8))
        import math

        for index in range(8):
            angle = math.radians(index * 45)
            x1 = 12 + 5.2 * math.cos(angle)
            y1 = 12 + 5.2 * math.sin(angle)
            x2 = 12 + 8.2 * math.cos(angle)
            y2 = 12 + 8.2 * math.sin(angle)
            _line(painter, x1, y1, x2, y2)
    elif name == "logout":
        painter.drawRoundedRect(QRectF(4, 4, 9, 16), 1.5, 1.5)
        _line(painter, 11, 12, 21, 12)
        _line(painter, 17, 8, 21, 12)
        _line(painter, 17, 16, 21, 12)
    elif name == "search":
        painter.drawEllipse(QRectF(4, 4, 12, 12))
        _line(painter, 15, 15, 21, 21)
    elif name == "plus":
        _line(painter, 12, 4, 12, 20)
        _line(painter, 4, 12, 20, 12)
    elif name == "minus":
        _line(painter, 4, 12, 20, 12)
    elif name == "edit":
        _line(painter, 4, 20, 8, 19)
        _line(painter, 8, 19, 20, 7)
        _line(painter, 20, 7, 17, 4)
        _line(painter, 17, 4, 5, 16)
        _line(painter, 5, 16, 4, 20)
    elif name == "trash":
        _line(painter, 4, 7, 20, 7)
        _line(painter, 9, 4, 15, 4)
        painter.drawRoundedRect(QRectF(6, 7, 12, 14), 1, 1)
        _line(painter, 10, 10, 10, 18)
        _line(painter, 14, 10, 14, 18)
    elif name == "history":
        painter.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 320 * 16)
        _line(painter, 4, 4, 4, 9)
        _line(painter, 4, 4, 9, 4)
        _line(painter, 12, 8, 12, 12)
        _line(painter, 12, 12, 15, 14)
    elif name == "refresh":
        painter.drawArc(QRectF(4, 4, 16, 16), 30 * 16, 290 * 16)
        _line(painter, 20, 4, 20, 9)
        _line(painter, 20, 4, 15, 4)
    elif name == "backup":
        painter.drawEllipse(QRectF(4, 3, 16, 5))
        _line(painter, 4, 5.5, 4, 18.5)
        _line(painter, 20, 5.5, 20, 18.5)
        painter.drawArc(QRectF(4, 15, 16, 7), 180 * 16, 180 * 16)
        painter.drawArc(QRectF(4, 10, 16, 7), 180 * 16, 180 * 16)
    elif name == "restore":
        _line(painter, 12, 20, 12, 8)
        _line(painter, 8, 12, 12, 8)
        _line(painter, 16, 12, 12, 8)
        _line(painter, 4, 21, 20, 21)
    elif name == "warning":
        painter.drawPolygon(
            [
                QPointF(12, 3),
                QPointF(22, 20),
                QPointF(2, 20),
            ]
        )
        _line(painter, 12, 8, 12, 14)
        painter.drawEllipse(QRectF(11.2, 16.5, 1.6, 1.6))
    elif name == "check":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        _line(painter, 7, 12, 11, 16)
        _line(painter, 11, 16, 18, 8)
    elif name == "close":
        _line(painter, 5, 5, 19, 19)
        _line(painter, 19, 5, 5, 19)
    elif name == "excel":
        painter.drawRoundedRect(QRectF(5, 3, 14, 18), 1.5, 1.5)
        _line(painter, 8, 12, 16, 12)
        _line(painter, 8, 15, 16, 15)
        _line(painter, 12, 7, 12, 18)
    elif name == "filter":
        painter.drawPolygon(
            [
                QPointF(3, 4),
                QPointF(21, 4),
                QPointF(14, 13),
                QPointF(14, 20),
                QPointF(10, 18),
                QPointF(10, 13),
            ]
        )
    elif name == "eye":
        painter.drawEllipse(QRectF(4, 8, 16, 9))
        painter.drawEllipse(QRectF(10, 10, 4, 4))
    elif name == "lock":
        painter.drawRoundedRect(QRectF(5, 10, 14, 11), 2, 2)
        painter.drawArc(QRectF(8, 3, 8, 11), 0, 180 * 16)
    elif name == "user":
        painter.drawEllipse(QRectF(7, 3, 10, 10))
        painter.drawArc(QRectF(3, 13, 18, 12), 10 * 16, 160 * 16)
    elif name == "calendar":
        painter.drawRoundedRect(QRectF(3, 5, 18, 16), 1.5, 1.5)
        _line(painter, 3, 10, 21, 10)
        _line(painter, 8, 3, 8, 7)
        _line(painter, 16, 3, 16, 7)
    elif name == "box":
        painter.drawRoundedRect(QRectF(3, 3, 18, 18), 2, 2)
    else:
        painter.drawEllipse(QRectF(5, 5, 14, 14))


def _tray() -> QPainterPath:
    path = QPainterPath()
    path.moveTo(3, 13)
    path.lineTo(3, 20)
    path.lineTo(21, 20)
    path.lineTo(21, 13)
    return path
