from flask import Flask, render_template, session, redirect, url_for, request
from flask_login import current_user
from cams.extensions import db, login_manager, mail


def create_app():
    app = Flask(__name__)
    app.config.from_object("cams.config.Config")

    # -------------------------
    # Initialize extensions
    # -------------------------
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
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

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(clubs)
    app.register_blueprint(dashboard)
    app.register_blueprint(student)
    app.register_blueprint(club_leader)
    app.register_blueprint(elections_bp, url_prefix="/elections")
    app.register_blueprint(audit_bp, url_prefix="/audit")

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

        # Allow public routes
        allowed_paths = (
            "/",
            "/auth/login",
            "/auth/logout",
            "/student/login",
            "/student/logout",
            "/static",
        )

        if request.path.startswith(allowed_paths):
            return

        # If logged in, refresh session
        if current_user.is_authenticated:
            session.modified = True
            return

        # Student protected routes
        if request.path.startswith("/student"):
            return redirect(url_for("student.login"))

        # Admin protected routes
        if request.path.startswith(("/dashboard", "/clubs", "/admin")):
            return redirect(url_for("auth.login"))

    # -------------------------------------------
    # MAKE BLUEPRINTS AVAILABLE IN TEMPLATES
    # -------------------------------------------
    @app.context_processor
    def inject_blueprints():
        from flask import current_app
        return dict(blueprints=current_app.blueprints)

    # -------------------------
    # HOME ROUTE
    # -------------------------
    @app.route("/")
    def home():
        return render_template("home.html")

    return app