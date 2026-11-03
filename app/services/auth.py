"""Autenticacion y gestion del administrador."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import User
from app.errors import NotFoundError, ValidationError
from app.services.security import hash_password, verify_password
from app.utils.dates import now


def count_users(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(User)) or 0)


def create_admin(
    session: Session, username: str, password: str, full_name: str = ""
) -> User:
    username = (username or "").strip()
    full_name = (full_name or "").strip()
    if len(username) < 3:
        raise ValidationError("El usuario debe tener al menos 3 caracteres.")
    if len(password or "") < 8:
        raise ValidationError("La contraseña debe tener al menos 8 caracteres.")
    exists = session.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if exists:
        raise ValidationError("Ese usuario ya existe.")
    digest, salt = hash_password(password)
    user = User(
        username=username,
        full_name=full_name,
        password_hash=digest,
        password_salt=salt,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User:
    username = (username or "").strip()
    user = session.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if user is None or not verify_password(password or "", user.password_hash, user.password_salt):
        raise ValidationError("Usuario o contraseña incorrectos.")
    if not user.is_active:
        raise ValidationError("El usuario se encuentra deshabilitado.")
    user.last_login_at = now()
    session.flush()
    return user


def change_password(
    session: Session, user_id: int, current_password: str, new_password: str
) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("El usuario no existe.")
    if not verify_password(current_password or "", user.password_hash, user.password_salt):
        raise ValidationError("La contraseña actual no es correcta.")
    if len(new_password or "") < 8:
        raise ValidationError("La nueva contraseña debe tener al menos 8 caracteres.")
    if current_password == new_password:
        raise ValidationError("La nueva contraseña debe ser diferente de la actual.")
    digest, salt = hash_password(new_password)
    user.password_hash = digest
    user.password_salt = salt
    session.flush()
