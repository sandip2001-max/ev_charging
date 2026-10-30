from flask import Blueprint, request, make_response, jsonify

from bson import ObjectId
import datetime

from importlib import import_module
_db = import_module("global.db")
stations, users = _db.stations, _db.users
_auth = import_module("global.auth")
token_required, admin_required = _auth.token_required, _auth.admin_required

station_bp = Blueprint("station_bp", __name__)


#================================== station routes ========================
@station_bp.route("/", methods=["GET"])
def index():
    return make_response("<h1>Welcome to EV Charging API</h1>", 200)


@station_bp.route("/api/stations", methods=["GET"])
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
@station_bp.route("/api/stations/<string:station_id>", methods=["GET"])
def show_one_station(station_id):

    if not ObjectId.is_valid(station_id):
        return make_response(jsonify({"error":"Invalid station ID"}), 400)

    station = stations.find_one({'_id':ObjectId(station_id)})

    if station is not None:
        station['_id'] = str(station['_id'])
        return make_response(jsonify(station), 200)

    else:
        return make_response(jsonify({"error":"Invalid station ID"}), 404)


# GET stations with available chargers
@station_bp.route("/api/stations/available", methods=["GET"])
def available_stations():
    data_to_return = []
    for station in stations.find({"available_chargers": {"$gt": 0}}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)
    return make_response(jsonify(data_to_return), 200)


# GET stations filtered by charger type (AC / DC)
@station_bp.route("/api/stations/type/<string:charger_type>", methods=["GET"])
def stations_by_type(charger_type):
    if charger_type not in ("AC", "DC"):
        return make_response(jsonify({"error":"Charger type must be AC or DC"}), 400)

    data_to_return = []
    for station in stations.find({"charger_type": charger_type}):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)
    return make_response(jsonify(data_to_return), 200)


# GET stations nearby (search by location substring)
@station_bp.route("/api/stations/nearby/<string:location>", methods=["GET"])
def nearby_stations():
    place = request.args.get("place")

    if not place:
        return make_response(jsonify({"error":"Missing 'place' query param"}), 400)

    data_to_return = []
    for station in stations.find({"location": {"$regex": place, "$options": "i"}}).limit(20):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)
    return make_response(jsonify(data_to_return), 200)


# GET search by location / status / min_power
@station_bp.route("/api/stations/search", methods=["GET"])
def search_stations():
    query = {}

    location = request.args.get("location")
    status = request.args.get("status")
    min_power = request.args.get("min_power")

    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    if status:
        query["status"] = status
    if min_power:
        try:
            query["power_output"] = {"$gte": float(min_power)}
        except ValueError:
            return make_response(jsonify({"error":"min_power must be a number"}), 400)

    data_to_return = []
    for station in stations.find(query):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)
    return make_response(jsonify(data_to_return), 200)


# GET analytics - aggregation of usage and energy
@station_bp.route("/api/stations/analytics", methods=["GET"])
def station_analytics():

    pipeline = [
        {
            "$group": {
                "_id": "$charger_type",
                "total_stations": {"$sum": 1},
                "total_chargers": {"$sum": "$total_chargers"},
                "available_chargers": {"$sum": "$available_chargers"},
                "charging_chargers": {"$sum": "$charging_chargers"},
                "total_energy_kwh": {"$sum": "$energy_consumption"},
                "avg_power_kw": {"$avg": "$power_output"}
            }
        },
        {"$sort": {"_id": 1}}
    ]

    by_type = list(stations.aggregate(pipeline))

    overall_pipeline = [
        {
            "$group": {
                "_id": None,
                "num_stations": {"$sum": 1},
                "total_chargers": {"$sum": "$total_chargers"},
                "available_chargers": {"$sum": "$available_chargers"},
                "charging_chargers": {"$sum": "$charging_chargers"},
                "total_energy_kwh": {"$sum": "$energy_consumption"}
            }
        }
    ]

    overall = list(stations.aggregate(overall_pipeline))

    if overall:
        overall = overall[0]
        overall.pop("_id", None)
        total = overall.get("total_chargers") or 1
        overall["utilisation_pct"] = round(100 * overall.get("charging_chargers", 0) / total, 2)
    else:
        overall = {}

    return make_response(jsonify({"overall": overall, "by_charger_type": by_type}), 200)


# GET top stations by energy consumed (peak usage reports)
@station_bp.route("/api/stations/top-demand", methods=["GET"])
def top_demand():
    n = 5
    if request.args.get('n'):
        n = int(request.args.get('n'))

    data_to_return = []
    for station in stations.find().sort("energy_consumption", -1).limit(n):
        station['_id'] = str(station['_id'])
        data_to_return.append(station)
    return make_response(jsonify(data_to_return), 200)


#post method to add a new station (ADMIN ONLY)
@station_bp.route("/api/stations", methods=["POST"])
@admin_required
def add_station():
    if "station_name" in request.form and \
        "location" in request.form and "charger_type" in request.form:

        new_station = {
            "station_id": request.form.get("station_id"),
            "station_name": request.form["station_name"],
            "location": request.form["location"],
            "total_chargers": int(request.form["total_chargers"]),
            "available_chargers": int(request.form["available_chargers"]),
            "charging_chargers": int(request.form["charging_chargers"]),
            "charger_type": request.form["charger_type"],
            "power_output": float(request.form["power_output"]),
            "energy_consumption": float(request.form.get("energy_consumption", 0)),
            "status": request.form["status"],
            "recent_update": request.form.get("recent_update",
                datetime.datetime.now(datetime.UTC).isoformat())
        }

        #cross-field validation
        if new_station["available_chargers"] + new_station["charging_chargers"] \
            > new_station["total_chargers"]:
            return make_response(jsonify({
                "error":"available + charging cannot exceed total_chargers"
            }), 400)

        new_station_id = stations.insert_one(new_station)

        new_station_link = "http://127.0.0.1:5001/api/stations/"\
            + str(new_station_id.inserted_id)

        return make_response(jsonify({"url": new_station_link}), 201)

    else:
        return make_response(jsonify({"error":"Missing form data"}), 400)


#PUT method to modify an existing station (ADMIN ONLY)
@station_bp.route("/api/stations/<string:station_id>", methods=["PUT"])
@admin_required
def edit_station(station_id):

    if not ObjectId.is_valid(station_id):
        return make_response(jsonify({"error":"Invalid station ID"}), 400)

    update_fields = {}

    for field in ("station_name", "location", "charger_type", "status", "recent_update"):
        if field in request.form:
            update_fields[field] = request.form[field]

    for field in ("station_id", "total_chargers", "available_chargers", "charging_chargers"):
        if field in request.form:
            update_fields[field] = int(request.form[field])

    for field in ("power_output", "energy_consumption"):
        if field in request.form:
            update_fields[field] = float(request.form[field])

    if not update_fields:
        return make_response(jsonify({"error":"No valid fields provided"}), 400)

    results = stations.update_one(
        {"_id":ObjectId(station_id)},
        {"$set": update_fields}
    )

    if results.matched_count == 1:
        edited_link = "http://127.0.0.1:5001/api/stations/" + station_id
        return make_response(jsonify({"url": edited_link}), 200)
    else:
        return make_response(jsonify({"error": "Invalid station ID"}), 404)


#DELETE method to remove a station (ADMIN ONLY)
@station_bp.route("/api/stations/<string:station_id>", methods=['DELETE'])
@admin_required
def delete_station(station_id):

    if not ObjectId.is_valid(station_id):
        return make_response(jsonify({"error":"Invalid station ID"}), 400)

    result = stations.delete_one({"_id":ObjectId(station_id)})

    if result.deleted_count == 1:
        return make_response(jsonify({"message":"Station deleted!!!"}), 200)
    else:
        return make_response(jsonify({"error":"Invalid station ID"}), 404)


#================================== user routes ========================
# POST / GET / DELETE favourites (logged-in user)
@station_bp.route("/api/user/favourites", methods=["GET", "POST", "DELETE"])
@token_required
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
@station_bp.route("/api/user/charging_history", methods=["GET", "POST"])
@token_required
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