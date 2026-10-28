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


#JWT decorator
def jwt_required(func):
    @wraps(func)
    def jwt_required_wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

        if not token:
            return make_response(jsonify({"message": "Token is missing"}), 401)

        try:
            data = jwt.decode(token,
                    app.config['SECRET_KEY'],
                    algorithms="HS256")
        except:
            return make_response(jsonify({"message":"Token is invalid"}), 401)

        request.user = data
        return func(*args, **kwargs)

    return jwt_required_wrapper



#========= station routes ============
@app.route("/", methods=["GET"])
def index():
    return make_response("<h1>Welcome to the EV Charging API</h1>", 200)

@app.route("/api/stations", methods=["GET"])
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
def show_available_stations():
    data_to_return = []

    for station in stations.find({"available_chargers":{"$gt":0}}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)

#GET stations filtered by charger type (Ac or Dc)
@app.route("/api/stations/type/<string:charger_type>", methods=["GET"])
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

#GET top stations by energy consumption
@app.route("/api/stations/top-stations", methods=["GET"])
def get_top_stations():
    n = 5
    if request.args.get('n'):
        n = int(request.args.get('n'))

    data_to_return = []
    for station in stations.find().sort("energy_consumption", -1).limit(n):
        station['_id'] = str(station['_id'])
        data_to_return.append(station) 

    return make_response(jsonify(data_to_return), 200)

#post method to add a new stations
@app.route("/api/stations", methods=["POST"])
@jwt_required
def add_station():
    if "station_name" in request.form and \
        "location" in request.form and "charger_type" in request.form:
        
        new_station = {
            "station_id": request.form["station_id"],
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
@jwt_required
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
@jwt_required
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
@app.route("/api/user/favourites", methods=["GET", "POST", "DELETE"])
@jwt_required
def favourites():
    username = request.user["user"]

    if request.method == "POST":
        station_id = request.form.get("station_id")
        if not station_id or not ObjectId.is_valid(station_id):
            return make_response(jsonify({"error":"Invalid station ID"}), 400)
        if stations.find_one({"_id": ObjectId(station_id)}) is None:
            return make_response(jsonify({"error":"Station not found"}), 404)

        users.update_one(
            {"username": username},
            {"$addToSet": {"favourites": ObjectId(station_id)}},
            upsert=True
        )
        return make_response(jsonify({"message":"Favourite added"}), 201)

    if request.method == "DELETE":
        station_id = request.form.get("station_id")
        if not station_id or not ObjectId.is_valid(station_id):
            return make_response(jsonify({"error":"Invalid station ID"}), 400)

        users.update_one(
            {"username": username},
            {"$pull": {"favourites": ObjectId(station_id)}}
        )
        return make_response(jsonify({"message":"Favourite removed"}), 200)

    #GET
    user_doc = users.find_one({"username": username}) or {}
    fav_ids = user_doc.get("favourites", [])

    data_to_return = []
    for station in stations.find({"_id": {"$in": fav_ids}}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)

    return make_response(jsonify(data_to_return), 200)


# POST / GET charging history (logged-in user)
@app.route("/api/user/charging_history", methods=["GET", "POST"])
@jwt_required
def charging_history():
    username = request.user["user"]

    if request.method == "POST":
        station_id = request.form.get("station_id")
        if not station_id or not ObjectId.is_valid(station_id):
            return make_response(jsonify({"error":"Invalid station ID"}), 400)

        entry = {
            "station_id": ObjectId(station_id),
            "energy_consumption": float(request.form.get("energy_consumption", 0)),
            "timestamp": datetime.datetime.now(datetime.UTC)
        }

        users.update_one(
            {"username": username},
            {"$push": {"charging_history": entry}},
            upsert=True
        )
        return make_response(jsonify({"message":"History entry added"}), 201)

    user_doc = users.find_one({"username": username}) or {}
    history = user_doc.get("charging_history", [])

    for h in history:
        h["station_id"] = str(h["station_id"])
        if isinstance(h["timestamp"], datetime.datetime):
            h["timestamp"] = h["timestamp"].isoformat()

    return make_response(jsonify(history), 200)


if __name__ == "__main__":
    app.run(debug=True, port=5001)