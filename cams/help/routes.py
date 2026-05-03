from flask import Blueprint, render_template

help_bp = Blueprint("help", __name__)

@help_bp.route("/")
def index():
    """
    Main Help Center landing page showing categories.
    """
    return render_template("help/index.html")

@help_bp.route("/student")
def student_guide():
    """
    Step-by-step guide for Students.
    """
    return render_template("help/student.html")

@help_bp.route("/leader")
def leader_guide():
    """
    Step-by-step guide for Club Leaders.
    """
    return render_template("help/leader.html")

@help_bp.route("/admin")
def admin_guide():
    """
    Step-by-step guide for Administrators.
    """
    return render_template("help/admin.html")
