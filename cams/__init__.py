from flask import Flask, render_template, session, redirect, url_for, request
from flask_login import current_user
from sqlalchemy import func
import traceback
from cams.extensions import db, login_manager, mail
from cams.models import Club, Event, ClubMembership, User


def create_app():
    # Create the core Flask application instance
    app = Flask(__name__)
    
    # Load settings from our config object (database URI, mail settings, etc.)
    app.config.from_object("cams.config.Config")
    
    # Ensure all unexpected errors propagate through the app for debugging
    app.config.setdefault("PROPAGATE_EXCEPTIONS", True)

    # -------------------------
    # Initialize extensions
    # -------------------------
    # Bind the database ORM to our newly created app
    db.init_app(app)
    
    # Bind the login manager for handling sessions and user persistence
    login_manager.init_app(app)
    
    # Bind the mail service for sending notifications
    mail.init_app(app)

    # Route unauthenticated users to the correct login page
    # based on which area they are trying to access.
    # The default view is the auth login for admins/staff.
    login_manager.login_view = "auth.login"

    # -------------------------
    # Register blueprints
    # -------------------------
    from cams.auth.routes import auth
    from cams.clubs import clubs
    from cams.dashboard.routes import dashboard
    from cams.student.routes import student
    from cams.leader.routes import club_leader
    from cams.election.routes import elections_bp
    from cams.audit.routes import audit_bp
    from cams.help.routes import help_bp

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(clubs)
    app.register_blueprint(dashboard)
    app.register_blueprint(student)
    app.register_blueprint(club_leader)
    app.register_blueprint(elections_bp, url_prefix="/elections")
    app.register_blueprint(audit_bp, url_prefix="/audit")
    app.register_blueprint(help_bp, url_prefix="/help")

    # -------------------------------------------
    # PREVENT BACK & FORWARD BUTTON CACHE
    # -------------------------------------------
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, private, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # -------------------------------------------
    # GLOBAL SESSION & SECURITY CHECK
    # -------------------------------------------
    @app.before_request
    def secure_session():
        # Track the active portal based on requested path
        if request.path.startswith("/student"):
            session['active_portal'] = 'student'
        elif request.path.startswith("/leader"):
            session['active_portal'] = 'leader'
        elif request.path.startswith(("/dashboard", "/clubs", "/admin", "/audit")):
            session['active_portal'] = 'admin'

        # Define routes that do not require authentication to access.
        # This includes all login, logout, registration, and static file routes.
        allowed_prefixes = (
            "/auth/login",
            "/auth/logout",
            "/auth/forgot_password",
            "/auth/reset_password",
            "/student/login",
            "/student/logout",
            "/student/register",
            "/student/activate",
            "/student/forgot_password",
            "/student/reset_password",
            "/events",
            "/static",
            "/help",
        )

        if request.path == "/" or request.path.startswith(allowed_prefixes):
            return

        # If the user is successfully authenticated, continually refresh their session
        # so they do not get logged out unexpectedly while active.
        if current_user.is_authenticated:
            session.modified = True
            return

        # If the user is NOT authenticated and tries to reach a restricted student route,
        # redirect them to the student login page.
        if request.path.startswith("/student"):
            return redirect(url_for("student.login", next=request.path))

        # If the user is NOT authenticated and tries to reach a staff/admin route,
        # redirect them to the generic staff login page.
        if request.path.startswith(("/dashboard", "/clubs", "/admin", "/audit", "/elections", "/leader")):
            return redirect(url_for("auth.login", next=request.path))

    # -------------------------------------------
    # MAKE BLUEPRINTS AVAILABLE IN TEMPLATES
    # -------------------------------------------
    @app.context_processor
    def inject_blueprints():
        from flask import current_app
        return dict(blueprints=current_app.blueprints)

    @app.context_processor
    def inject_now():
        from datetime import datetime
        return dict(now=datetime.now())

    @app.context_processor
    def inject_notifications():
        from flask_login import current_user
        from cams.models import Notification
        count = 0
        if current_user.is_authenticated:
            count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return dict(unread_notifications_count=count)

    # -------------------------------------------
    # HOMEPAGE ROUTE
    # -------------------------------------------
    @app.route("/")
    def home():

        # -------- SYSTEM STATS --------
        total_clubs = Club.query.count()

        total_members = db.session.query(
            func.count(ClubMembership.user_id)
        ).filter(ClubMembership.status == "active").scalar()

        total_events = Event.query.count()

        total_patrons = User.query.filter_by(role="staff").count()

        stats = {
            "clubs": total_clubs,
            "members": total_members,
            "events": total_events,
            "patrons": total_patrons
        }

        # -------- LATEST EVENTS --------
        latest_events = Event.query.order_by(Event.date.desc()).limit(3).all()

        return render_template(
            "home.html",
            stats=stats,
            events=latest_events
        )

    # -------------------------------------------
    # PUBLIC EVENTS ROUTE
    # -------------------------------------------
    @app.route("/events")
    def public_events():
        events = Event.query.order_by(Event.date.desc()).all()
        return render_template("public_events.html", events=events)

    # -------------------------------------------
    # REGISTER CLI COMMANDS
    # -------------------------------------------
    from cams.utils.cli import register_cli_commands
    register_cli_commands(app)

    return app