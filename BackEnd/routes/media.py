from bson import ObjectId

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    stream_with_context
)

from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required
)

from gridfs.errors import NoFile

from config.mongodb import (
    db,
    fs
)


media_bp = Blueprint(
    "media",
    __name__
)


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

    user_id = int(
        get_jwt_identity()
    )

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