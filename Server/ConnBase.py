import os
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from pyspark.sql import SparkSession


app = Flask(__name__)

spark = SparkSession.builder \
	.appName("ServidorUsuariosAnime") \
	.config(
		"spark.jars",
		str(Path(__file__).resolve().parent / "mssql-jdbc-13.4.0.jre11.jar")
	) \
	.getOrCreate()

CORS(
	app,
	resources={
		r"/api/*": {
			"origins": "*"
		}
	}
)


@app.route("/api/users/check", methods=["POST"])
def check_user():
	data = request.get_json(silent=True) or {}
	username = str(data.get("username", "")).strip()

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


@app.route("/health", methods=["GET"])
def health():
	return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
	try:
		app.run(
			host="0.0.0.0",
			port=int(os.getenv("PORT", "5001")),
			debug=True
		)
	finally:
		spark.stop()
