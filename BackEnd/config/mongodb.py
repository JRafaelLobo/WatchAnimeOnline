import os

from pymongo import MongoClient
import gridfs


MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://animeadmin:password@mongodb:27017/"
    "anime_media?authSource=admin"
)


client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000
)

db = client["anime_media"]

fs = gridfs.GridFS(db)