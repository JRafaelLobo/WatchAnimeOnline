import os
import threading
from pathlib import Path

MAX_ROWS = int(os.getenv("MAX_RATINGS", "1000000"))
SQL_SERVER = os.getenv("SQL_SERVER", "sqlserver")
SQL_PORT = os.getenv("SQL_PORT", "1433")
SQL_DATABASE = os.getenv("SQL_DATABASE", "AnimeDB")
SQL_USER = os.getenv("SQL_USER", "sa")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")
JDBC_URL = (
	f"jdbc:sqlserver://{SQL_SERVER}:{SQL_PORT};"
	f"databaseName={SQL_DATABASE};encrypt=true;trustServerCertificate=true;"
)
JDBC_PROPERTIES = {
	"user": SQL_USER,
	"password": SQL_PASSWORD,
	"driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver"
}
_model = None
_model_lock = threading.Lock()
_spark = None
_seen_items = {}
_model_source = None
MODEL_PATH = os.getenv("ALS_MODEL_PATH", "/app/model/als_model")


def _get_spark():
	global _spark
	if _spark is None:
		from pyspark.sql import SparkSession

		_spark = (
			SparkSession.builder.appName("AnimeRecommendationAPI")
			.config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "2g"))
			.config("spark.jars", "/app/jars/mssql-jdbc.jar")
			.getOrCreate()
		)
		_spark.sparkContext.setLogLevel("WARN")
	return _spark


def load_ratings():
	spark = _get_spark()
	if _sql_table_exists("ratings"):
		query = (
			f"(SELECT TOP {MAX_ROWS} userId, movieId, rating "
			"FROM ratings WHERE userId IS NOT NULL "
			"AND movieId IS NOT NULL AND rating IS NOT NULL AND rating > 0) AS source_ratings"
		)
	else:
		query = (
			f"(SELECT TOP {MAX_ROWS} user_id AS userId, anime_id AS movieId, my_score AS rating "
			"FROM Reviews WHERE user_id IS NOT NULL AND anime_id IS NOT NULL "
			"AND my_score IS NOT NULL AND my_score > 0) AS source_reviews"
		)
	ratings = spark.read.jdbc(url=JDBC_URL, table=query, properties=JDBC_PROPERTIES)
	return ratings.selectExpr(
		"CAST(userId AS INT) AS userId",
		"CAST(movieId AS INT) AS movieId",
		"CAST(rating AS FLOAT) AS rating"
	).repartition(8, "userId")


def _sql_table_exists(table_name):
	import pyodbc

	connection = pyodbc.connect(
		"DRIVER={ODBC Driver 18 for SQL Server};"
		f"SERVER={SQL_SERVER},{SQL_PORT};"
		f"DATABASE={SQL_DATABASE};"
		f"UID={SQL_USER};"
		f"PWD={SQL_PASSWORD};"
		"TrustServerCertificate=yes;"
	)
	try:
		cursor = connection.cursor()
		cursor.execute(
			"SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
			table_name
		)
		return cursor.fetchone() is not None
	finally:
		connection.close()


def train_model():
	global _model, _seen_items, _model_source
	from pyspark.ml.recommendation import ALS
	from pyspark.sql.functions import collect_set
	ratings = load_ratings()
	if ratings.limit(1).count() == 0:
		_model = None
		_seen_items = {}
		return {"success": False, "message": "No existen ratings para entrenar"}
	_seen_items = {
		int(row.userId): set(row.items)
		for row in ratings.groupBy("userId").agg(
			collect_set("movieId").alias("items")
		).collect()
	}
	als = ALS(
		maxIter=10, regParam=0.1, rank=10, userCol="userId",
		itemCol="movieId", ratingCol="rating", coldStartStrategy="drop",
		nonnegative=True
	)
	with _model_lock:
		_model = als.fit(ratings)
	_model_source = "trained"
	try:
		Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
		_model.write().overwrite().save(MODEL_PATH)
		_model_source = "trained_and_saved"
	except Exception as error:
		print(f"No se pudo guardar el modelo ALS: {error}")
	return {
		"success": True,
		"message": "Modelo ALS entrenado correctamente",
		"source": _model_source
	}


def load_saved_model():
	global _model, _model_source, _seen_items
	if _model is not None:
		return True
	model_path = Path(MODEL_PATH)
	if not model_path.exists():
		return False
	try:
		from pyspark.ml.recommendation import ALSModel
		_get_spark()
		_model = ALSModel.load(MODEL_PATH)
		_model_source = "persisted"
		_seen_items = _load_seen_items()
		return True
	except Exception as error:
		print(f"No se pudo cargar el modelo ALS persistido: {error}")
		return False


def _load_seen_items():
	from pyspark.sql.functions import collect_set

	ratings = load_ratings()
	return {
		int(row.userId): set(row.items)
		for row in ratings.groupBy("userId").agg(
			collect_set("movieId").alias("items")
		).collect()
	}


def generate_recommendations(user_id, limit=10):
	if not _ensure_model():
		return None
	seen_items = _seen_items.get(int(user_id), set())
	users = _get_spark().createDataFrame([(int(user_id),)], ["userId"])
	candidate_limit = min(limit + len(seen_items), 100)
	rows = _model.recommendForUserSubset(users, candidate_limit).collect()
	if not rows:
		return []
	recommendations = [
		{"movieId": int(item.movieId), "predictedRating": float(item.rating)}
		for item in rows[0].recommendations
		if int(item.movieId) not in seen_items
	]
	return recommendations[:limit]


def _ensure_model():
	if _model is not None:
		return True
	if load_saved_model():
		return True
	result = train_model()
	return bool(result.get("success"))


def generate_global_recommendations(limit=10):
	"""Aggregate ALS recommendations across all known users."""
	if not _ensure_model():
		return None

	from pyspark.sql.functions import avg, col, count, desc, explode

	candidate_limit = min(max(limit * 3, limit), 100)
	all_recommendations = _model.recommendForAllUsers(candidate_limit)
	exploded = all_recommendations.select(
		explode("recommendations").alias("recommendation")
	).select(
		col("recommendation.movieId").alias("movieId"),
		col("recommendation.rating").alias("rating")
	)

	rows = (
		exploded.groupBy("movieId")
		.agg(
			avg("rating").alias("predictedRating"),
			count("rating").alias("userSupport")
		)
		.orderBy(desc("predictedRating"), desc("userSupport"))
		.limit(limit)
		.collect()
	)
	return [
		{
			"movieId": int(row.movieId),
			"predictedRating": float(row.predictedRating),
			"userSupport": int(row.userSupport)
		}
		for row in rows
	]


def model_is_ready():
	return _model is not None


def model_status():
	return {
		"ready": model_is_ready(),
		"source": _model_source,
		"modelPath": MODEL_PATH,
		"availableItems": len({item for items in _seen_items.values() for item in items})
	}
