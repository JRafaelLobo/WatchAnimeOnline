from flask import Flask, jsonify, request

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    IntegerType,
    FloatType,
    LongType
)
from pyspark.ml.recommendation import ALS


app = Flask(__name__)


# ============================================================
# 1. CONFIGURATION
# ============================================================

MAX_ROWS = 1_000_000

CSV_PATH = "/home/jovyan/work/ratings.csv"


# ============================================================
# 2. CREATE SPARK SESSION
# ============================================================

spark = (
    SparkSession.builder
    .appName("RecomendacionMovieAPI")
    .config("spark.driver.memory", "4g")
    .config(
        "spark.jars.packages",
        "com.mysql:mysql-connector-j:8.4.0"
    )
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")


# ============================================================
# 3. MYSQL CONNECTION
# ============================================================

MYSQL_URL = (
    "jdbc:mysql://host.docker.internal:3306/spark"
    "?useCursorFetch=true"
    "&defaultFetchSize=10000"
)

MYSQL_PROPERTIES = {
    "user": "root",
    "password": "Patrick151.",
    "driver": "com.mysql.cj.jdbc.Driver"
}


# ============================================================
# 4. CSV SCHEMA
# ============================================================

ratings_schema = StructType([
    StructField("userId", IntegerType(), False),
    StructField("movieId", IntegerType(), False),
    StructField("rating", FloatType(), False),
    StructField("timestamp", LongType(), False)
])


# ============================================================
# 5. READ 1 MILLION RATINGS FROM MYSQL
# ============================================================

def load_ratings_sql():

    query = f"""
        (
            SELECT userId, movieId, rating
            FROM ratings
            LIMIT {MAX_ROWS}
        ) AS limited_ratings
    """

    ratings = spark.read.jdbc(
        url=MYSQL_URL,
        table=query,
        properties=MYSQL_PROPERTIES
    )

    # Make types explicit for ALS
    ratings = ratings.selectExpr(
        "CAST(userId AS INT) AS userId",
        "CAST(movieId AS INT) AS movieId",
        "CAST(rating AS FLOAT) AS rating"
    )

    # Spread work across Spark partitions
    ratings = ratings.repartition(8, "userId")

    return ratings


# ============================================================
# 6. READ 1 MILLION RATINGS FROM CSV
# ============================================================

def load_ratings_csv():

    ratings = (
        spark.read
        .option("header", True)
        .schema(ratings_schema)
        .csv(CSV_PATH)
        .select(
            "userId",
            "movieId",
            "rating"
        )
        .limit(MAX_ROWS)
        .repartition(8, "userId")
    )

    return ratings


# ============================================================
# 7. TRAIN ALS MODEL
# ============================================================

def train_model(ratings):

    training, testing = ratings.randomSplit(
        [0.8, 0.2],
        seed=42
    )

    als = ALS(
        maxIter=5,
        regParam=0.01,
        userCol="userId",
        itemCol="movieId",
        ratingCol="rating",
        coldStartStrategy="drop"
    )

    return als.fit(training)


# ============================================================
# 8. TRAIN MODELS
# ============================================================

print("Loading 1,000,000 ratings from MySQL...")
sql_ratings = load_ratings_sql()

print("Training SQL ALS model...")
sql_model = train_model(sql_ratings)

print("SQL model ready.")


print("Loading 1,000,000 ratings from CSV...")
csv_ratings = load_ratings_csv()

print("Training CSV ALS model...")
csv_model = train_model(csv_ratings)

print("CSV model ready.")


# ============================================================
# 9. RECOMMENDATION FUNCTION
# ============================================================

def generate_recommendations(model, user_id, limit):

    users = spark.createDataFrame(
        [(user_id,)],
        ["userId"]
    )

    result = model.recommendForUserSubset(
        users,
        limit
    )

    rows = result.collect()

    if not rows:
        return None

    return [
        {
            "movieId": recommendation.movieId,
            "predictedRating": float(recommendation.rating)
        }
        for recommendation in rows[0].recommendations
    ]


# ============================================================
# 10. API ENDPOINTS
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "message": "Movie Recommendation API is running",
        "maxRowsPerSource": MAX_ROWS,
        "endpoints": {
            "sql": "/recommendations/sql/<user_id>",
            "csv": "/recommendations/csv/<user_id>"
        }
    })


# ============================================================
# SQL RECOMMENDATIONS
# ============================================================

@app.route(
    "/recommendations/sql/<int:user_id>",
    methods=["GET"]
)
def recommendations_sql(user_id):

    limit = request.args.get(
        "limit",
        default=10,
        type=int
    )

    recommendations = generate_recommendations(
        sql_model,
        user_id,
        limit
    )

    if recommendations is None:

        return jsonify({
            "source": "mysql",
            "userId": user_id,
            "message": "User not found or no recommendations available"
        }), 404

    return jsonify({
        "source": "mysql",
        "userId": user_id,
        "recommendations": recommendations
    })


# ============================================================
# CSV RECOMMENDATIONS
# ============================================================

@app.route(
    "/recommendations/csv/<int:user_id>",
    methods=["GET"]
)
def recommendations_csv(user_id):

    limit = request.args.get(
        "limit",
        default=10,
        type=int
    )

    recommendations = generate_recommendations(
        csv_model,
        user_id,
        limit
    )

    if recommendations is None:

        return jsonify({
            "source": "csv",
            "userId": user_id,
            "message": "User not found or no recommendations available"
        }), 404

    return jsonify({
        "source": "csv",
        "userId": user_id,
        "recommendations": recommendations
    })


# ============================================================
# 11. START FLASK
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )