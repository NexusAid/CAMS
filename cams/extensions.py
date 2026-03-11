from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask import redirect, url_for, request

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()


@login_manager.unauthorized_handler
def unauthorized():

    # Student routes
    if request.path.startswith("/student"):
        return redirect(url_for("student.login"))

    # Admin routes
    if request.path.startswith("/dashboard"):
        return redirect(url_for("auth.login"))

    # Default
    return redirect(url_for("auth.login"))