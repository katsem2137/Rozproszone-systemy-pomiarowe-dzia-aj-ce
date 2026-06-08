import os
import secrets
from functools import wraps

from flask import request, jsonify

# Dane logowania pobierane ze zmiennych srodowiskowych (env_file: .env w compose).
# NIE wpisujemy ich na stale w kodzie. Domyslne student/student tylko dla wygody lab.
API_USERNAME = os.environ.get("API_USERNAME", "student")
API_PASSWORD = os.environ.get("API_PASSWORD", "student")


def _is_valid_basic_auth(auth):
    # auth = obiekt Authorization z request.authorization (Basic) albo None.
    if auth is None:
        return False
    username = auth.username or ""
    password = auth.password or ""
    # compare_digest = porownanie odporne na ataki czasowe (timing attack).
    username_ok = secrets.compare_digest(username, API_USERNAME)
    password_ok = secrets.compare_digest(password, API_PASSWORD)
    return username_ok and password_ok


def unauthorized_response():
    response = jsonify({
        "error": "unauthorized",
        "message": "Missing or invalid credentials",
    })
    # 401 + naglowek WWW-Authenticate => klient (przegladarka/curl/Streamlit) wie,
    # ze ma podac dane Basic Auth.
    return response, 401, {
        "WWW-Authenticate": 'Basic realm="RSP API"',
    }


def auth_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if not _is_valid_basic_auth(request.authorization):
            return unauthorized_response()
        return view_function(*args, **kwargs)
    return wrapper
