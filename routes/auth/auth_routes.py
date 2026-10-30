from flask import Blueprint, request, make_response, jsonify, current_app

import jwt
import datetime

auth_bp = Blueprint("auth_bp", __name__)


# Demonstration login: real user accounts and admin permissions
@auth_bp.route("/api/auth/login", methods=['GET'])
def login():
    auth = request.authorization

    if auth and auth.password == 'password':
        role = 'admin' if auth.username == 'admin' else 'user'

        token = jwt.encode({
            'user' : auth.username,
            'role' : role,
            'exp' : datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)
        },
        current_app.config['SECRET_KEY'],
        algorithm="HS256")

        return make_response(jsonify({"token": token, "role": role}), 200)

    return make_response("Could not verify", 401, \
        {'WWW-Authenticate': 'Basic realm = "Login required"'})