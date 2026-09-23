from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services import recommender


recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.get("/status")
def status():
    return jsonify(recommender.model_status()), 200


@recommendations_bp.get("")
def global_recommendations():
    limit = max(1, min(request.args.get("limit", 10, type=int), 50))
    try:
        items = recommender.generate_global_recommendations(limit)
    except Exception as error:
        print(f"Error generando recomendaciones globales: {error}")
        return jsonify({"error": "No se pudieron generar recomendaciones"}), 503
    if items is None:
        return jsonify({"error": "No hay datos suficientes para entrenar el modelo"}), 503
    response = {
        "mode": "global",
        "requestedLimit": limit,
        "returnedCount": len(items),
        "recommendations": items
    }
    if len(items) < limit:
        response["message"] = "El dataset actual no contiene suficientes animes distintos"
    return jsonify(response), 200


@recommendations_bp.post("/train")
def train():
    try:
        return jsonify(recommender.train_model()), 200
    except Exception as error:
        print(f"Error entrenando modelo: {error}")
        return jsonify({"error": "No se pudo entrenar el modelo"}), 503


def _recommendations(user_id):
    limit = max(1, min(request.args.get("limit", 10, type=int), 50))
    try:
        items = recommender.generate_recommendations(user_id, limit)
    except Exception as error:
        print(f"Error generando recomendaciones: {error}")
        return jsonify({"error": "No se pudieron generar recomendaciones"}), 503
    if items is None:
        return jsonify({"error": "El modelo aún no está entrenado"}), 503
    message = None
    if not items:
        message = "No hay animes nuevos disponibles para este usuario"
    elif len(items) < limit:
        message = "No hay suficientes animes nuevos para completar el límite solicitado"
    response = {
        "userId": user_id,
        "requestedLimit": limit,
        "returnedCount": len(items),
        "recommendations": items
    }
    if message:
        response["message"] = message
    return jsonify(response), 200


@recommendations_bp.get("/me")
@jwt_required()
def my_recommendations():
    return _recommendations(int(get_jwt_identity()))


@recommendations_bp.get("/<int:user_id>")
def user_recommendations(user_id):
    return _recommendations(user_id)