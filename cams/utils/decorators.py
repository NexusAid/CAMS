from functools import wraps
from flask import abort
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)  # Not logged in

        if current_user.role not in ["admin", "dean", "assistant_admin"]:
            abort(403)  # Forbidden

        return f(*args, **kwargs)

    return decorated_function

def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)

        if current_user.role != "admin":
            abort(403)

        return f(*args, **kwargs)

    return decorated_function

def dean_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)

        if current_user.role not in ["admin", "dean", "assistant_admin"]:
            abort(403)

        return f(*args, **kwargs)

    return decorated_function

def dean_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)

        if current_user.role != "dean":
            abort(403)

        return f(*args, **kwargs)

    return decorated_function
