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
# STAFF/ADMIN LOGIN
# -------------------------
@auth.route("/login", methods=["GET", "POST"])
def login():
    # If the user submitted the login form
    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        # Attempt to find the user in the database by their email address
        user = User.query.filter_by(email=email).first()

        # If no user is found with that email, reject the login attempt
        if not user:
            flash("Invalid email", "danger")
            return redirect(url_for("auth.login"))

        # If the user exists but the password doesn't match the hash, reject the login
        if not check_password_hash(user.password_hash, password):
            flash("Wrong password", "danger")
            return redirect(url_for("auth.login"))

        # Log the user in officially via Flask-Login
        login_user(user, remember=False)

        # Make the session permanent so it doesn't expire immediately when the browser closes
        session.permanent = True

        # Check if the user was trying to access a specific page before being redirected here
        next_page = request.args.get("next")

        # Redirect them back to where they were going, or to the dashboard by default
        return redirect(next_page or url_for("dashboard.dashboard_home"))

    # If it's a GET request, just render the login page
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

        # Always show a generic message to avoid exposing whether the email exists
        if not user:
            flash("If the email is registered, a password reset link has been sent.", "info")
            return redirect(url_for("auth.login"))

        # Assistant admins must go through the Dean-managed reset flow
        if user.role == "assistant_admin":
            flash(
                "Assistant Admins cannot reset passwords from this page. "
                "Please contact the Dean to receive a new password.",
                "danger",
            )
            return redirect(url_for("auth.login"))

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

        try:
            send_email(email, subject, body)
        except Exception:
            # Even on failure, avoid revealing details to the requester
            pass

        flash("If the email is registered, a password reset link has been sent.", "success")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


# -------------------------
# RESET PASSWORD
# -------------------------
@auth.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):

    # Verify that the token in the URL is valid and hasn't expired
    email = verify_reset_token(token)

    # If verification fails, deny the reset attempt
    if not email:
        flash("Invalid or expired reset link", "danger")
        return redirect(url_for("auth.login"))

    # If they submitted the new password form
    if request.method == "POST":

        password = request.form.get("password")

        # Fetch the user using the email recovered from the token
        user = User.query.filter_by(email=email).first()

        if user.check_password_reuse(password):
            flash("You cannot reuse a previous password.", "danger")
            return redirect(url_for("auth.reset_password", token=token))

        # Hash their new password and save it
        user.set_password(password)

        db.session.commit()

        flash("Password updated successfully. Please login.", "success")

        # Send them back to the login page to try their new password
        return redirect(url_for("auth.login"))

    # Show the password reset form
    return render_template("auth/reset_password.html")