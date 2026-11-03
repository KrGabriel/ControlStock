"""Errores de negocio con mensajes aptos para mostrar al usuario."""
from __future__ import annotations


class AppError(Exception):
    """Error controlado de la aplicacion."""


class ValidationError(AppError):
    """Datos invalidos o regla de negocio incumplida."""


class NotFoundError(AppError):
    """Entidad inexistente."""


class ConflictError(AppError):
    """Operacion no permitida por el estado actual de los datos."""
