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
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()

    if not leadership:
        flash("Access denied: Club leaders only.", "danger")
        return redirect(url_for("main.index"))

    return None

# -------------------------------------------------
# ACTIVATE LEADERSHIP ROLE
# -------------------------------------------------
from cams.auth.routes import verify_activation_token, generate_reset_token, verify_reset_token
from cams.utils.email_service import send_email

@club_leader.route("/activate/<token>", methods=["GET", "POST"])
def activate_role(token):
    membership_id = verify_activation_token(token)
    
    if not membership_id:
        flash("The activation link is invalid or has expired.", "danger")
        return redirect(url_for("club_leader.login"))
        
    membership = ClubMembership.query.get(membership_id)
    
    if not membership or membership.status != "pending":
        flash("This leadership role has already been activated or is no longer valid.", "warning")
        return redirect(url_for("club_leader.login"))
        
    if request.method == "POST":
        membership.status = "active"
        db.session.commit()
        flash("Your leadership role has been successfully activated! You can now log into the Club Leader portal.", "success")
        return redirect(url_for("club_leader.login"))
        
    return render_template("club_leader/activate.html", membership=membership)


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
            ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
            ClubMembership.status == "active"
        ).first()

        if not leader_membership:
            flash("You are not authorized as a club leader", "danger")
            return redirect(url_for("club_leader.login"))

        login_user(user)

        return redirect(url_for("club_leader.dashboard"))

    return render_template("club_leader/login.html")


# -------------------------------------------------
# FORGOT PASSWORD
# -------------------------------------------------
@club_leader.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if current_user.is_authenticated:
        return redirect(url_for("club_leader.dashboard"))

    if request.method == "POST":

        email = request.form.get("email")

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("If the email is registered and associated with a club leader account, a password reset link has been sent.", "info")
            return redirect(url_for("club_leader.login"))

        leader_membership = ClubMembership.query.filter(
            ClubMembership.user_id == user.id,
            ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
            ClubMembership.status == "active"
        ).first()

        if not leader_membership:
            flash("If the email is registered and associated with a club leader account, a password reset link has been sent.", "info")
            return redirect(url_for("club_leader.login"))

        token = generate_reset_token(email)

        reset_link = url_for("club_leader.reset_password", token=token, _external=True)

        subject = "CAMS Club Leader - Reset Your Password"

        body = f"Hello {user.first_name},\n\nYou requested to reset your password for your Club Leader account.\n\nClick the link below to reset it:\n\n{reset_link}\n\nThis link will expire in 1 hour.\n\nIf you did not request this, please ignore this email.\n\nCAMS System"

        try:
            send_email(email, subject, body)
        except Exception:
            pass

        flash("If the email is registered and associated with a club leader account, a password reset link has been sent.", "success")

        return redirect(url_for("club_leader.login"))

    return render_template("club_leader/forgot_password.html")


# -------------------------------------------------
# RESET PASSWORD
# -------------------------------------------------
@club_leader.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):

    if current_user.is_authenticated:
        return redirect(url_for("club_leader.dashboard"))

    email = verify_reset_token(token)

    if not email:
        flash("Invalid or expired reset link", "danger")
        return redirect(url_for("club_leader.forgot_password"))

    if request.method == "POST":

        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        
        if user:
            if user.check_password_reuse(password):
                flash("You cannot reuse a previous password.", "danger")
                return redirect(url_for("club_leader.reset_password", token=token))

            user.set_password(password)
            db.session.commit()

            flash("Password updated successfully. Please login.", "success")
            return redirect(url_for("club_leader.login"))
            
    return render_template("club_leader/reset_password.html", token=token)


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------
@club_leader.route("/dashboard")
@login_required
def dashboard():

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    club_ids = [lead.club_id for lead in leaderships]

    pending_requests = ClubMembership.query.filter(
        ClubMembership.club_id.in_(club_ids),
        ClubMembership.status == "pending"
    ).all()

    # Active Announcements
    from cams.models import Announcement
    active_announcements = Announcement.query.filter(
        (Announcement.target_audience.in_(['all', 'club_leader'])),
        (Announcement.expires_at == None) | (Announcement.expires_at > datetime.utcnow())
    ).order_by(Announcement.created_at.desc()).all()

    return render_template(
        "club_leader/dashboard.html",
        leaderships=leaderships,
        pending_requests=pending_requests,
        announcements=active_announcements
    )


# -------------------------------------------------
# APPROVE MEMBER
# Allows a club leader to approve a pending membership request
# -------------------------------------------------
@club_leader.route("/approve-member/<int:id>")
@login_required
def approve_member(id):

    membership = ClubMembership.query.get_or_404(id)

    # Make sure the current user is actually a leader of the club this membership belongs to
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == membership.club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()

    if not is_leader:
        flash("Unauthorized: You are not a leader of this club.", "danger")
        return redirect(url_for("club_leader.dashboard"))

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
# Allows a club leader to reject a pending membership request
# -------------------------------------------------
@club_leader.route("/reject-member/<int:id>")
@login_required
def reject_member(id):

    membership = ClubMembership.query.get_or_404(id)

    # Security Check: Ensure current user is a leader of this specific club
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == membership.club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()

    if not is_leader:
        flash("Unauthorized: You are not a leader of this club.", "danger")
        return redirect(url_for("club_leader.dashboard"))

    membership.status = "rejected"
    membership.rejection_count += 1
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
# Allows a club leader to revoke an active membership
# -------------------------------------------------
@club_leader.route("/remove-member/<int:id>", methods=["POST"])
@login_required
def remove_member(id):

    denied = club_leader_required()
    if denied:
        return denied

    membership = ClubMembership.query.get_or_404(id)
    
    # Security Check: Ensure current user is a leader of this specific club
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == membership.club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()

    if not is_leader:
        flash("Unauthorized: You cannot remove members from this club.", "danger")
        return redirect(url_for("club_leader.dashboard"))
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
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
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
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    club_ids = [lead.club_id for lead in leaderships]

    from cams.models import Event
    from sqlalchemy import or_

    now = datetime.utcnow()

    # Upcoming events: end_date >= now OR date >= now (if end_date is missing)
    upcoming_events = Event.query.filter(
        Event.club_id.in_(club_ids),
        or_(Event.end_date >= now, Event.date >= now)
    ).order_by(Event.date).all()

    # Past events: end_date < now OR date < now (if end_date is missing)
    past_events = Event.query.filter(
        Event.club_id.in_(club_ids),
        or_(Event.end_date < now, Event.date < now)
    ).order_by(Event.date.desc()).all()

    return render_template("club_leader/events.html", upcoming_events=upcoming_events, past_events=past_events, current_time=now)


# -------------------------------------------------
# MANAGE EVENT ATTENDANCE
# -------------------------------------------------
@club_leader.route("/events/<int:event_id>/attendance", methods=["GET", "POST"])
@login_required
def event_attendance(event_id):
    denied = club_leader_required()
    if denied: return denied

    from cams.models import Event, Attendance
    event = Event.query.get_or_404(event_id)

    # Ensure current user leads the club that owns this event
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == event.club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()
    if not is_leader:
        flash("Unauthorized access to this event's attendance.", "danger")
        return redirect(url_for("club_leader.events"))

    # Only allow attendance if event is in the past
    now = datetime.utcnow()
    event_conclusion = event.end_date if event.end_date else event.date
    if event_conclusion > now:
        flash("You cannot take attendance for an event that hasn't concluded yet.", "warning")
        return redirect(url_for("club_leader.events"))

    # Get active members of the club
    members = ClubMembership.query.filter_by(
        club_id=event.club_id,
        status="active"
    ).all()

    if request.method == "POST":
        # Delete old attendance records for this event
        Attendance.query.filter_by(event_id=event.id).delete()
        
        # Save new records
        for member in members:
            # Expected from form: attendance_user_{user_id} = "attended" | "absent" | "apology"
            status = request.form.get(f"attendance_user_{member.user_id}")
            if status in ["attended", "absent", "apology"]:
                att = Attendance(
                    event_id=event.id,
                    user_id=member.user_id,
                    status=status
                )
                db.session.add(att)
        
        db.session.commit()
        flash("Attendance updated successfully.", "success")
        return redirect(url_for("club_leader.events"))

    # Fetch existing attendance to prefill the UI
    existing_records = Attendance.query.filter_by(event_id=event.id).all()
    attendance_map = {att.user_id: att.status for att in existing_records}

    return render_template(
        "club_leader/event_attendance.html", 
        event=event, 
        members=members, 
        attendance_map=attendance_map
    )


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
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()

    from flask import current_app
    import os
    from werkzeug.utils import secure_filename

    if request.method == "POST":

        title = request.form.get("title")
        date_str = request.form.get("date")
        end_date_str = request.form.get("end_date")
        description = request.form.get("description")
        location = request.form.get("location")
        club_id = request.form.get("club_id")
        image_file = request.files.get("image")

        if not club_id:
            flash("Please select a club.", "danger")
            return redirect(url_for("club_leader.create_event"))

        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            flash("Invalid start date format.", "danger")
            return redirect(url_for("club_leader.create_event"))

        event_end_date = None
        if end_date_str:
            try:
                event_end_date = datetime.strptime(end_date_str, "%Y-%m-%dT%H:%M")
                if event_end_date <= event_date:
                    flash("End date must be after the start date.", "danger")
                    return redirect(url_for("club_leader.create_event"))
            except ValueError:
                flash("Invalid end date format.", "danger")
                return redirect(url_for("club_leader.create_event"))

        from cams.models import Event
        new_event = Event(
            club_id=club_id,
            title=title,
            description=description,
            location=location,
            date=event_date,
            end_date=event_end_date
        )

        # Handle optional image upload
        if image_file and image_file.filename:
            upload_dir = os.path.join(current_app.root_path, "static", "uploads", "events")
            os.makedirs(upload_dir, exist_ok=True)
            filename = secure_filename(f"club_{club_id}_event_{int(datetime.utcnow().timestamp())}_{image_file.filename}")
            filepath = os.path.join(upload_dir, filename)
            image_file.save(filepath)
            new_event.image_path = f"uploads/events/{filename}"

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
    from cams.models import Club, ClubMembership, Event, Attendance
    
    denied = club_leader_required()
    if denied:
        return denied

    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
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
        return redirect(url_for('club_leader.reports'))
    
    club = Club.query.get_or_404(selected_club_id)

    # Membership stats
    members = ClubMembership.query.filter_by(club_id=club.id).all()
    active_members = sum(1 for m in members if m.status == "active")
    pending_members = sum(1 for m in members if m.status == "pending")
    rejected_members = sum(1 for m in members if m.status == "rejected")
    inactive_members = sum(1 for m in members if m.status == "inactive")

    # Event stats
    now = datetime.utcnow()
    events = Event.query.filter_by(club_id=club.id).all()
    total_events = len(events)
    upcoming_events = [e for e in events if (e.end_date or e.date) >= now]
    past_events = [e for e in events if (e.end_date or e.date) < now]
    
    # Sort past events by date descending to get recent 5
    recent_past_events = sorted(past_events, key=lambda x: x.date, reverse=True)[:5]
    
    event_stats = []
    total_attended = 0
    total_attendance_records = 0

    for ev in recent_past_events:
        records = Attendance.query.filter_by(event_id=ev.id).all()
        attended = sum(1 for r in records if r.status == "attended")
        absent = sum(1 for r in records if r.status == "absent")
        apology = sum(1 for r in records if r.status == "apology")
        total_for_ev = len(records)
        rate = (attended / total_for_ev * 100) if total_for_ev > 0 else 0
        
        event_stats.append({
            'event': ev,
            'attended': attended,
            'absent': absent,
            'apology': apology,
            'rate': rate,
            'total': total_for_ev
        })
        
        total_attended += attended
        total_attendance_records += total_for_ev

    overall_attendance_rate = (total_attended / total_attendance_records * 100) if total_attendance_records > 0 else 0

    return render_template(
        "club_leader/reports.html",
        leaderships=leaderships,
        selected_club=club,
        stats={
            'active_members': active_members,
            'pending_members': pending_members,
            'rejected_members': rejected_members,
            'inactive_members': inactive_members,
            'total_events': total_events,
            'upcoming_events': len(upcoming_events),
            'past_events': len(past_events),
            'overall_attendance_rate': overall_attendance_rate
        },
        recent_event_stats=event_stats
    )

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
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
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
        # Update Description if provided
        new_desc = request.form.get("description")
        if new_desc is not None:
            club.description = new_desc

        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
        os.makedirs(upload_dir, exist_ok=True)

        
        for doc_type in ['constitution', 'minutes', 'patron_letter', 'rules']:
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
                    elif doc_type == 'rules':
                        club.rules_file = f"uploads/documents/{filename}"
                        club.has_rules = True
                        
        db.session.commit()
        flash("Club profile and documents updated successfully.", "success")
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

# -------------------------------------------------
# NOTIFICATIONS
# -------------------------------------------------
@club_leader.route("/notifications")
@login_required
def notifications():
    from cams.models import Notification
    notifications_list = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_date.desc()).all()
    return render_template("club_leader/notifications.html", notifications=notifications_list)

@club_leader.route("/notifications/<int:id>/read", methods=["POST"])
@login_required
def mark_read(id):
    from cams.models import Notification
    notif = Notification.query.get_or_404(id)
    if notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
    return redirect(url_for('club_leader.notifications'))

@club_leader.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    from cams.models import Notification
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(dict(is_read=True))
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for('club_leader.notifications'))

# =====================================================
# LEADER - SURVEYS
# =====================================================
@club_leader.route("/surveys", methods=["GET", "POST"])
@login_required
def surveys():
    denied = club_leader_required()
    if denied: return denied
    
    from cams.models import Survey
    
    leaderships = ClubMembership.query.filter(
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()
    club_ids = [lead.club_id for lead in leaderships]
    
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        club_id = request.form.get("club_id")
        
        if int(club_id) not in club_ids:
            flash("Unauthorized club selection.", "danger")
            return redirect(url_for("club_leader.surveys"))
            
        survey = Survey(
            title=title,
            description=description,
            club_id=club_id,
            creator_id=current_user.id
        )
        db.session.add(survey)
        db.session.commit()
        flash("Survey created successfully.", "success")
        return redirect(url_for("club_leader.surveys"))
        
    surveys_list = Survey.query.filter(Survey.club_id.in_(club_ids)).order_by(Survey.created_at.desc()).all()
    return render_template("club_leader/surveys.html", surveys=surveys_list, leaderships=leaderships)

@club_leader.route("/surveys/<int:id>")
@login_required
def view_survey(id):
    denied = club_leader_required()
    if denied: return denied
    
    from cams.models import Survey, SurveyResponse
    survey = Survey.query.get_or_404(id)
    
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == survey.club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()
    
    if not is_leader:
        flash("Unauthorized.", "danger")
        return redirect(url_for("club_leader.surveys"))
        
    responses = SurveyResponse.query.filter_by(survey_id=id).all()
    return render_template("club_leader/view_survey.html", survey=survey, responses=responses)

@club_leader.route("/surveys/<int:id>/toggle", methods=["POST"])
@login_required
def toggle_survey(id):
    denied = club_leader_required()
    if denied: return denied
    from cams.models import Survey
    survey = Survey.query.get_or_404(id)
    
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == survey.club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first()
    
    if is_leader:
        survey.is_active = not survey.is_active
        db.session.commit()
        flash(f"Survey {'activated' if survey.is_active else 'closed'}.", "success")
        
    return redirect(url_for("club_leader.surveys"))