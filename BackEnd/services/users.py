"""Read existing accounts and their dataset profiles without modifying SQL data."""

from contextlib import closing

from flask import current_app
from flask_jwt_extended import get_jwt_identity
from werkzeug.exceptions import ServiceUnavailable, Unauthorized
from werkzeug.security import check_password_hash

from config.sqlserver import get_connection


def _profile(cursor, account):
    # There is no foreign key between these tables. Only a unique name match
    # is accepted; auth_users.id must never be treated as Reviews.user_id.
    cursor.execute("SELECT TOP (2) id FROM auth_users WHERE nombre = ?", account.nombre)
    if len(cursor.fetchall()) != 1:
        return None

    cursor.execute(
        """
        SELECT TOP (2) user_id, MIN(username) AS username,
               MAX(stats_mean_score) AS stats_mean_score
        FROM Usuarios
        WHERE username = ? AND user_id IS NOT NULL
        GROUP BY user_id
        """,
        account.nombre,
    )
    profiles = cursor.fetchall()
    if len(profiles) != 1:
        return None

    profile = profiles[0]
    cursor.execute(
        """
        SELECT COUNT_BIG(DISTINCT anime_id) AS review_count
        FROM Reviews
        WHERE user_id = ? AND anime_id IS NOT NULL AND my_score > 0
        """,
        profile.user_id,
    )
    review_count = cursor.fetchone().review_count
    return {
        "userId": int(profile.user_id),
        "username": profile.username,
        "meanScore": float(profile.stats_mean_score) if profile.stats_mean_score is not None else None,
        "reviewCount": int(review_count),
    }


def _user(cursor, account):
    return {
        "id": int(account.id),
        "nombre": account.nombre,
        "email": account.email,
        "fechaCreacion": account.fecha_creacion.isoformat() if account.fecha_creacion else None,
        "profile": _profile(cursor, account),
    }


def authenticate_user(email, password):
    try:
        with closing(get_connection()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                """
                SELECT id, nombre, email, password_hash, fecha_creacion
                FROM auth_users WHERE email = ?
                """,
                email,
            )
            account = cursor.fetchone()
            if account is None:
                return None
            try:
                valid = check_password_hash(account.password_hash, password)
            except (ValueError, TypeError):
                valid = False
            if not valid:
                return None
            return _user(cursor, account)
    except Exception as error:
        current_app.logger.error("No se pudo consultar la cuenta de inicio de sesión")
        raise ServiceUnavailable("No se pudo consultar tu cuenta. Intentá de nuevo.") from error


def get_user(account_id):
    try:
        with closing(get_connection()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                """
                SELECT id, nombre, email, fecha_creacion
                FROM auth_users WHERE id = ?
                """,
                account_id,
            )
            account = cursor.fetchone()
            return _user(cursor, account) if account is not None else None
    except Exception as error:
        current_app.logger.error("No se pudo consultar el usuario de la sesión")
        raise ServiceUnavailable("No se pudo consultar tu cuenta. Intentá de nuevo.") from error


def get_current_user():
    identity = get_jwt_identity()
    if not isinstance(identity, str) or not identity.isascii() or not identity.isdecimal():
        raise Unauthorized("La sesión no es válida. Iniciá sesión nuevamente.")
    if len(identity) > 10 or not 0 < int(identity) <= 2147483647:
        raise Unauthorized("La sesión no es válida. Iniciá sesión nuevamente.")
    user = get_user(int(identity))
    if user is None:
        raise Unauthorized("La cuenta de esta sesión ya no está disponible.")
    return user
