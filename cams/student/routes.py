from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from datetime import datetime, timezone, timedelta
from cams import db, login_manager
from cams.utils.email_service import send_email
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
from cams.models import User, Club, ClubMembership, ClubDocument, Event, Notification
from cams.models import (
    ClubMembership, Election, ElectionStatus,
    Nomination, NominationStatus, Vote, LeadershipApplication
)
import os
from werkzeug.utils import secure_filename


student = Blueprint("student", __name__, url_prefix="/student")

# -------------------------------
# STUDENT LOGIN
# -------------------------------
@student.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        reg_no = request.form.get("reg_no")
        password = request.form.get("password")

        # Validate registration number format: S13/07803/22
        import re
        pattern = r"^[A-Za-z]{1}[0-9]{2}/[0-9]{5}/[0-9]{2}$"
        if not re.match(pattern, reg_no):
            flash("Invalid registration number format. Example: S13/07803/22", "danger")
            return redirect(url_for("student.login"))

        # Normalize reg_no to uppercase for consistent lookup
        reg_no = reg_no.upper()

        # Attempt to find the student
        user = User.query.filter_by(registration_number=reg_no, role="student").first()
        
        # Fallback to email lookup if older record
        if not user:
            user = User.query.filter_by(email=reg_no, role="student").first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("Your account is not activated. Please check your email for the activation link.", "warning")
                return redirect(url_for("student.login"))
                
            login_user(user)
            flash(f"Welcome, {user.first_name} {user.last_name}!", "success")
            return redirect(url_for("student.dashboard"))
        else:
            flash("Invalid registration number or password.", "danger")

    return render_template("student/login.html")


# -------------------------------
# TOKEN GENERATION UTILS
# -------------------------------
def generate_token(email, salt):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(email, salt=salt)

def verify_token(token, salt, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = serializer.loads(token, salt=salt, max_age=expiration)
        return email
    except:
        return None


# -------------------------------
# STUDENT REGISTRATION
# -------------------------------
@student.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        reg_no = request.form.get("reg_no")
        course = request.form.get("course")
        password = request.form.get("password")

        # Validate reg_no
        import re
        pattern = r"^[A-Za-z]{1}[0-9]{2}/[0-9]{5}/[0-9]{2}$"
        if not re.match(pattern, reg_no):
            flash("Invalid registration number format. Example: S13/07803/22", "danger")
            return redirect(url_for("student.register"))
            
        reg_no = reg_no.upper()

        if User.query.filter_by(email=email).first():
            flash("Email address is already registered.", "danger")
            return redirect(url_for("student.register"))

        if User.query.filter_by(registration_number=reg_no).first():
            flash("Registration number is already in use.", "danger")
            return redirect(url_for("student.register"))

        from werkzeug.security import generate_password_hash
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            registration_number=reg_no,
            course=course,
            role="student",
            is_active=False
        )
        user.password_hash = generate_password_hash(password)

        db.session.add(user)
        db.session.commit()

        # Generate activation token
        token = generate_token(email, "email-activation-salt")
        activation_link = url_for("student.activate", token=token, _external=True)
        
        subject = "CAMS - Activate Your Account"
        body = f"""Hello {first_name},

Thank you for registering on CAMS!

Please click the link below to activate your account:
{activation_link}

This link will expire in 1 hour.

Regards,
CAMS System"""

        try:
            send_email(email, subject, body)
            flash("Registration successful. Please check your email for the activation link.", "success")
        except Exception as e:
            flash(f"Registration successful, but there was an error sending the activation email: {str(e)}", "warning")
            
        return redirect(url_for("student.login"))

    # Need dynamic options later, but currently hardcoded as fallback or passed directly
    from cams.models import Club
    categories = db.session.query(Club.category).distinct().all() 
    # Course dropdown handling will be added during data cleanup
    return render_template("student/register.html")


# -------------------------------
# ACCOUNT ACTIVATION
# -------------------------------
@student.route("/activate/<token>")
def activate(token):
    email = verify_token(token, "email-activation-salt")
    if not email:
        flash("The activation link is invalid or has expired.", "danger")
        return redirect(url_for("student.login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Account not found.", "danger")
        return redirect(url_for("student.login"))

    if user.is_active:
        flash("Account is already active. Please login.", "info")
    else:
        user.is_active = True
        db.session.commit()
        flash("Your account has been activated successfully. You can now login.", "success")

    return redirect(url_for("student.login"))


# -------------------------------
# FORGOT PASSWORD
# -------------------------------
@student.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email, role="student").first()

        if not user:
            # Always show success to prevent email enumeration
            flash("If the email is registered, a password reset link has been sent.", "info")
            return redirect(url_for("student.login"))

        token = generate_token(email, "student-password-reset-salt")
        reset_link = url_for("student.reset_password", token=token, _external=True)
        
        subject = "CAMS - Reset Your Password"
        body = f"""Hello {user.first_name},

You requested to reset your password. Please click the link below:
{reset_link}

This link will expire in 1 hour. If you did not request this, please ignore this email.

Regards,
CAMS System"""

        send_email(email, subject, body)
        flash("If the email is registered, a password reset link has been sent.", "info")
        return redirect(url_for("student.login"))

    return render_template("student/forgot_password.html")


# -------------------------------
# RESET PASSWORD
# -------------------------------
@student.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    email = verify_token(token, "student-password-reset-salt")
    if not email:
        flash("The reset link is invalid or has expired.", "danger")
        return redirect(url_for("student.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password")
        from werkzeug.security import generate_password_hash
        
        user = User.query.filter_by(email=email, role="student").first()
        if user:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            flash("Your password has been updated successfully. Please login.", "success")
            return redirect(url_for("student.login"))
            
    return render_template("student/reset_password.html")


# -------------------------------
# STUDENT LOGOUT
# -------------------------------
@student.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("student.login"))


# -------------------------------
# STUDENT DASHBOARD
# -------------------------------
@student.route("/dashboard")
@login_required
def dashboard():
    """
    Student dashboard — now includes active elections the student
    is eligible to participate in (member of that club).
    """
    # ── Existing logic (keep as-is) ───────────────────────
    memberships     = ClubMembership.query.filter_by(user_id=current_user.id).all()
    active_count    = sum(1 for m in memberships if m.status == 'active')
    pending_count   = sum(1 for m in memberships if m.status == 'pending')
    active_club_ids = [m.club_id for m in memberships if m.status == 'active']

    upcoming_events = (
        Event.query
        .filter(Event.club_id.in_(active_club_ids), Event.date >= datetime.utcnow())
        .order_by(Event.date)
        .limit(10).all()
    )

    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_date.desc())
        .limit(20).all()
    )

    leader_eligible_clubs = [
        m.club for m in memberships
        if m.status == 'active'
        and m.role == 'member'
        and (datetime.utcnow() - m.join_date).days >= 365
    ]

    # ── NEW: Elections the student can interact with ───────
    # Only elections belonging to clubs the student is an active member of
    active_elections = (
        Election.query
        .filter(
            Election.club_id.in_(active_club_ids),
            Election.status.in_([
                ElectionStatus.NOMINATION,
                ElectionStatus.REVIEW,
                ElectionStatus.VOTING,
                ElectionStatus.CLOSED,
                ElectionStatus.PUBLISHED,
            ])
        )
        .order_by(Election.voting_start.desc())
        .all()
    )

    # Track which elections the student has already nominated in
    nominated_election_ids = set(
        n.election_id
        for n in Nomination.query
        .filter_by(member_id=current_user.id)
        .filter(Nomination.status != NominationStatus.REJECTED)
        .all()
    )

    # Track which elections the student has already voted in
    voted_election_ids = set(
        v.election_id
        for v in Vote.query.filter_by(voter_id=current_user.id).all()
    )

    # ── Handle AJAX refresh (return JSON for live updates) ─
    if request.headers.get('Accept') == 'application/json' or request.args.get('json'):
        return jsonify({
            'active':         active_count,
            'pending':        pending_count,
            'events':         len(upcoming_events),
            'notifications':  len(notifications),
            'leader_eligible': len(leader_eligible_clubs),
        })

    return render_template(
        'student/dashboard.html',
        memberships          = memberships,
        active_count         = active_count,
        pending_count        = pending_count,
        upcoming_events      = upcoming_events,
        notifications        = notifications,
        leader_eligible_clubs = leader_eligible_clubs,

        # NEW election context vars
        active_elections      = active_elections,
        nominated_election_ids = nominated_election_ids,
        voted_election_ids     = voted_election_ids,
    )
# -------------------------------
# VIEW ALL CLUBS
# -------------------------------
@student.route("/clubs")
@login_required
def list_clubs():
    clubs = Club.query.filter_by(status="active").all()
    return render_template("student/list.html", clubs=clubs)


# -------------------------------
# VIEW CLUB DETAILS
# -------------------------------
@student.route("/clubs/<int:club_id>")
@login_required
def club_details(club_id):
    club = Club.query.get_or_404(club_id)

    # Fetch club leaders (approved memberships with leadership roles)
    leaders = ClubMembership.query.filter(
        ClubMembership.club_id == club_id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    # Fetch club patron (assuming club.patron_id exists)
    patron = User.query.get(club.patron_id) if hasattr(club, 'patron_id') else None

    # Check current user's membership
    membership = ClubMembership.query.filter_by(
        club_id=club_id,
        user_id=current_user.id
    ).first()

    # Fetch approved documents
    documents = ClubDocument.query.filter_by(
        club_id=club_id,
        approved=True
    ).all()

    return render_template(
        "student/details.html",
        club=club,
        leaders=leaders,
        patron=patron,
        membership=membership,
        documents=documents
    )


# -------------------------------
# REQUEST MEMBERSHIP
# -------------------------------
@student.route("/clubs/<int:club_id>/join", methods=["POST"])
@login_required
def request_membership(club_id):
    existing = ClubMembership.query.filter_by(
        club_id=club_id,
        user_id=current_user.id
    ).first()

    if existing:
        flash("You already requested or are a member of this club.", "warning")
        return redirect(url_for("student.club_details", club_id=club_id))

    membership = ClubMembership(
        club_id=club_id,
        user_id=current_user.id,
        status="pending",
        role="member",
        join_date=datetime.utcnow()
    )

    db.session.add(membership)
    db.session.commit()

    flash("Membership request sent. Awaiting approval from club leaders.", "success")
    return redirect(url_for("student.club_details", club_id=club_id))


# =====================================================
# DOCUMENT HANDLER
# =====================================================
def handle_club_documents(files, club):
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "club_documents")
    os.makedirs(upload_dir, exist_ok=True)

    required_docs = ["constitution", "minutes", "patron_letter"]
    uploaded = []

    for doc_type in required_docs:
        file = files.get(doc_type)
        if not file or not file.filename:
            continue

        filename = secure_filename(f"club_{club.id}_{doc_type}_{datetime.utcnow().timestamp()}.pdf")
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        document = ClubDocument(
            club_id=club.id,
            document_type=doc_type,
            file_name=filename,
            file_path=filepath,
            uploaded_by=current_user.id
        )

        db.session.add(document)
        uploaded.append(doc_type)

    if not all(doc in uploaded for doc in required_docs):
        raise Exception("All required documents must be uploaded.")

# =====================================================
# CLUB REGISTRATION
# =====================================================
@student.route("/clubs/register", methods=["GET", "POST"])
@login_required
def clubs_register():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        category = request.form.get("category")
        patron_email = request.form.get("patron_email")

        if Club.query.filter_by(name=name).first():
            flash("Club name already exists.", "danger")
            return redirect(url_for("student.clubs_register"))

        patron = User.query.filter(
            User.email == patron_email,
            User.role.in_(["admin", "club_officer"])
        ).first()

        if not patron:
            flash("Invalid patron selected.", "danger")
            return redirect(url_for("student.clubs_register"))

        club = Club(
            name=name,
            description=description,
            category=category,
            patron_id=patron.id,
            status="pending",
            member_count=0
        )

        db.session.add(club)
        db.session.flush()

        try:
            handle_club_documents(request.files, club)
        except Exception as e:
            db.session.rollback()
            flash(f"File upload error: {str(e)}", "danger")
            return redirect(url_for("student.clubs_register"))

        db.session.commit()

        # Send an email notification directly to the Dean
        dean = User.query.filter_by(role="dean").first()
        if dean and dean.email:
            send_email(
                dean.email,
                "CAMS - New Club Registration Pending Approval",
                f"""Hello Dean {dean.last_name},

A new club '{name}' has been submitted for registration by a student.

Category: {category}
Patron requested: {patron.email}

Please log in to the CAMS admin portal to review the supporting documents (constitution, minutes, and patron consent letter) and approve or reject this club.

Regards,
CAMS System"""
            )

        flash("Club registration submitted successfully. It is now pending approval by the Dean.", "success")
        return redirect(url_for("student.list_clubs"))

    staff_members = User.query.filter(User.role.in_(["admin", "club_officer"])).all()
    categories = [c[0] for c in db.session.query(Club.category).distinct().all() if c[0]]
    if not categories:
        categories = ["Academic", "Sports", "Cultural", "Social", "Religious", "Professional", "Other"]

    return render_template("student/clubs/register.html", staff_members=staff_members, categories=categories)


# -------------------------------
# VIEW CLUB DOCUMENT (READ ONLY, NO DOWNLOAD)
# -------------------------------
@student.route("/clubs/<int:club_id>/documents/<int:doc_id>")
@login_required
def view_document(club_id, doc_id):
    doc = ClubDocument.query.get_or_404(doc_id)

    # Ensure document belongs to the club
    if doc.club_id != club_id:
        flash("Invalid document access.", "danger")
        return redirect(url_for("student.club_details", club_id=club_id))

    # Ensure user is approved member for restricted docs
    membership = ClubMembership.query.filter_by(
        club_id=club_id,
        user_id=current_user.id,
        status="active"
    ).first()

    # Only show if document approved
    if doc.approved and (membership or doc.document_type == "constitution"):
        # Render inline (read-only view)
        return render_template(
            "student/clubs/document_view.html",
            document=doc,
            club_id=club_id
        )

    flash("You are not authorized to view this document.", "danger")
    return redirect(url_for("student.club_details", club_id=club_id))


# -------------------------------
# VIEW MY MEMBERSHIPS
# -------------------------------
@student.route("/my-memberships")
@login_required
def my_memberships():
    memberships = ClubMembership.query.filter_by(user_id=current_user.id).all()
    return render_template("student/my_memberships.html", memberships=memberships)


# -------------------------------
# LOGIN MANAGER USER LOADER
# -------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@student.route("/my-events")
@login_required
def my_events():
    return render_template("student/details.html", events = my_events)

@student.route("/profile")
@login_required
def profile():
    return render_template(
        "student/profile.html",
        student=current_user
    )


@student.route("/leadership/apply", methods=["GET", "POST"])
@login_required
def apply_leadership():
    """
    GET  → Show the leadership application form with eligible clubs.
    POST → Validate and save the application.
    """
    # Clubs where the student has been active for 1+ year
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

    memberships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.status  == "active",
        ClubMembership.join_date <= one_year_ago,
        ClubMembership.role    == "member",      # not already a leader
    ).all()

    leader_eligible_clubs = [m.club for m in memberships]

    # Past applications for this student
    past_applications = LeadershipApplication.query.filter_by(
        student_id=current_user.id
    ).order_by(LeadershipApplication.created_at.desc()).limit(10).all()

    if request.method == "POST":
        club_id      = request.form.get("club_id", type=int)
        position     = request.form.get("position", "").strip()
        motivation   = request.form.get("motivation", "").strip()
        experience   = request.form.get("experience", "").strip()
        goals        = request.form.get("goals", "").strip()
        availability = request.form.get("availability", "").strip()
        declaration  = request.form.get("declaration")

        # ── Validation ────────────────────────────────────
        eligible_ids = [c.id for c in leader_eligible_clubs]

        if not club_id or club_id not in eligible_ids:
            flash("Please select an eligible club.", "danger")
            return render_template(
                "student/apply_leadership.html",
                leader_eligible_clubs=leader_eligible_clubs,
                past_applications=past_applications,
            )

        if position not in ("president", "vice_president", "secretary", "treasurer"):
            flash("Please select a valid position.", "danger")
            return render_template(
                "student/apply_leadership.html",
                leader_eligible_clubs=leader_eligible_clubs,
                past_applications=past_applications,
            )

        if len(motivation) < 80:
            flash("Your motivation statement must be at least 80 characters.", "danger")
            return render_template(
                "student/apply_leadership.html",
                leader_eligible_clubs=leader_eligible_clubs,
                past_applications=past_applications,
            )

        if not declaration:
            flash("You must confirm the declaration to submit.", "danger")
            return render_template(
                "student/apply_leadership.html",
                leader_eligible_clubs=leader_eligible_clubs,
                past_applications=past_applications,
            )

        # ── Prevent duplicate pending application ─────────
        existing = LeadershipApplication.query.filter_by(
            student_id = current_user.id,
            club_id    = club_id,
            position   = position,
            status     = "pending",
        ).first()

        if existing:
            flash(
                f"You already have a pending application for {position.replace('_',' ').title()} "
                f"in this club.",
                "warning"
            )
            return redirect(url_for("student.apply_leadership"))

        # ── Save application ───────────────────────────────
        application = LeadershipApplication(
            student_id   = current_user.id,
            club_id      = club_id,
            position     = position,
            motivation   = motivation,
            experience   = experience,
            goals        = goals,
            availability = availability,
            status       = "pending",
        )
        db.session.add(application)

        # Notify dean/admin that a new application was submitted
        _notify_new_application(application)

        db.session.commit()

        flash(
            f"Your application for {position.replace('_',' ').title()} has been submitted. "
            f"You will be notified once it's reviewed.",
            "success"
        )
        return redirect(url_for("student.apply_leadership"))

    return render_template(
        "student/apply_leadership.html",
        leader_eligible_clubs = leader_eligible_clubs,
        past_applications     = past_applications,
    )


# ─────────────────────────────────────────────────────────
# INTERNAL — notify admins/dean of new application
# ─────────────────────────────────────────────────────────

def _notify_new_application(application):
    """
    Creates a Notification for every admin/dean user so they
    can review the application from the admin panel.
    """
    from cams.models import User

    admins = User.query.filter(User.role.in_(["admin", "dean"])).all()

    club = Club.query.get(application.club_id)
    student = User.query.get(application.student_id)

    for admin in admins:
        notif = Notification(
            user_id           = admin.id,
            club_id           = application.club_id,
            title             = f"New Leadership Application — {club.name}",
            message           = (
                f"{student.full_name} has applied for the position of "
                f"{application.position.replace('_', ' ').title()} "
                f"in {club.name}."
            ),
            notification_type = "leadership_application",
            priority          = "normal",
            is_read           = False,
        )
        db.session.add(notif)
