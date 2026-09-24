from pyspark.sql import SparkSession
from pyspark.ml.recommendation import ALS

spark = SparkSession.builder \
    .appName("EntrenamientoModeloAnime") \
    .config("spark.driver.memory", "2g") \
    .config("spark.jars", "mssql-jdbc-13.4.0.jre11.jar") \
    .getOrCreate()

ratings = spark.read \
    .format("jdbc") \
    .option("url", "jdbc:sqlserver://host.docker.internal:11433;databaseName=Anime;encrypt=true;trustServerCertificate=true;") \
    .option("dbtable", "Reviews") \
    .option("user", "sa") \
    .option("password", "P@ssw0rd") \
    .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver") \
    .load()
(training, testing) = ratings.randomSplit([0.8, 0.2])

als = ALS(maxIter=5, regParam=0.01, userCol="user_id", itemCol="anime_id", ratingCol="my_score")
modelo = als.fit(training)

modelo.write().overwrite().save("modelo_als")

print("Modelo entrenado y guardado con éxito en 'modelo_als'")
spark.stop()