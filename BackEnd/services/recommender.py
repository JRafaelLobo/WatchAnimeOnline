import os
import threading

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
	query = (
		f"(SELECT TOP {MAX_ROWS} "
		"user_id AS userId, "
		"anime_id AS movieId, "
		"my_score AS rating "
		"FROM Reviews "
		"WHERE user_id IS NOT NULL "
		"AND anime_id IS NOT NULL "
		"AND my_score IS NOT NULL "
		"AND my_score > 0) AS limited_ratings"
	)
	ratings = spark.read.jdbc(url=JDBC_URL, table=query, properties=JDBC_PROPERTIES)
	return ratings.selectExpr(
		"CAST(userId AS INT) AS userId",
		"CAST(movieId AS INT) AS movieId",
		"CAST(rating AS FLOAT) AS rating"
	).repartition(8, "userId")


def train_model():
	global _model
	from pyspark.ml.recommendation import ALS
	ratings = load_ratings()
	if ratings.limit(1).count() == 0:
		_model = None
		return {"success": False, "message": "No existen ratings para entrenar"}
	als = ALS(
		maxIter=10, regParam=0.1, rank=10, userCol="userId",
		itemCol="movieId", ratingCol="rating", coldStartStrategy="drop",
		nonnegative=True
	)
	with _model_lock:
		_model = als.fit(ratings)
	return {"success": True, "message": "Modelo ALS entrenado correctamente"}


def generate_recommendations(user_id, limit=10):
	if _model is None:
		return None
	users = _get_spark().createDataFrame([(int(user_id),)], ["userId"])
	rows = _model.recommendForUserSubset(users, limit).collect()
	if not rows:
		return []
	return [
		{"movieId": int(item.movieId), "predictedRating": float(item.rating)}
		for item in rows[0].recommendations
	]


def model_is_ready():
	return _model is not None
