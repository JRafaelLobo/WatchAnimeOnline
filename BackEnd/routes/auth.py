import re

import pyodbc
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config.sqlserver import get_connection


auth_bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def _read_credentials(registering=False):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, "Envía los datos del formulario en formato JSON"

    fields = ("nombre", "email", "password") if registering else ("email", "password")
    if any(not isinstance(data.get(field), str) for field in fields):
        return None, "Completa todos los campos con valores de texto"

    values = {field: data[field] for field in fields}
    values["email"] = values["email"].strip().lower()
    if not values["email"] or not values["password"]:
        return None, "El correo y la contraseña son obligatorios"
    if len(values["email"]) > 255 or not EMAIL_PATTERN.fullmatch(values["email"]):
        return None, "Ingresa un correo válido de hasta 255 caracteres"

    if registering:
        values["nombre"] = values["nombre"].strip()
        if not 1 <= len(values["nombre"]) <= 100:
            return None, "El nombre debe tener entre 1 y 100 caracteres"
        if not 8 <= len(values["password"]) <= 128:
            return None, "La contraseña debe tener entre 8 y 128 caracteres"
    elif len(values["password"]) > 1024:
        # Existing accounts may predate the registration length limit.
        return None, "La contraseña es demasiado larga"
    return values, None


def _close_resources(cursor, connection):
    for resource in (cursor, connection):
        if resource is not None:
            try:
                resource.close()
            except Exception:
                current_app.logger.exception("No se pudo cerrar un recurso SQL")


def _rollback(connection):
    if connection is not None:
        try:
            connection.rollback()
        except Exception:
            current_app.logger.exception("No se pudo revertir la transacción SQL")


def _session_response(user, message, status=200):
    token = create_access_token(identity=str(user["id"]))
    response = jsonify({
        "message": message,
        "accessToken": token,
        "expiresAt": decode_token(token)["exp"],
        "user": user,
    })
    set_access_cookies(response, token)
    return response, status


@auth_bp.after_request
def prevent_auth_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.post("/register")
def register():
    data, error = _read_credentials(registering=True)
    if error:
        return jsonify({"error": error}), 400

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM auth_users WHERE email = ?", data["email"])
        if cursor.fetchone():
            return jsonify({"error": "El correo ya está registrado"}), 409

        password_hash = generate_password_hash(data["password"])
        cursor.execute(
            """
            INSERT INTO auth_users (nombre, email, password_hash)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?)
            """,
            data["nombre"], data["email"], password_hash,
        )
        user_id = cursor.fetchone()[0]
        connection.commit()
    except Exception as error:
        _rollback(connection)
        # The UNIQUE constraint also handles simultaneous registrations.
        if isinstance(error, pyodbc.IntegrityError) and any(
            code in str(error) for code in ("2601", "2627")
        ):
            return jsonify({"error": "El correo ya está registrado"}), 409
        current_app.logger.exception("Error al registrar el usuario")
        return jsonify({"error": "No se pudo conectar con la base de datos. Intenta de nuevo"}), 503
    finally:
        _close_resources(cursor, connection)

    return _session_response(
        {"id": user_id, "nombre": data["nombre"], "email": data["email"]},
        "Usuario registrado correctamente", 201,
    )


@auth_bp.post("/login")
def login():
    data, error = _read_credentials()
    if error:
        return jsonify({"error": error}), 400

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, nombre, email, password_hash FROM auth_users WHERE email = ?",
            data["email"],
        )
        user = cursor.fetchone()
    except Exception:
        current_app.logger.exception("Error al consultar las credenciales")
        return jsonify({"error": "No se pudo conectar con la base de datos. Intenta de nuevo"}), 503
    finally:
        _close_resources(cursor, connection)

    if not user or not check_password_hash(user.password_hash, data["password"]):
        return jsonify({"error": "Correo o contraseña incorrectos"}), 401

    return _session_response(
        {"id": user.id, "nombre": user.nombre, "email": user.email},
        "Sesión iniciada correctamente",
    )


@auth_bp.post("/logout")
def logout():
    # Clearing the browser session must also work after its JWT expires.
    response = jsonify({"message": "Sesión cerrada correctamente"})
    unset_jwt_cookies(response)
    return response, 200


@auth_bp.get("/me")
@jwt_required()
def me():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return jsonify({"error": "La sesión no es válida. Inicia sesión de nuevo"}), 401

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, nombre, email, fecha_creacion FROM auth_users WHERE id = ?",
            user_id,
        )
        user = cursor.fetchone()
        if not user:
            response = jsonify({"error": "Tu cuenta ya no está disponible. Inicia sesión de nuevo"})
            unset_jwt_cookies(response)
            return response, 401

        return jsonify({
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "fechaCreacion": user.fecha_creacion.isoformat() if user.fecha_creacion else None,
            "expiresAt": get_jwt()["exp"],
        }), 200
    except Exception:
        current_app.logger.exception("Error al consultar el usuario")
        return jsonify({"error": "No se pudo conectar con la base de datos. Intenta de nuevo"}), 503
    finally:
        _close_resources(cursor, connection)
