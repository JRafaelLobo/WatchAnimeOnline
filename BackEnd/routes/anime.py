from flask import Blueprint, jsonify, request

from services.jikan import (
    get_anime,
    get_genres,
    get_season_now,
    get_top_anime,
    search_anime
)


anime_bp = Blueprint(
    "anime",
    __name__
)


@anime_bp.route("/search", methods=["GET"])
def anime_search():
    query = request.args.get(
        "q",
        "",
        type=str
    ).strip()

    page = request.args.get(
        "page",
        1,
        type=int
    )

    limit = request.args.get(
        "limit",
        12,
        type=int
    )

    page = max(page, 1)
    limit = max(1, min(limit, 25))

    if not query:
        return jsonify({
            "error": "Debe indicar el parámetro q"
        }), 400

    data, error = search_anime(
        query,
        page,
        limit
    )

    if error:
        return jsonify({
            "error": error
        }), 502

    return jsonify(data), 200


@anime_bp.route("/top", methods=["GET"])
def anime_top():
    page = max(
        request.args.get("page", 1, type=int),
        1
    )

    limit = request.args.get(
        "limit",
        12,
        type=int
    )

    limit = max(1, min(limit, 25))

    data, error = get_top_anime(
        page,
        limit
    )

    if error:
        return jsonify({
            "error": error
        }), 502

    return jsonify(data), 200


@anime_bp.route("/season/now", methods=["GET"])
def anime_season_now():
    page = max(
        request.args.get("page", 1, type=int),
        1
    )

    limit = request.args.get(
        "limit",
        12,
        type=int
    )

    limit = max(1, min(limit, 25))

    data, error = get_season_now(
        page,
        limit
    )

    if error:
        return jsonify({
            "error": error
        }), 502

    return jsonify(data), 200


@anime_bp.route("/genres", methods=["GET"])
def anime_genres():
    data, error = get_genres()

    if error:
        return jsonify({
            "error": error
        }), 502

    return jsonify(data), 200


@anime_bp.route("/<int:anime_id>", methods=["GET"])
def anime_detail(anime_id):
    data, error = get_anime(anime_id)

    if error:
        return jsonify({
            "error": error
        }), 502

    return jsonify(data), 200