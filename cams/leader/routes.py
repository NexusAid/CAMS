from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime

from cams.models import User, ClubMembership
from cams.extensions import db


club_leader = Blueprint(
    "club_leader",
    __name__,
    url_prefix="/club-leader"
)


# -------------------------------------------------
# HELPER: CHECK IF USER IS A CLUB LEADER
# -------------------------------------------------
def club_leader_required():

    leadership = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()

    if not leadership:
        flash("Access denied: Club leaders only.", "danger")
        return redirect(url_for("main.index"))

    return None


# -------------------------------------------------
# CLUB LEADER LOGIN
# -------------------------------------------------
@club_leader.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("club_leader.dashboard"))

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password", "danger")
            return redirect(url_for("club_leader.login"))

        leader_membership = ClubMembership.query.filter(
            ClubMembership.user_id == user.id,
            ClubMembership.role.in_(["president", "secretary", "treasurer"]),
            ClubMembership.status == "active"
        ).first()

        if not leader_membership:
            flash("You are not authorized as a club leader", "danger")
            return redirect(url_for("club_leader.login"))

        login_user(user)

        return redirect(url_for("club_leader.dashboard"))

    return render_template("club_leader/login.html")


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------
@club_leader.route("/dashboard")
@login_required
def dashboard():

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    club_ids = [lead.club_id for lead in leaderships]

    pending_requests = ClubMembership.query.filter(
        ClubMembership.club_id.in_(club_ids),
        ClubMembership.status == "pending"
    ).all()

    return render_template(
        "club_leader/dashboard.html",
        leaderships=leaderships,
        pending_requests=pending_requests
    )


# -------------------------------------------------
# APPROVE MEMBER
# -------------------------------------------------
@club_leader.route("/approve-member/<int:id>")
@login_required
def approve_member(id):

    membership = ClubMembership.query.get_or_404(id)

    membership.status = "active"
    membership.last_updated = datetime.utcnow()

    db.session.commit()

    from cams.utils.email_service import send_email
    subject = f"Club Request Approved: {membership.club.name}"
    body = f"Hello {membership.user.first_name},\n\nYour request to join the club '{membership.club.name}' has been approved by the club leadership. You are now an official member!\n\nBest Regards,\nCAMS System"
    try:
        if membership.user.email:
            send_email(membership.user.email, subject, body)
    except Exception:
        pass

    flash("Member approved successfully", "success")

    return redirect(url_for("club_leader.dashboard"))


# -------------------------------------------------
# REJECT MEMBER
# -------------------------------------------------
@club_leader.route("/reject-member/<int:id>")
@login_required
def reject_member(id):

    membership = ClubMembership.query.get_or_404(id)

    membership.status = "inactive"
    membership.last_updated = datetime.utcnow()

    db.session.commit()

    from cams.utils.email_service import send_email
    subject = f"Club Request Update: {membership.club.name}"
    body = f"Hello {membership.user.first_name},\n\nWe regret to inform you that your request to join the club '{membership.club.name}' has been rejected by the club leadership at this time.\n\nBest Regards,\nCAMS System"
    try:
        if membership.user.email:
            send_email(membership.user.email, subject, body)
    except Exception:
        pass

    flash("Membership request rejected", "warning")

    return redirect(url_for("club_leader.dashboard"))


# -------------------------------------------------
# REMOVE MEMBER
# -------------------------------------------------
@club_leader.route("/remove-member/<int:id>", methods=["POST"])
@login_required
def remove_member(id):

    denied = club_leader_required()
    if denied:
        return denied

    membership = ClubMembership.query.get_or_404(id)
    reason = request.form.get("reason", "No reason provided.")

    membership.status = "inactive"
    membership.last_updated = datetime.utcnow()

    db.session.commit()

    from cams.utils.email_service import send_email
    subject = f"Club Membership Revoked: {membership.club.name}"
    body = f"Hello {membership.user.first_name},\n\nYou have been removed from the club '{membership.club.name}'.\n\nReason: {reason}\n\nIf you have questions, please reach out to the club leadership.\n\nBest Regards,\nCAMS System"
    try:
        if membership.user.email:
            send_email(membership.user.email, subject, body)
    except Exception:
        pass

    flash("Member removed successfully", "success")

    return redirect(url_for("club_leader.members"))


# -------------------------------------------------
# MEMBERS MANAGEMENT
# -------------------------------------------------
@club_leader.route("/members")
@login_required
def members():

    denied = club_leader_required()
    if denied:
        return denied

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    club_ids = [lead.club_id for lead in leaderships]

    members = ClubMembership.query.filter(
        ClubMembership.club_id.in_(club_ids),
        ClubMembership.status == "active"
    ).all()

    return render_template(
        "club_leader/members.html",
        members=members
    )


# -------------------------------------------------
# EVENTS
# -------------------------------------------------
@club_leader.route("/events")
@login_required
def events():

    denied = club_leader_required()
    if denied:
        return denied

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    club_ids = [lead.club_id for lead in leaderships]

    from cams.models import Event
    club_events = Event.query.filter(Event.club_id.in_(club_ids)).order_by(Event.date.desc()).all()

    return render_template("club_leader/events.html", events=club_events)


# -------------------------------------------------
# CREATE EVENT
# -------------------------------------------------
@club_leader.route("/events/create", methods=["GET", "POST"])
@login_required
def create_event():

    denied = club_leader_required()
    if denied:
        return denied

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    if request.method == "POST":

        title = request.form.get("title")
        date_str = request.form.get("date")
        description = request.form.get("description")
        club_id = request.form.get("club_id")

        if not club_id:
            flash("Please select a club.", "danger")
            return redirect(url_for("club_leader.create_event"))

        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for("club_leader.create_event"))

        from cams.models import Event
        new_event = Event(
            club_id=club_id,
            title=title,
            description=description,
            date=event_date
        )

        db.session.add(new_event)
        db.session.commit()

        flash("Event created successfully.", "success")
        return redirect(url_for("club_leader.events"))

    return render_template("club_leader/create_event.html", leaderships=leaderships)


# -------------------------------------------------
# REPORTS
# -------------------------------------------------
@club_leader.route("/reports")
@login_required
def reports():

    denied = club_leader_required()
    if denied:
        return denied

    return render_template("club_leader/reports.html")

# -------------------------------------------------
# DOCUMENTS
# -------------------------------------------------
@club_leader.route("/documents", methods=["GET", "POST"])
@login_required
def documents():
    import os
    from werkzeug.utils import secure_filename
    from flask import current_app
    from cams.models import Club

    denied = club_leader_required()
    if denied:
        return denied

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    if not leaderships:
        flash("You do not have any active leadership roles.", "warning")
        return redirect(url_for("club_leader.dashboard"))

    selected_club_id = request.args.get('club_id', type=int)
    if not selected_club_id:
        selected_club_id = leaderships[0].club_id

    if not any(lead.club_id == selected_club_id for lead in leaderships):
        flash("Unauthorized club access.", "danger")
        return redirect(url_for('club_leader.documents'))
    
    club = Club.query.get_or_404(selected_club_id)

    if request.method == "POST":
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
        os.makedirs(upload_dir, exist_ok=True)
        
        for doc_type in ['constitution', 'minutes', 'patron_letter']:
            if doc_type in request.files:
                file = request.files[doc_type]
                if file and file.filename != '':
                    filename = secure_filename(f"{club.id}_{doc_type}_{file.filename}")
                    file.save(os.path.join(upload_dir, filename))
                    
                    if doc_type == 'constitution':
                        club.constitution_file = f"uploads/documents/{filename}"
                        club.has_constitution = True
                    elif doc_type == 'minutes':
                        club.minutes_file = f"uploads/documents/{filename}"
                        club.has_minutes = True
                    elif doc_type == 'patron_letter':
                        club.patron_letter_file = f"uploads/documents/{filename}"
                        club.has_patron_letter = True
                        
        db.session.commit()
        flash("Documents uploaded successfully.", "success")
        return redirect(url_for('club_leader.documents', club_id=club.id))

    return render_template("club_leader/documents.html", leaderships=leaderships, selected_club=club)


# -------------------------------------------------
# LOGOUT
# -------------------------------------------------
@club_leader.route("/logout")
@login_required
def logout():

    logout_user()

    flash("Logged out successfully", "success")

    return redirect(url_for("club_leader.login"))