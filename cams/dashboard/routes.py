from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import extract
import os

from cams.models import (
    db,
    Club,
    ClubDocument,
    ClubMembership,
    User,
    ActivityLog,
    Event,
    DeregistrationRecord,
    AdminTask
)

from cams.utils.notifications import send_notification
from cams.utils.email_service import send_email
from cams.utils.decorators import admin_required, dean_required, admin_only, dean_only


dashboard = Blueprint("dashboard", __name__)


# =====================================================
# DASHBOARD HOME
# =====================================================
@dashboard.route("/dashboard")
@login_required
def dashboard_home():

    total_clubs = Club.query.count()
    total_members = ClubMembership.query.filter_by(status="active").count()

    upcoming_events_query = Event.query.filter(Event.date >= datetime.utcnow())
    upcoming_events = upcoming_events_query.order_by(Event.date.asc()).limit(5).all()

    stats = {
        "total_clubs": total_clubs,
        "total_members": total_members,
        "upcoming_events": upcoming_events_query.count(),
        "pending_approvals": ClubMembership.query.filter_by(status="pending").count()
    }

    current_year = datetime.utcnow().year
    monthly_members = []

    for month in range(1, 13):
        count = ClubMembership.query.filter(
            extract("year", ClubMembership.join_date) == current_year,
            extract("month", ClubMembership.join_date) == month,
            ClubMembership.status == "active"
        ).count()

        monthly_members.append(count)

    categories = db.session.query(Club.category).distinct().all()
    club_labels = []
    club_data = []

    for (category,) in categories:
        if category:
            club_labels.append(category)
            club_data.append(Club.query.filter_by(category=category).count())

    recent_activities = ActivityLog.query.order_by(
        ActivityLog.timestamp.desc()
    ).limit(5).all()

    return render_template(
        "dashboard/index.html",
        stats=stats,
        upcoming_events=upcoming_events,
        monthly_members=monthly_members,
        club_labels=club_labels,
        club_data=club_data,
        recent_activities=recent_activities
    )






# =====================================================
# CLUB LIST
# =====================================================
@dashboard.route("/clubs")
@login_required
def clubs_list():

    if current_user.is_admin:
        clubs = Club.query.all()
    else:
        clubs = Club.query.filter_by(status="active").all()

    return render_template("clubs/list.html", clubs=clubs)


# =====================================================
# ADMIN – APPROVE CLUB
# =====================================================
@dashboard.route("/admin/clubs/approve/<int:club_id>", methods=["POST"])
@login_required
@admin_required
def approve_club(club_id):

    club = Club.query.get_or_404(club_id)

    club.status = "active"
    club.registration_date = datetime.utcnow()

    db.session.commit()

    send_notification(
        title="Club Approved",
        message=f"Your club '{club.name}' is now active.",
        notification_type="registration",
        priority="normal",
        club_id=club.id
    )

    patron = User.query.get(club.patron_id)

    if patron:
        send_email(
            patron.email,
            "Club Registration Approved",
            f"""
Hello,

Your club '{club.name}' has been approved.

You can now begin managing activities in CAMS.

CAMS Administration
"""
        )

    flash("Club approved successfully.", "success")
    return redirect(url_for("dashboard.pending_clubs"))


# =====================================================
# ADMIN – DEREGISTER CLUB
# =====================================================
@dashboard.route(
    "/admin/clubs/deregister/<int:club_id>",
    methods=["GET", "POST"]
)
@login_required
@admin_required
def deregister_club(club_id):

    club = Club.query.get_or_404(club_id)

    if request.method == "POST":

        reason = request.form.get(
            "reason",
            "Non-compliance with university regulations"
        )

        club.status = "deregistered"
        club.date_modified = datetime.utcnow()

        record = DeregistrationRecord(
            club_id=club.id,
            reason=reason,
            deregistered_by=current_user.id,
            deregistration_date=datetime.utcnow()
        )

        db.session.add(record)
        db.session.commit()

        send_notification(
            title="Club Deregistered",
            message=f"Club '{club.name}' has been deregistered.",
            notification_type="deregistration",
            priority="urgent",
            club_id=club.id
        )

        patron = User.query.get(club.patron_id)

        if patron:
            send_email(
                patron.email,
                "Club Deregistration Notice",
                f"""
Hello,

Your club '{club.name}' has been deregistered.

Reason:
{reason}

Please contact the administration for clarification.

CAMS Administration
"""
            )

        flash("Club deregistered successfully.", "success")
        return redirect(url_for("dashboard.pending_clubs"))

    return render_template("admin/confirm_deregister.html", club=club)

@dashboard.route("/clubs/<int:club_id>/edit", methods=["GET", "POST"], endpoint="edit_club")
@login_required
def edit_club(club_id):
    club = Club.query.get_or_404(club_id)

    # Check if current user is a leader or admin
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "secretary", "treasurer"])
    ).first()

    if not current_user.is_admin and not is_leader:
        flash("Permission denied.", "danger")
        return redirect(url_for("dashboard.club_details", club_id=club_id))

    if request.method == "POST":
        old_name = club.name
        old_description = club.description
        old_category = club.category

        club.name = request.form.get("name", club.name)
        club.description = request.form.get("description", club.description)
        club.category = request.form.get("category", club.category)
        club.date_modified = datetime.utcnow()

        db.session.commit()

        flash("Club updated successfully.", "success")

        # Optional: Notify patron if important fields changed
        patron = User.query.get(club.patron_id)
        if patron and (old_name != club.name or old_description != club.description or old_category != club.category):
            send_email(
                patron.email,
                "Club Information Updated",
                f"""
Hello,

The club '{club.name}' has been updated.

Updated Details:
Name: {club.name}
Description: {club.description}
Category: {club.category}

Regards,
CAMS Administration
"""
            )

        return redirect(url_for("dashboard.club_details", club_id=club_id))

    return render_template("clubs/edit.html", club=club)

@dashboard.route("/admin/clubs/pending", endpoint="pending_clubs")
@login_required
@admin_required
def pending_clubs():
    pending = Club.query.filter_by(status="pending").all()
    dereg_pending = Club.query.filter_by(status="pending_deregistration").all()
    return render_template(
        "admin/pending_clubs.html",
        pending_clubs=pending,
        deregistration_clubs=dereg_pending
    )

@dashboard.route("/clubs/<int:club_id>", endpoint="club_details")
@login_required
def club_details(club_id):
    club = Club.query.get_or_404(club_id)
    members = ClubMembership.query.filter_by(club_id=club_id).all()
    documents = ClubDocument.query.filter_by(club_id=club_id).all()
    
    return render_template(
        "clubs/details.html",
        club=club,
        members=members,
        documents=documents
    )

# =====================================================
# ADMIN – EMAIL BROADCAST
# =====================================================
@dashboard.route("/admin/email", methods=["GET", "POST"], endpoint="email_broadcast")
@login_required
@admin_required
def email_broadcast():
    if request.method == "POST":
        target = request.form.get("target")
        subject = request.form.get("subject")
        message_body = request.form.get("message")
        
        recipient_emails = set()

        if target == "all_students":
            students = User.query.filter_by(role="student").all()
            for s in students:
                recipient_emails.add(s.email)
                
        elif target == "all_users":
            users = User.query.all()
            for u in users:
                recipient_emails.add(u.email)

        elif target == "club_members":
            club_id = request.form.get("club_id")
            if club_id:
                memberships = ClubMembership.query.filter_by(club_id=club_id, status="active").all()
                for m in memberships:
                    recipient_emails.add(m.user.email)

        elif target == "specific_user":
            specific_email = request.form.get("specific_email")
            if specific_email:
                recipient_emails.add(specific_email)

        if not recipient_emails:
            flash("No recipients found for the selected target.", "warning")
            return redirect(url_for("dashboard.email_broadcast"))

        success_count: int = 0
        for email in recipient_emails:
            try:
                send_email(email, subject, message_body)
                success_count += 1
            except Exception as e:
                current_app.logger.error(f"Failed to send email to {email}: {e}")

        flash(f"Successfully broadcasted email to {success_count} recipient(s).", "success")
        return redirect(url_for("dashboard.email_broadcast"))

    # Pass active clubs for the dropdown if targeting specific club
    clubs = Club.query.filter_by(status="active").all()
    return render_template("admin/email_broadcast.html", clubs=clubs)


# =====================================================
# DEAN – ASSISTANT ADMIN MANAGEMENT
# =====================================================
@dashboard.route("/admin/assistants")
@login_required
@admin_only
def assistants():
    assistants = User.query.filter_by(role="assistant_admin").all()
    return render_template("admin/assistants.html", assistants=assistants)


@dashboard.route("/admin/assistants/create", methods=["POST"])
@login_required
@admin_only
def create_assistant():
    first_name = request.form.get("first_name")
    last_name = request.form.get("last_name")
    email = request.form.get("email")
    password = request.form.get("password")

    if User.query.filter_by(email=email).first():
        flash("Email already registered.", "danger")
        return redirect(url_for("dashboard.assistants"))

    new_admin = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        role="assistant_admin",
        is_active=True
    )
    from werkzeug.security import generate_password_hash
    new_admin.password_hash = generate_password_hash(password)

    db.session.add(new_admin)
    db.session.commit()

    # Send credentials to the new assistant
    subject = "CAMS - Assistant Admin Account Created"
    body = f"""Hello {first_name},

An Assistant Admin account has been created for you by the Dean.

Your login credentials are:
Email: {email}
Password: {password}

Please log in to the CAMS portal. Remember, you cannot reset your password
from the login page; if you lose it, you must contact the Dean.

Regards,
CAMS System"""

    try:
        send_email(email, subject, body)
        flash("Assistant Admin created successfully and credentials emailed.", "success")
    except Exception as e:
        current_app.logger.error(f"Error sending email to {email}: {e}")
        flash("Assistant Admin created, but there was an error sending the credentials email.", "warning")

    return redirect(url_for("dashboard.assistants"))


@dashboard.route("/admin/assistants/delete/<int:id>", methods=["POST"])
@login_required
@admin_only
def delete_assistant(id):
    assistant = User.query.get_or_404(id)
    if assistant.role != "assistant_admin":
        flash("Cannot delete non-assistant users from this interface.", "danger")
        return redirect(url_for("dashboard.assistants"))

    db.session.delete(assistant)
    db.session.commit()

    flash(f"Assistant {assistant.full_name} has been deleted.", "success")
    return redirect(url_for("dashboard.assistants"))


@dashboard.route("/admin/assistants/reset/<int:id>", methods=["POST"])
@login_required
@admin_only
def reset_assistant_password(id):
    assistant = User.query.get_or_404(id)
    if assistant.role != "assistant_admin":
        flash("Invalid request.", "danger")
        return redirect(url_for("dashboard.assistants"))

    new_password = request.form.get("new_password")
    
    from werkzeug.security import generate_password_hash
    assistant.password_hash = generate_password_hash(new_password)
    db.session.commit()

    subject = "CAMS - Password Reset by Dean"
    body = f"""Hello {assistant.first_name},

Your Assistant Admin password has been explicitly reset by the Dean.

Your new password is: {new_password}

Regards,
CAMS System"""

    send_email(assistant.email, subject, body)
    
    flash(f"Password for {assistant.full_name} has been reset and emailed.", "success")
    return redirect(url_for("dashboard.assistants"))


# =====================================================
# ASSISTANT ADMIN - TASK MANAGEMENT
# =====================================================
@dashboard.route("/admin/tasks")
@login_required
@admin_required
def tasks():
    # Dean sees all tasks; Assistants see only their own
    if current_user.role == "dean":
        all_tasks = AdminTask.query.order_by(AdminTask.created_at.desc()).all()
    else:
        all_tasks = AdminTask.query.filter_by(assigned_to_id=current_user.id).order_by(AdminTask.created_at.desc()).all()
        
    assistants = User.query.filter_by(role="assistant_admin").all()
    
    return render_template("admin/tasks.html", tasks=all_tasks, assistants=assistants)


@dashboard.route("/admin/tasks/create", methods=["POST"])
@login_required
@dean_only
def create_task():
    title = request.form.get("title")
    description = request.form.get("description")
    assigned_to_id = request.form.get("assigned_to_id")

    task = AdminTask(
        title=title,
        description=description,
        assigned_to_id=assigned_to_id,
        assigned_by_id=current_user.id,
        status="pending"
    )
    db.session.add(task)
    db.session.commit()

    assistant = User.query.get(assigned_to_id)
    if assistant and assistant.email:
        subject = "CAMS - New Admin Task Assigned"
        body = f"""Hello {assistant.first_name},

A new task has been assigned to you by the Dean.

Task: {title}
Description: {description}

Please log in to the CAMS portal to review and update the task status.

Regards,
CAMS System"""
        try:
            send_email(assistant.email, subject, body)
        except:
            pass

    flash("Task created and assigned successfully.", "success")
    return redirect(url_for("dashboard.tasks"))


@dashboard.route("/admin/tasks/<int:id>/status", methods=["POST"])
@login_required
@admin_required
def update_task_status(id):
    task = AdminTask.query.get_or_404(id)
    
    # Only the assigned assistant or the dean can update status
    if current_user.role != "dean" and task.assigned_to_id != current_user.id:
        flash("Unauthorized to update this task.", "danger")
        return redirect(url_for("dashboard.tasks"))

    new_status = request.form.get("status")
    if new_status in ["pending", "in_progress", "completed"]:
        task.status = new_status
        db.session.commit()
        flash("Task status updated.", "success")
    else:
        flash("Invalid status.", "danger")

    return redirect(url_for("dashboard.tasks"))


@dashboard.route("/admin/tasks/<int:id>/delete", methods=["POST"])
@login_required
@dean_only
def delete_task(id):
    task = AdminTask.query.get_or_404(id)
    
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted successfully.", "success")
    return redirect(url_for("dashboard.tasks"))