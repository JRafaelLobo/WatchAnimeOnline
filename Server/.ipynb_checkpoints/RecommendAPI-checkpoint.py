from flask import Flask, jsonify, request
from pyspark.sql import SparkSession
from pyspark.ml.recommendation import ALSModel

app = Flask(__name__)

spark = SparkSession.builder \
    .appName("APIAnimeRecommendations") \
    .config("spark.driver.memory", "2g") \
    .config("spark.ui.enabled", "false") \
    .getOrCreate()

modelo = ALSModel.load("modelo_als")

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4040)