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
    Vote, LeadershipApplication
)
import os
from werkzeug.utils import secure_filename


student = Blueprint("student", __name__, url_prefix="/student")

# -------------------------------
# STUDENT LOGIN
# Handles authentication via either Email or Registration Number
# -------------------------------
@student.route("/login", methods=["GET", "POST"])
def login():
    # If the student is already logged in, send them straight to the dashboard
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    # When the login form is submitted
    if request.method == "POST":
        identifier = request.form.get("identifier")
        password = request.form.get("password")

        # Try login by email first (preferred)
        user = User.query.filter_by(email=identifier, role="student").first()

        # Fallback: if not an email, try legacy registration_number format
        if not user:
            import re
            pattern = r"^[A-Za-z]{1}[0-9]{2}/[0-9]{5}/[0-9]{2}$"
            if re.match(pattern, identifier or ""):
                reg_no = identifier.upper()
                user = User.query.filter_by(registration_number=reg_no, role="student").first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("Your account is not activated. Please check your email for the activation link.", "warning")
                return redirect(url_for("student.login"))
                
            login_user(user)
            flash(f"Welcome, {user.first_name} {user.last_name}!", "success")
            return redirect(url_for("student.dashboard"))
        else:
            flash("Invalid email/registration or password.", "danger")

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
# Handles new student signups and sends an activation email
# -------------------------------
@student.route("/register", methods=["GET", "POST"])
def register():
    # Prevent logged-in students from accessing the registration form
    if current_user.is_authenticated:
        return redirect(url_for("student.dashboard"))

    # Process the registration form submission
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
            
        reg_no = reg_no.upper() if reg_no and reg_no.strip() else None

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
        user.set_password(password)

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
        user = User.query.filter_by(email=email, role="student").first()
        if user:
            if user.check_password_reuse(password):
                flash("You cannot reuse a previous password.", "danger")
                return redirect(url_for("student.reset_password", token=token))
                
            user.set_password(password)
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
# STUDENT NOTIFICATIONS
# -------------------------------
@student.route("/notifications")
@login_required
def notifications():
    notifications_list = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_date.desc()).all()
    return render_template("student/notifications.html", notifications=notifications_list)

@student.route("/notifications/<int:id>/read", methods=["POST"])
@login_required
def mark_read(id):
    notif = Notification.query.get_or_404(id)
    if notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
    return redirect(url_for('student.notifications'))

@student.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(dict(is_read=True))
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for('student.notifications'))


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

    # Track which elections the student has submitted an application for
    # We map applications to elections via club_id
    user_applications = LeadershipApplication.query.filter_by(student_id=current_user.id).all()
    applied_club_ids = {app.club_id for app in user_applications}
    
    nominated_election_ids = set()
    for el in active_elections:
        if el.club_id in applied_club_ids:
            nominated_election_ids.add(el.id)

    # Track which elections the student has already voted in
    voted_election_ids = set(
        v.election_id
        for v in Vote.query.filter_by(voter_id=current_user.id).all()
    )

    # ── NEW: Active Announcements ──────────────────────────
    from cams.models import Announcement
    active_announcements = Announcement.query.filter(
        (Announcement.target_audience.in_(['all', 'student'])),
        (Announcement.expires_at == None) | (Announcement.expires_at > datetime.utcnow())
    ).order_by(Announcement.created_at.desc()).all()

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
        announcements         = active_announcements,
    )
# -------------------------------
# VIEW ALL CLUBS
# -------------------------------
@student.route("/clubs")
@login_required
def list_clubs():
    q = request.args.get('q', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)

    # "Available clubs" should include clubs students can still discover/join.
    # Some clubs are intentionally in warning/non_compliant states and should remain visible.
    from sqlalchemy import or_
    visible_statuses = ["active", "warning", "non_compliant"]
    query = Club.query.filter(
        or_(Club.status == None, Club.status.in_(visible_statuses))
    )

    if q:
        query = query.filter(Club.name.ilike(f'%{q}%'))
    if category:
        query = query.filter(Club.category == category)
        
    pagination = query.paginate(page=page, per_page=12, error_out=False)
    categories = db.session.query(Club.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    return render_template("student/list.html", pagination=pagination, clubs=pagination.items, q=q, current_category=category, categories=categories)



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
        if existing.status in ["rejected", "removed"]:
            if existing.rejection_count >= 3:
                flash("You have been rejected or removed from this club 3 times and can no longer apply.", "danger")
                return redirect(url_for("student.club_details", club_id=club_id))
            else:
                existing.status = "pending"
                db.session.commit()
                flash("Membership request re-submitted. Awaiting approval from club leaders.", "success")
                return redirect(url_for("student.club_details", club_id=club_id))
        else:
            flash("You already requested or are a member of this club.", "warning")
            return redirect(url_for("student.club_details", club_id=club_id))

    membership = ClubMembership(
        club_id=club_id,
        user_id=current_user.id,
        status="pending",
        role="member",
        join_date=datetime.utcnow(),
        rejection_count=0
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
    doc_field_map = {
        "constitution": ("has_constitution", "constitution_file"),
        "minutes": ("has_minutes", "minutes_file"),
        "patron_letter": ("has_patron_letter", "patron_letter_file"),
    }

    for doc_type in required_docs:
        file = files.get(doc_type)
        if not file or not file.filename:
            continue

        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'bin'
        filename = secure_filename(f"club_{club.id}_{doc_type}_{datetime.utcnow().timestamp()}.{ext}")
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        relative_static_path = f"uploads/club_documents/{filename}"

        document = ClubDocument(
            club_id=club.id,
            document_type=doc_type,
            file_name=filename,
            # Store static-relative path so templates and viewers can resolve it reliably
            file_path=relative_static_path,
            uploaded_by=current_user.id
        )

        db.session.add(document)
        # Keep Club-level compliance flags/files in sync with uploaded documents.
        flag_field, file_field = doc_field_map[doc_type]
        setattr(club, flag_field, True)
        setattr(club, file_field, relative_static_path)
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
        patron_name = request.form.get("patron_name")
        patron_email = request.form.get("patron_email")

        if Club.query.filter_by(name=name).first():
            flash("Club name already exists.", "danger")
            return redirect(url_for("student.clubs_register"))

        if not patron_email or not patron_email.endswith("@egerton.ac.ke"):
            flash("Patron email must be a valid @egerton.ac.ke staff email.", "danger")
            return redirect(url_for("student.clubs_register"))
            
        if not patron_name:
            flash("Patron name is required.", "danger")
            return redirect(url_for("student.clubs_register"))

        # Extract and validate nominated leaders
        leader_president = request.form.get("leader_president")
        leader_vice_president = request.form.get("leader_vice_president")
        leader_secretary = request.form.get("leader_secretary")
        leader_treasurer = request.form.get("leader_treasurer")

        nominated_leaders = {}
        for role, reg_no in [
            ("president", leader_president), 
            ("vice_president", leader_vice_president), 
            ("secretary", leader_secretary), 
            ("treasurer", leader_treasurer)
        ]:
            if reg_no:
                user = User.query.filter_by(registration_number=reg_no.upper()).first()
                if not user:
                    flash(f"Nominated {role.replace('_', ' ').title()} with registration number '{reg_no}' not found.", "danger")
                    return redirect(url_for("student.clubs_register"))
                
                # Ensure a user is not nominated for multiple roles in the same form
                if user in nominated_leaders.values():
                    flash(f"User {reg_no} is nominated for multiple roles. Each role must have a unique student.", "danger")
                    return redirect(url_for("student.clubs_register"))
                    
                nominated_leaders[role] = user

        import uuid
        registration_number = f"REG-CLUB-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}"

        club = Club(
            name=name,
            description=description,
            category=category,
            # Store the original applicant contact for workflow notifications
            email=current_user.email,
            patron_name=patron_name,
            patron_email=patron_email,
            patron_status="pending",
            registration_number=registration_number,
            status="pending"
        )

        db.session.add(club)
        db.session.flush()

        # Add the nominated leaders as pending members with their respective roles
        for role, user in nominated_leaders.items():
            membership = ClubMembership(
                club_id=club.id,
                user_id=user.id,
                status="pending",
                role=role,
                join_date=datetime.utcnow(),
                rejection_count=0
            )
            db.session.add(membership)
            
        # Add the creator as a pending member if they aren't already nominated
        if current_user not in nominated_leaders.values():
            db.session.add(ClubMembership(
                club_id=club.id,
                user_id=current_user.id,
                status="pending",
                role="member",
                join_date=datetime.utcnow(),
                rejection_count=0
            ))

        db.session.flush()

        try:
            handle_club_documents(request.files, club)
        except Exception as e:
            db.session.rollback()
            flash(f"File upload error: {str(e)}", "danger")
            return redirect(url_for("student.clubs_register"))

        db.session.commit()

        # Generate patron verification token
        token = generate_token(str(club.id), "patron-verification-salt")
        accept_link = url_for("student.patron_verify", token=token, action="accept", _external=True)
        reject_link = url_for("student.patron_verify", token=token, action="reject", _external=True)
        
        # Send an email notification to the Patron
        send_email(
            patron_email,
            "CAMS - Club Patron Acceptance Request",
            f"""Hello {patron_name},

A student ({current_user.first_name} {current_user.last_name}, Reg No: {current_user.registration_number}) has registered a new club on the CAMS platform and nominated you as the Patron.

Club Details:
- Name: {name}
- Category: {category}
- Registration Number: {registration_number}

Please confirm whether you accept to be the patron for this club or if this registration is incorrect. If you reject, this club registration will be automatically rejected.

To ACCEPT being the patron, please click this link:
{accept_link}

To REJECT this nomination, please click this link:
{reject_link}

Regards,
CAMS System"""
        )

        # Send an email notification to the applying student
        if current_user.email:
            send_email(
                current_user.email,
                "CAMS - Club Registration Application Received",
                f"""Hello {current_user.first_name},

Your application to register the club '{name}' has been successfully submitted.

An email has been sent to {patron_name} ({patron_email}) to accept or reject the patron request.
Your application will only be forwarded to the Dean after the patron accepts.

Regards,
CAMS System"""
            )

        flash("Club registration submitted successfully. It is now pending approval by the Dean.", "success")
        return redirect(url_for("student.list_clubs"))

    staff_members = User.query.filter(User.role.in_(["admin", "club_officer"])).all()
    # Always show the full category list in the form (not only what's already in DB),
    # plus any extra categories that might exist in older data.
    default_categories = [
        "Academic",
        "Sports",
        "Cultural",
        "Social",
        "Religious",
        "Professional",
        "Environmental",
        "Technology",
        "Community Service",
        "Arts",
        "Other",
    ]
    db_categories = [c[0] for c in db.session.query(Club.category).distinct().all() if c[0]]
    categories = sorted({*default_categories, *db_categories})

    return render_template("student/clubs/register.html", staff_members=staff_members, categories=categories)


# =====================================================
# PATRON VERIFICATION ROUTE
# =====================================================
@student.route("/clubs/patron-verify/<token>/<action>")
def patron_verify(token, action):
    club_id_str = verify_token(token, "patron-verification-salt", expiration=604800) # Valid for 7 days
    if not club_id_str:
        return "The verification link is invalid or has expired. Please contact the club founders.", 400

    club = Club.query.get(int(club_id_str))
    if not club:
        return "Club not found.", 404

    if club.patron_status != "pending":
        return f"This request has already been processed (Current status: {club.patron_status}).", 200

    if action == "accept":
        club.patron_status = "accepted"
        db.session.commit()
        
        # Notify the Dean that the patron accepted and it's ready for full review
        dean = User.query.filter_by(role="dean").first()
        if dean and dean.email:
            send_email(
                dean.email,
                "CAMS - Club Application Ready for Review (Patron Accepted)",
                f"""Hello Dean {dean.last_name},
                
The requested Patron ({club.patron_name}) has accepted their nomination for the new club '{club.name}'.

The application is now complete and ready for your final review and approval in the CAMS admin portal.

Regards,
CAMS System"""
            )
            
        return render_template("student/clubs/patron_response.html", club=club, action="accepted")

    elif action == "reject":
        club.patron_status = "rejected"
        club.status = "rejected" # Automatically reject the whole club registration
        db.session.commit()

        # Notify only the original applicant and abort workflow (no dean escalation).
        applicant = User.query.filter_by(email=club.email).first() if club.email else None
        if applicant and applicant.email:
            send_email(
                applicant.email,
                "CAMS - Club Registration Application Rejected",
                f"""Hello {applicant.first_name},

Your application to register the club '{club.name}' has been REJECTED.

The nominated patron ({club.patron_name}) declined the nomination. The application has been closed and will not be forwarded to the Dean.

You may submit a new application with a different staff patron.

Regards,
CAMS System"""
            )
        elif club.email:
            # Fallback if applicant user record cannot be resolved, but contact email exists
            send_email(
                club.email,
                "CAMS - Club Registration Application Rejected",
                f"""Hello,

Your application to register the club '{club.name}' has been REJECTED.

The nominated patron ({club.patron_name}) declined the nomination. The application has been closed and will not be forwarded to the Dean.

You may submit a new application with a different staff patron.

Regards,
CAMS System"""
            )
        
        return render_template("student/clubs/patron_response.html", club=club, action="rejected")
    
    return "Invalid action selected.", 400


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
    memberships = ClubMembership.query.filter_by(
        user_id=current_user.id,
        status="active"
    ).all()
    
    from sqlalchemy import or_

    club_ids = [m.club_id for m in memberships]
    now = datetime.utcnow()
    
    upcoming_events = Event.query.filter(
        Event.club_id.in_(club_ids),
        or_(Event.end_date >= now, Event.date >= now)
    ).order_by(Event.date).all()
    
    past_events_query = Event.query.filter(
        Event.club_id.in_(club_ids),
        or_(Event.end_date < now, Event.date < now)
    ).order_by(Event.date.desc()).all()

    from cams.models import Attendance
    past_events = []
    for ev in past_events_query:
        att = Attendance.query.filter_by(event_id=ev.id, user_id=current_user.id).first()
        status = att.status if att else "absent"
        past_events.append({
            "event": ev,
            "status": status
        })
    
    return render_template("student/my_events.html", upcoming_events=upcoming_events, past_events=past_events)

@student.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name", current_user.first_name)
        current_user.last_name = request.form.get("last_name", current_user.last_name)
        current_user.email = request.form.get("email", current_user.email)
        current_user.course = request.form.get("course", current_user.course)
        
        # Handle profile image: either upload or choose a demo avatar
        demo_choice = request.form.get("demo_avatar")
        file = request.files.get("profile_image")

        # Simple demo avatar set (external URLs, no local binaries needed)
        demo_avatars = {
            "green": "https://ui-avatars.com/api/?name={}&background=16a34a&color=ffffff&bold=true".format(
                (current_user.first_name or "C")[0]
            ),
            "blue": "https://ui-avatars.com/api/?name={}&background=0ea5e9&color=ffffff&bold=true".format(
                (current_user.first_name or "C")[0]
            ),
            "amber": "https://ui-avatars.com/api/?name={}&background=f59e0b&color=ffffff&bold=true".format(
                (current_user.first_name or "C")[0]
            ),
        }

        # If an image file is uploaded, it takes priority
        if file and file.filename:
            upload_dir = os.path.join(current_app.root_path, "static", "uploads", "avatars")
            os.makedirs(upload_dir, exist_ok=True)

            from werkzeug.utils import secure_filename
            filename = secure_filename(
                f"user_{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}"
            )
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)

            # Store as a URL path so it can be used directly in <img src="">
            current_user.profile_image = f"/static/uploads/avatars/{filename}"

        # Otherwise, if a demo avatar was chosen, use that
        elif demo_choice in demo_avatars:
            current_user.profile_image = demo_avatars[demo_choice]
        
        # Optionally allow password change if provided
        new_password = request.form.get("password")
        if new_password:
            if current_user.check_password_reuse(new_password):
                flash("You cannot reuse a previous password.", "danger")
                return redirect(url_for("student.profile"))
            current_user.set_password(new_password)
            
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("student.profile"))

    return render_template(
        "student/profile.html",
        student=current_user
    )


@student.route("/leadership/apply/<int:election_id>", methods=["GET", "POST"])
@login_required
def apply_leadership(election_id):
    """
    GET  → Show the leadership application form linked to the election.
    POST → Validate and save the application.
    """
    from cams.models import _is_final_year_student, Election
    election = Election.query.get_or_404(election_id)
    
    if getattr(election, 'status', None) and election.status.value != "nomination":
        flash("Nominations are not currently open for this election.", "warning")
        return redirect(url_for('student.profile'))

    # If they are a final year student, they cannot apply
    if _is_final_year_student(current_user):
        flash("Final year students are not eligible to apply for leadership positions.", "danger")
        return redirect(url_for('elections.election_detail', election_id=election_id))

    membership = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.club_id == election.club_id,
        ClubMembership.status  == "active",
        ClubMembership.role    == "member",      # not already a leader
    ).first()
    
    if not membership:
        flash("You are not eligible to apply. You must be an active, non-leader member of this club.", "danger")
        return redirect(url_for('elections.election_detail', election_id=election_id))

    # Past applications for this student
    past_applications = LeadershipApplication.query.filter_by(
        student_id=current_user.id
    ).order_by(LeadershipApplication.created_at.desc()).limit(10).all()

    if request.method == "POST":
        position     = request.form.get("position", "").strip()
        motivation   = request.form.get("motivation", "").strip()
        experience   = request.form.get("experience", "").strip()
        goals        = request.form.get("goals", "").strip()
        availability = request.form.get("availability", "").strip()
        declaration  = request.form.get("declaration")
        photo_file   = request.files.get("photo")

        # ── Validation ────────────────────────────────────
        valid_positions = [p.title.lower().replace(" ", "_") for p in election.positions]
        if position not in valid_positions:
            flash("Please select a valid position for this election.", "danger")
            return render_template(
                "student/apply_leadership.html",
                election=election,
                past_applications=past_applications,
            )

        if len(motivation) < 80:
            flash("Your motivation statement must be at least 80 characters.", "danger")
            return render_template(
                "student/apply_leadership.html",
                election=election,
                past_applications=past_applications,
            )

        if not declaration:
            flash("You must confirm the declaration to submit.", "danger")
            return render_template(
                "student/apply_leadership.html",
                election=election,
                past_applications=past_applications,
            )

        if not photo_file or not photo_file.filename:
            flash("You must upload a photo for your application.", "danger")
            return render_template(
                "student/apply_leadership.html",
                election=election,
                past_applications=past_applications,
            )

        # ── Prevent duplicate pending application ─────────
        existing = LeadershipApplication.query.filter_by(
            student_id = current_user.id,
            club_id    = election.club_id,
            position   = position,
            status     = "pending",
        ).first()

        if existing:
            flash(
                f"You already have a pending application for {position.replace('_',' ').title()} "
                f"in this club.",
                "warning"
            )
            return redirect(url_for("student.apply_leadership", election_id=election.id))

        # ── Save application ───────────────────────────────
        upload_dir = os.path.join(current_app.root_path, "static", "uploads", "candidates")
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(
            f"candidate_{current_user.id}_{election.club_id}_{position}_{int(datetime.utcnow().timestamp())}_{photo_file.filename}"
        )
        filepath = os.path.join(upload_dir, filename)
        photo_file.save(filepath)
        photo_url = f"/static/uploads/candidates/{filename}"

        application = LeadershipApplication(
            student_id   = current_user.id,
            club_id      = election.club_id,
            position     = position,
            motivation   = motivation,
            experience   = experience,
            goals        = goals,
            availability = availability,
            status       = "pending",
            photo_url    = photo_url,
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
        return redirect(url_for("elections.election_detail", election_id=election.id))

    return render_template(
        "student/apply_leadership.html",
        election=election,
        past_applications=past_applications,
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
