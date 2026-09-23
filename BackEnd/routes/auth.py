from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required

from services.users import authenticate_user, get_current_user


auth_bp = Blueprint("auth", __name__)


@auth_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Enviá email y password en un objeto JSON"}), 400

    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "email y password son obligatorios"}), 400
    email = email.strip().lower()
    if not email or not password or len(email) > 255:
        return jsonify({"error": "email y password son obligatorios"}), 400

    user = authenticate_user(email, password)
    if user is None:
        return jsonify({"error": "Correo o contraseña incorrectos"}), 401

    return jsonify({
        "message": "Login correcto",
        "accessToken": create_access_token(identity=str(user["id"])),
        "user": user,
    }), 200


@auth_bp.get("/me")
@jwt_required()
def me():
    return jsonify(get_current_user()), 200
