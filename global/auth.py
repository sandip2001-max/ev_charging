from flask import request, make_response, jsonify, current_app
from functools import wraps

import jwt

# Helper function to decode the JWT token from the Authorization header
def _decode_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        return jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# Decorator - any logged-in user
def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        payload = _decode_token()
        if payload is None:
            return make_response(jsonify({"error":"Token missing or invalid"}), 401)
        request.user = payload
        return f(*args, **kwargs)
    return wrapper


# Decorator - admin only
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        payload = _decode_token()
        if payload is None:
            return make_response(jsonify({"error":"Token missing or invalid"}), 401)
        if payload.get("role") != "admin":
            return make_response(jsonify({"error":"Admin privileges required"}), 403)
        request.user = payload
        return f(*args, **kwargs)
    return wrapper