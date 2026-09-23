from flask import Blueprint, jsonify, request

from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from config.sqlserver import get_connection


auth_bp = Blueprint(
    "auth",
    __name__
)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    nombre = str(data.get("nombre", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not nombre or not email or not password:
        return jsonify({
            "error": "nombre, email y password son obligatorios"
        }), 400

    if len(password) < 8:
        return jsonify({
            "error": "La contraseña debe tener al menos 8 caracteres"
        }), 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT id
            FROM auth_users
            WHERE email = ?
            """,
            email
        )

        if cursor.fetchone():
            return jsonify({
                "error": "El correo ya está registrado"
            }), 409

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO auth_users (
                nombre,
                email,
                password_hash
            )
            OUTPUT INSERTED.id
            VALUES (?, ?, ?)
            """,
            nombre,
            email,
            password_hash
        )

        user_id = cursor.fetchone()[0]

        connection.commit()

        return jsonify({
            "message": "Usuario registrado correctamente",
            "user": {
                "id": user_id,
                "nombre": nombre,
                "email": email
            }
        }), 201

    except Exception as error:
        connection.rollback()

        print(f"Error register: {error}")

        return jsonify({
            "error": "No se pudo registrar el usuario"
        }), 500

    finally:
        cursor.close()
        connection.close()


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({
            "error": "email y password son obligatorios"
        }), 400

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                nombre,
                email,
                password_hash
            FROM auth_users
            WHERE email = ?
            """,
            email
        )

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "error": "Correo o contraseña incorrectos"
            }), 401

        if not check_password_hash(
            user.password_hash,
            password
        ):
            return jsonify({
                "error": "Correo o contraseña incorrectos"
            }), 401

        token = create_access_token(
            identity=str(user.id)
        )

        return jsonify({
            "message": "Login correcto",
            "accessToken": token,
            "user": {
                "id": user.id,
                "nombre": user.nombre,
                "email": user.email
            }
        }), 200

    finally:
        cursor.close()
        connection.close()


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id,
                nombre,
                email,
                fecha_creacion
            FROM auth_users
            WHERE id = ?
            """,
            user_id
        )

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "error": "Usuario no encontrado"
            }), 404

        return jsonify({
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "fechaCreacion": (
                user.fecha_creacion.isoformat()
                if user.fecha_creacion
                else None
            )
        }), 200

    finally:
        cursor.close