from bson import ObjectId
import requests

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    stream_with_context
)

from flask_jwt_extended import jwt_required

from gridfs.errors import NoFile

from config.mongodb import (
    db,
    fs
)
from config.sqlserver import get_connection
from services.jikan import get_anime
from services.users import get_current_user


media_bp = Blueprint(
    "media",
    __name__
)

IMAGE_TIMEOUT = 15


def _image_url(data):
    anime = data.get("data", data) if isinstance(data, dict) else {}
    images = anime.get("images", {})
    jpg = images.get("jpg", {})
    webp = images.get("webp", {})
    return (
        jpg.get("large_image_url")
        or jpg.get("image_url")
        or webp.get("large_image_url")
        or webp.get("image_url")
    )


def _catalog_image_url(anime_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT image_url FROM Animes WHERE anime_id = ?",
            anime_id
        )
        row = cursor.fetchone()
        cursor.close()
    finally:
        connection.close()

    if not row or not row.image_url:
        return None
    return row.image_url.replace(
        "myanimelist.cdn-dena.com",
        "myanimelist.net"
    )


@media_bp.route(
    "/<int:anime_id>/image",
    methods=["GET"]
)
def anime_image(anime_id):
    stored = db.anime_media.find_one({
        "animeId": anime_id,
        "source": "jikan"
    })

    if stored:
        try:
            grid_file = fs.get(stored["fileId"])
            return Response(
                grid_file,
                content_type=grid_file.content_type or "image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"}
            )
        except NoFile:
            db.anime_media.delete_one({"_id": stored["_id"]})

    image_url = _catalog_image_url(anime_id)
    error = None
    if not image_url:
        data, error = get_anime(anime_id)
        image_url = _image_url(data) if not error else None
    if not image_url:
        return jsonify({"error": error or "El anime no tiene una imagen disponible"}), 404 if not error else 502

    try:
        response = requests.get(image_url, timeout=IMAGE_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if not content_type.startswith("image/"):
            return jsonify({"error": "La imagen externa no tiene un formato válido"}), 502

        file_id = fs.put(
            response.content,
            filename=f"anime-{anime_id}.jpg",
            contentType=content_type,
            metadata={"animeId": anime_id, "source": "jikan", "sourceUrl": image_url}
        )
        db.anime_media.update_one(
            {"animeId": anime_id, "source": "jikan"},
            {"$set": {"fileId": file_id, "filename": f"anime-{anime_id}.jpg", "contentType": content_type, "source": "jikan"}},
            upsert=True
        )
        return Response(
            response.content,
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"}
        )
    except requests.exceptions.RequestException as request_error:
        print(f"Error descargando imagen de Jikan: {request_error}")
        return jsonify({"error": "No se pudo descargar la imagen del anime"}), 502
    except Exception as error:
        print(f"Error guardando imagen en MongoDB: {error}")
        return jsonify({"error": "No se pudo guardar la imagen en MongoDB"}), 503


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf"
}


@media_bp.route(
    "/<int:anime_id>",
    methods=["POST"]
)
@jwt_required()
def upload_media(anime_id):
    user_id = get_current_user()["id"]
    if "file" not in request.files:
        return jsonify({
            "error": "Debe enviar un archivo en el campo file"
        }), 400

    uploaded_file = request.files["file"]

    if not uploaded_file.filename:
        return jsonify({
            "error": "El archivo no tiene nombre"
        }), 400

    if uploaded_file.mimetype not in ALLOWED_CONTENT_TYPES:
        return jsonify({
            "error": (
                "Solo se permiten JPG, PNG, WEBP y PDF"
            )
        }), 400

    try:
        file_id = fs.put(
            uploaded_file.stream,
            filename=uploaded_file.filename,
            contentType=uploaded_file.mimetype,
            metadata={
                "animeId": anime_id,
                "uploadedBy": user_id
            }
        )

        db.anime_media.insert_one({
            "animeId": anime_id,
            "fileId": file_id,
            "filename": uploaded_file.filename,
            "contentType": uploaded_file.mimetype,
            "uploadedBy": user_id
        })

        return jsonify({
            "message": "Archivo guardado en MongoDB",
            "animeId": anime_id,
            "fileId": str(file_id),
            "url": (
                f"/api/media/file/{file_id}"
            )
        }), 201

    except Exception as error:
        print(
            f"Error MongoDB upload: {error}"
        )

        return jsonify({
            "error": "No se pudo almacenar el archivo"
        }), 500


@media_bp.route(
    "/<int:anime_id>",
    methods=["GET"]
)
def anime_media(anime_id):
    cursor = db.anime_media.find({
        "animeId": anime_id
    })

    items = []

    for item in cursor:
        items.append({
            "id": str(item["_id"]),
            "animeId": item["animeId"],
            "fileId": str(item["fileId"]),
            "filename": item["filename"],
            "contentType": item["contentType"],
            "url": (
                f"/api/media/file/{item['fileId']}"
            )
        })

    return jsonify({
        "animeId": anime_id,
        "files": items
    })


@media_bp.route(
    "/file/<file_id>",
    methods=["GET"]
)
def download_media(file_id):
    try:
        object_id = ObjectId(file_id)

        grid_file = fs.get(
            object_id
        )

    except (NoFile, Exception):
        return jsonify({
            "error": "Archivo no encontrado"
        }), 404

    def generate():
        while True:
            chunk = grid_file.read(64 * 1024)

            if not chunk:
                break

            yield chunk

    response = Response(
        stream_with_context(generate()),
        content_type=(
            grid_file.content_type
            or "application/octet-stream"
        )
    )

    response.headers["Content-Disposition"] = (
        f'inline; filename="{grid_file.filename}"'
    )

    return response


@media_bp.route(
    "/file/<file_id>",
    methods=["DELETE"]
)
@jwt_required()
def delete_media(file_id):
    user_id = get_current_user()["id"]
    try:
        object_id = ObjectId(file_id)

    except Exception:
        return jsonify({
            "error": "ID de archivo inválido"
        }), 400

    if not fs.exists(object_id):
        return jsonify({
            "error": "Archivo no encontrado"
        }), 404

    try:
        media = db.anime_media.find_one({"fileId": object_id})
        if not media or media.get("uploadedBy") != user_id:
            return jsonify({
                "error": "Solo puedes eliminar los archivos que has subido"
            }), 403

        fs.delete(object_id)

        db.anime_media.delete_many({
            "fileId": object_id
        })

        return jsonify({
            "message": "Archivo eliminado correctamente"
        })

    except Exception as error:
        print(
            f"Error eliminando archivo: {error}"
        )

        return jsonify({
            "error": "No se pudo eliminar el archivo"
        }), 500
