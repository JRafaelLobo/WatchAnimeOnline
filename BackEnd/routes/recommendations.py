from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from services import recommender
from services.users import get_current_user


recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.after_request
def prevent_personal_recommendation_caching(response):
    if request.endpoint in {
        "recommendations.my_recommendations",
        "recommendations.user_recommendations",
    }:
        response.headers["Cache-Control"] = "no-store"
    return response


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


def _recommendations(account):
    limit = max(1, min(request.args.get("limit", 10, type=int), 50))
    profile = account.get("profile")
    user_id = profile["userId"] if profile else None
    mode = "global"
    message = None
    try:
        if profile:
            trained_user = recommender.has_trained_user(user_id)
            if trained_user is None:
                return jsonify({"error": "No hay datos suficientes para entrenar el modelo"}), 503
            if trained_user:
                mode = "personalized"
                items = recommender.generate_recommendations(user_id, limit)
            else:
                items = recommender.generate_global_recommendations(limit)
                message = (
                    "Tu perfil aún no tiene valoraciones en el modelo. "
                    "Te mostramos recomendaciones generales."
                )
        else:
            items = recommender.generate_global_recommendations(limit)
            message = (
                "Tu cuenta no tiene un perfil de anime vinculado. "
                "Te mostramos recomendaciones generales."
            )
    except Exception as error:
        print(f"Error generando recomendaciones: {error}")
        return jsonify({"error": "No se pudieron generar recomendaciones"}), 503
    if items is None:
        return jsonify({"error": "El modelo aún no está entrenado"}), 503
    if mode == "personalized" and not items:
        message = "No hay animes nuevos disponibles para este usuario"
    elif mode == "personalized" and len(items) < limit:
        message = "No hay suficientes animes nuevos para completar el límite solicitado"
    response = {
        "mode": mode,
        "accountId": account["id"],
        "userId": user_id,
        "profile": profile,
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
    return _recommendations(get_current_user())


@recommendations_bp.get("/<int:user_id>")
@jwt_required()
def user_recommendations(user_id):
    account = get_current_user()
    profile = account.get("profile")
    if not profile or profile["userId"] != user_id:
        return jsonify({"error": "Solo puedes consultar las recomendaciones de tu propio perfil"}), 403
    return _recommendations(account)
