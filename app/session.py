"""Sesion del usuario autenticado en memoria."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionUser:
    id: int
    username: str
    full_name: str


_current_user: SessionUser | None = None


def set_current_user(user) -> SessionUser:
    global _current_user
    _current_user = SessionUser(
        id=user.id,
        username=user.username,
        full_name=getattr(user, "full_name", "") or user.username,
    )
    return _current_user


def get_current_user() -> SessionUser:
    if _current_user is None:
        raise RuntimeError("No hay una sesion activa.")
    return _current_user


def current_user_or_none() -> SessionUser | None:
    return _current_user


def clear_current_user() -> None:
    global _current_user
    _current_user = None
