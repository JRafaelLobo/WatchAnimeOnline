import os
import threading

from pyspark.ml.recommendation import ALS
from pyspark.sql import SparkSession


MAX_ROWS = int(
    os.getenv("MAX_RATINGS", "1000000")
)


# ============================================================
# SPARK
# ============================================================

spark = (
    SparkSession.builder
    .appName("AnimeRecommendationAPI")
    .config(
        "spark.driver.memory",
        os.getenv("SPARK_DRIVER_MEMORY", "2g")
    )
    .config(
        "spark.jars",
        "/app/jars/mssql-jdbc.jar"
    )
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")


# ============================================================
# SQL SERVER
# ============================================================

SQL_SERVER = os.getenv(
    "SQL_SERVER",
    "sqlserver"
)

SQL_PORT = os.getenv(
    "SQL_PORT",
    "1433"
)

SQL_DATABASE = os.getenv(
    "SQL_DATABASE",
    "AnimeDB"
)

SQL_USER = os.getenv(
    "SQL_USER",
    "sa"
)

SQL_PASSWORD = os.getenv(
    "SQL_PASSWORD"
)


JDBC_URL = (
    f"jdbc:sqlserver://{SQL_SERVER}:{SQL_PORT};"
    f"databaseName={SQL_DATABASE};"
    "encrypt=true;"
    "trustServerCertificate=true;"
)


JDBC_PROPERTIES = {
    "user": SQL_USER,
    "password": SQL_PASSWORD,
    "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver"
}


_model = None
_model_lock = threading.Lock()


# ============================================================
# LOAD RATINGS
# ============================================================

def load_ratings():
    query = f"""
    (
        SELECT TOP {MAX_ROWS}
            userId,
            movieId,
            rating
        FROM ratings
        ORDER BY userId, movieId
    ) AS limited_ratings
    """

    ratings = spark.read.jdbc(
        url=JDBC_URL,
        table=query,
        properties=JDBC_PROPERTIES
    )

    ratings = ratings.selectExpr(
        "CAST(userId AS INT) AS userId",
        "CAST(movieId AS INT) AS movieId",
        "CAST(rating AS FLOAT) AS rating"
    )

    return ratings.repartition(
        8,
        "userId"
    )


# ============================================================
# TRAIN
# ============================================================

def train_model():
    global _model

    ratings = load_ratings()

    if ratings.limit(1).count() == 0:
        _model = None

        return {
            "success": False,
            "message": "No existen ratings para entrenar"
        }

    als = ALS(
        maxIter=10,
        regParam=0.1,
        rank=10,
        userCol="userId",
        itemCol="movieId",
        ratingCol="rating",
        coldStartStrategy="drop",
        nonnegative=True
    )

    with _model_lock:
        _model = als.fit(ratings)

    return {
        "success": True,
        "message": "Modelo ALS entrenado correctamente"
    }


# ============================================================
# RECOMMENDATIONS
# ============================================================

def generate_recommendations(
    user_id,
    limit=10
):
    if _model is None:
        return None

    users = spark.createDataFrame(
        [(int(user_id),)],
        ["userId"]
    )

    result = _model.recommendForUserSubset(
        users,
        limit
    )

    rows = result.collect()

    if not rows:
        return []

    recommendations = []

    for recommendation in rows[0].recommendations:
        recommendations.append({
            "movieId": int(
                recommendation.movieId
            ),
            "predictedRating": float(
                recommendation.rating
            )
        })

    return recommendations


def model_is_ready():
    return _model is not None