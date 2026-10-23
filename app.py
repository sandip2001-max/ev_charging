from flask import Flask, make_response, jsonify, request
#pip install pymongo
from pymongo import MongoClient
from bson import ObjectId

import jwt
import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecret'

#Mongo connection
client = MongoClient("mongodb://localhost:27017")
db = client.ev_charging
stations = db.stations
users = db.users


# Demonstration login: real user accounts and admin permissions
@app.route("/api/login", methods=['GET'])
def login():
    auth = request.authorization

    if auth and auth.password == 'password':
        role = "admin" if auth.username == "admin" else "user"
        
        token = jwt.encode({
            'user' : auth.username,
            'role' : role,
            'exp' : datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)
        },
        app.config['SECRET_KEY'],
        algorithm="HS256")

        return make_response(jsonify({"token": token}), 200)
    
    return make_response("Could not verify", 401, \
        {'WWW-Authenticate': 'Basic realm = "Login required"'})


#================================== JWT decorator ========================
def jwt_required(func):
    @wraps(func)
    def jwt_required_wrapper(*args, **kwargs):
        token = request.args.get('token')

        if not token:
            return make_response(jsonify({"message": "Token is missing"}), 401)

        try:
            data = jwt.decode(token,
                    app.config['SECRET_KEY'],
                    algorithms="HS256")
        except:
            return make_response(jsonify({"message":"Token is invalid"}), 401)
        
        return func(*args, **kwargs)

    return jwt_required_wrapper



#================================== station routes ========================
@app.route("/", methods=["GET"])
def index():
    return make_response("<h1>Welcome to the EV Charging API</h1>", 200)


@app.route("/api/stations", methods=["GET"])
#@jwt_required
def show_all_stations():
    
    page_num, page_size = 1, 3
    if request.args.get('pn'):
        page_num = int(request.args.get('pn'))
    if request.args.get('ps'):
        page_size = int(request.args.get('ps'))

    page_start = (page_size * (page_num - 1))

    data_to_return = []

    for station in stations.find().skip(page_start).limit(page_size):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)


# fetch by ID
@app.route("/api/stations/<string:station_id>", methods=["GET"])
#@jwt_required
def show_one_station(station_id):

    if not ObjectId.is_valid(station_id):
        return make_response(jsonify({"error":"Invalid station ID"}), 400)
    
    station = stations.find_one({'_id':ObjectId(station_id)})

    if station is not None:
        station['_id'] = str(station['_id'])
        return make_response(jsonify(station), 200)

    else:
        return make_response(jsonify({"error":"Invalid station ID"}), 404)


#GET stations with available chargers
@app.route("/api/stations/available", methods=["GET"])
#@jwt_required
def show_available_stations():
    data_to_return = []

    for station in stations.find({"available_chargers":{"$gt":0}}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)

#GET stations filtered by charger type (Ac or Dc)
@app.route("/api/stations/type/<string:charger_type>", methods=["GET"])
#@jwt_required
def show_stations_by_type(charger_type):
    if charger_type not in ["Ac", "Dc"]:
        return make_response(jsonify({"error":"Invalid charger type"}), 400)
    data_to_return = []

    for station in stations.find({"charger_type": charger_type}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)

#GET stations nearby (search by location substring)
@app.route("/api/stations/nearby/<string:location>", methods=["GET"])
#@jwt_required
def show_stations_nearby():
    place = request.args.get('place')

    if not place:
        return make_response(jsonify({"error":"Missing'place'"}), 400)

    data_to_return = []

    for station in stations.find({"location": {"$regex": place, "$options": "i"}}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)

#get stations by location / status / min_power
@app.route("/api/stations/search", methods=["GET"])
#@jwt_required
def search_stations():
    query = {}
    location = request.args.get('location')
    status = request.args.get('status')
    min_power = request.args.get('min_power')

    if location:
        query['location'] = {"$regex": location, "$options": "i"}
    if status:
        query['status'] = status
    if min_power:
        try:
            query['power_output'] = {"$gte": float(min_power)}
        except ValueError:
            return make_response(jsonify({"error":"Invalid 'min_power' value"}), 400)

    data_to_return = []

    for station in stations.find(query):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)

#GET analytics - aggregation of usage and energy
@app.route("/api/stations/analytics", methods=["GET"])
#@jwt_required
def get_analytics():

    pipeline = [
        {
            "$group": {
                "_id": "$charger_type",
                "total_stations": {"$sum": 1},
                "total_chargers": {"$sum": "$total_chargers"},
                "available_chargers": {"$sum": "$available_chargers"},
                "charging_chargers": {"$sum": "$charging_chargers"},
                "total_energy_consumption": {"$sum": "$energy_consumption"},
                "avg_power_output": {"$avg": "$power_output"}
            }
        },
        {"$sort": {"_id": 1}}
    ]

#GET top stations by energy consumption
@app.route("/api/stations/top", methods=["GET"])
#@jwt_required
def get_top_stations():
    n = 5
    if request.args.get('n'):
        n = int(request.args.get('n'))

    data_to_return = []
    for station in stations.find().sort("energy_consumption", -1).limit(n):
        station['_id'] = str(station['_id'])
        data_to_return.append(station) 

    return make_response(jsonify(data_to_return), 200)

#post method to add a new station
@app.route("/api/stations", methods=["POST"])
#@jwt_required
def add_station():
    if "station_name" in request.form and \
        "location" in request.form and "charger_type" in request.form:
        
        new_station = {
            "station_name": request.form["station_name"],
            "location": request.form["location"],
            "charger_type": request.form["charger_type"],
            "total_chargers": request.form["total_chargers"],
            "available_chargers": request.form["available_chargers"],
            "charging_chargers": request.form["charging_chargers"],
            "power_output": request.form["power_output"],
            "energy_consumption": request.form["energy_consumption"],
            "status": request.form["status"],
            "recent_update": request.form["recent_update"]
            
        }

        new_station_id = stations.insert_one(new_station)

        new_station_link = "http://127.0.0.1:5001/api/stations/"\
            + str(new_station_id.inserted_id)
        
        return make_response(jsonify({"url": new_station_link}), 201)

    else:
        return make_response(jsonify({"url":"Missing form data"}), 404)

#PUT method to modify an existing station
@app.route("/api/stations/<string:station_id>", methods=["PUT"])
#@jwt_required
def edit_station(station_id):
    if not ObjectId.is_valid(station_id):
        return make_response(jsonify({"error":"Invalid station ID"}), 400)

    update_fields = {}
    for field in ("station_name", "location", "charger_type", "status", "recent_update",):
        if field in request.form:
            update_fields[field] = request.form[field]

    for field in ("total_chargers", "available_chargers", "charging_chargers"):
        if field in request.form:
            update_fields[field] = int(request.form[field])

    for field in ("power_output", "energy_consumption"):
        if field in request.form:
            update_fields[field] = float(request.form[field])

    if update_fields:
        results = stations.update_one(
            {"_id": ObjectId(station_id)}, {"$set": update_fields}
            )

    
        if results.matched_count == 1:
            edited_link = "http://127.0.0.1:5001/api/stations/" \
            + station_id 
            return make_response(jsonify({"url": edited_link}), 200)
        else:
            return make_response(jsonify({"error": "Invalid station ID"}), 404)
    else:
        return make_response(jsonify({"error":"Missing form data"}), 404)


#DELETE method to remove a station (admin only)
@app.route("/api/stations/<string:station_id>", methods=['DELETE'])
#@jwt_required
def delete_station(station_id):

    if not ObjectId.is_valid(station_id):
        return make_response(jsonify({"error":"Invalid station ID"}), 400)
    
    result = stations.delete_one({"_id":ObjectId(station_id)})

    if result.deleted_count == 1:
        return make_response(jsonify({"message":"Station deleted!!!"}), 200)
    else:
        return make_response(jsonify({"error":"Invalid station ID"}), 404)

#user routes
#POST /GET /DELETE FAVORITE STATIONS

if __name__ == "__main__":
    app.run(debug=True, port=5001)