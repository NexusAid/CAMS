from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required
from cams.models import User, db
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer
from cams.utils.email_service import send_email

auth = Blueprint("auth", __name__)


# -------------------------
# TOKEN GENERATION
# -------------------------
def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(email, salt="password-reset-salt")


def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    try:
        email = serializer.loads(
            token,
            salt="password-reset-salt",
            max_age=expiration
        )
        return email
    except:
        return None


# -------------------------
# LOGIN
# -------------------------
@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Invalid email", "danger")
            return redirect(url_for("auth.login"))

        if not check_password_hash(user.password_hash, password):
            flash("Wrong password", "danger")
            return redirect(url_for("auth.login"))

        login_user(user, remember=False)

        session.permanent = True

        next_page = request.args.get("next")

        return redirect(next_page or url_for("dashboard.dashboard_home"))

    return render_template("auth/login.html")


# -------------------------
# LOGOUT
# -------------------------
@auth.route("/logout", methods=["POST"])
@login_required
def logout():

    logout_user()

    session.clear()

    flash("You have been logged out", "info")

    return redirect(url_for("auth.login"))


# -------------------------
# FORGOT PASSWORD
# -------------------------
@auth.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form.get("email")

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Email not found", "danger")
            return redirect(url_for("auth.forgot_password"))

        if user.role == "admin":
            flash("Assistant Admins cannot reset passwords here. Please contact the Dean for a new password.", "danger")
            return redirect(url_for("auth.forgot_password"))

        token = generate_reset_token(email)

        reset_link = url_for("auth.reset_password", token=token, _external=True)

        subject = "CAMS Password Reset"

        body = f"""
Hello,

You requested to reset your password for CAMS.

Click the link below to reset it:

{reset_link}

This link will expire in 1 hour.

If you did not request this, please ignore this email.

CAMS System
"""

        send_email(email, subject, body)

        flash("Password reset link sent to your email", "success")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


# -------------------------
# RESET PASSWORD
# -------------------------
@auth.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):

    email = verify_reset_token(token)

    if not email:
        flash("Invalid or expired reset link", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":

        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        user.password_hash = generate_password_hash(password)

        db.session.commit()

        flash("Password updated successfully. Please login.", "success")

        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")