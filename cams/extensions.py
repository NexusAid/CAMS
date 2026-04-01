from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask import redirect, url_for, request

# Instantiate the SQLAlchemy ORM extension
db = SQLAlchemy()

# Instantiate the Flask-Login manager for user sessions
login_manager = LoginManager()

# Instantiate the Flask-Mail extension for emailing
mail = Mail()


@login_manager.unauthorized_handler
def _unauthorized():
    # Preserve the "next" argument so the user returns to their requested page after login
    next_url = request.full_path if request.query_string else request.path
    
    # If the request was for a student route, bounce them to the student login
    if request.path.startswith("/student"):
        return redirect(url_for("student.login", next=next_url))
        
    # By default, bounce unauthorized users to the staff/admin login
    return redirect(url_for("auth.login", next=next_url))