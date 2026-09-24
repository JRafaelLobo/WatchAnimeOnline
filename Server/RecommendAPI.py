import os
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from pyspark.sql import SparkSession
from pyspark.ml.recommendation import ALSModel

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)

server_dir = Path(__file__).resolve().parent

spark = SparkSession.builder \
    .appName("APIAnime") \
    .config("spark.driver.memory", "2g") \
    .config("spark.jars", str(server_dir / "mssql-jdbc-13.4.0.jre11.jar")) \
    .config("spark.ui.enabled", "false") \
    .getOrCreate()

modelo = ALSModel.load(str(server_dir / "modelo_als"))


@app.route('/api/users/check', methods=['POST'])
def check_user():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()

    if not username:
        return jsonify({
            "error": "username es obligatorio"
        }), 400

    escaped_username = username.replace("'", "''")
    query = (
        "SELECT username, user_id, stats_mean_score "
        "FROM Usuarios "
        f"WHERE username = '{escaped_username}'"
    )

    try:
        users = spark.read \
            .format("jdbc") \
            .option(
                "url",
                "jdbc:sqlserver://host.docker.internal:11433;"
                "databaseName=Anime;"
                "encrypt=true;"
                "trustServerCertificate=true;"
            ) \
            .option("query", query) \
            .option("user", "sa") \
            .option("password", "P@ssw0rd") \
            .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver") \
            .load()

        user = users.first()

        if not user:
            return jsonify({
                "error": "El usuario no existe"
            }), 404

        return jsonify({
            "username": user["username"],
            "user_id": user["user_id"],
            "stats_mean_score": user["stats_mean_score"]
        }), 200
    except Exception as error:
        return jsonify({
            "error": "Error al consultar el usuario",
            "detalle": str(error)
        }), 500

@app.route('/api/v1/recomendaciones/<int:user_id>', methods=['GET'])
def get_recommendations(user_id):
    try:
        user_df = spark.createDataFrame([(user_id,)], ["user_id"])

        user_recs = modelo.recommendForUserSubset(user_df, 10).collect()

        if not user_recs:
            return jsonify({"error": f"No se encontraron recomendaciones para el usuario {user_id}"}), 404

        movie_ids = [rec.anime_id for rec in user_recs[0].recommendations]

        return jsonify({
            "user_id": user_id,
            "recomendaciones": movie_ids
        }), 200

    except Exception as e:
        return jsonify({"error": "Error interno al procesar recomendaciones", "detalle": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    try:
        app.run(
            host='0.0.0.0',
            port=int(os.getenv('PORT', '5001'))
        )
    finally:
        spark.stop()