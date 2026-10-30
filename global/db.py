from pymongo import MongoClient

#Mongo connection
client = MongoClient("mongodb://localhost:27017")
db = client.ev_charging
stations = db.stations
users = db.users