from flask import Flask
from importlib import import_module

_db = import_module("global.db")
client, db, stations, users = _db.client, _db.db, _db.stations, _db.users
from routes.auth.auth_routes import auth_bp
from routes.station.station_routes import station_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecret'

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(station_bp)


if __name__ == "__main__":
    app.run(debug=True, port=5001)