from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
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
    AdminTask,
    LeadershipApplication
)

from cams.utils.notifications import send_notification
from cams.utils.email_service import send_email
from cams.utils.decorators import admin_required, dean_required, admin_only, dean_only


dashboard = Blueprint("dashboard", __name__)


# =====================================================
# DASHBOARD HOME
# The main administrative landing page showing system stats
# =====================================================
@dashboard.route("/dashboard")
@login_required
def dashboard_home():

    # Calculate system totals for the top summary cards
    total_clubs = Club.query.count()
    total_members = ClubMembership.query.filter_by(status="active").count()

    # Fetch the next 5 upcoming events across all clubs
    upcoming_events_query = Event.query.filter(Event.date >= datetime.utcnow())
    upcoming_events = upcoming_events_query.order_by(Event.date.asc()).limit(5).all()

    # -------------------------
    # Compliance snapshot data (used by dashboard template)
    # -------------------------
    compliance_alerts = []
    elections_due_list = []
    overdue_financial_list = []
    dormant_clubs_list = []

    active_clubs = Club.query.filter(Club.status != "deregistered").all()
    for club in active_clubs:
        try:
            issues = club.check_compliance_issues()
        except Exception:
            issues = []

        # Compliance alerts (show first issue as a headline)
        if issues:
            compliance_alerts.append({
                "club_name": club.name,
                "message": issues[0],
            })

        # Dormancy
        try:
            if club.is_dormant():
                dormant_clubs_list.append(club)
        except Exception:
            pass

        # Overdue financials (use latest_financial_report if present)
        try:
            report = club.latest_financial_report
            if (not report) or ((datetime.utcnow() - report.report_date).days > 365):
                overdue_financial_list.append(club)
        except Exception:
            pass

        # Elections due (best-effort; some projects may not track election dates cleanly)
        # If no election records exist for the club, consider it due.
        try:
            from cams.models import Election
            has_any_election = Election.query.filter_by(club_id=club.id).first() is not None
            if not has_any_election:
                elections_due_list.append(club)
        except Exception:
            pass

    stats = {
        "total_clubs": total_clubs,
        "total_members": total_members,
        "upcoming_events": upcoming_events_query.count(),
        "pending_approvals": ClubMembership.query.filter_by(status="pending").count(),

        # Compliance snapshot cards
        "elections_due": len(elections_due_list),
        "overdue_financials": len(overdue_financial_list),
        "dormant_clubs": len(dormant_clubs_list),
        "non_compliant_clubs": len(compliance_alerts),
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

    from cams.models import Announcement
    active_announcements = Announcement.query.filter(
        (Announcement.target_audience.in_(['all', 'admin'])),
        (Announcement.expires_at == None) | (Announcement.expires_at > datetime.utcnow())
    ).order_by(Announcement.created_at.desc()).all()

    return render_template(
        "dashboard/index.html",
        stats=stats,
        upcoming_events=upcoming_events,
        monthly_members=monthly_members,
        club_labels=club_labels,
        club_data=club_data,
        recent_activities=recent_activities,
        announcements=active_announcements,


        # Template expects these lists
        compliance_alerts=compliance_alerts[:10],
        elections_due_list=elections_due_list[:10],
        overdue_financial_list=overdue_financial_list[:10],
        dormant_clubs_list=dormant_clubs_list[:10],
    )






# =====================================================
# CLUB LIST
# Displays a list of all registered clubs in the system
# =====================================================
@dashboard.route("/clubs")
@login_required
def clubs_list():

    # Admin/dean/assistant_admin can see all clubs regardless of status.
    if current_user.role in ["admin", "dean", "assistant_admin"]:
        clubs = Club.query.all()
    else:
        clubs = Club.query.filter_by(status="active").all()

    return render_template("clubs/list.html", clubs=clubs)


from cams.auth.routes import generate_activation_token

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

    # Deliver activation links to all pending interim leaders
    pending_leaders = ClubMembership.query.filter(
        ClubMembership.club_id == club.id,
        ClubMembership.status == "pending",
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"])
    ).all()

    for leader_member in pending_leaders:
        token = generate_activation_token(leader_member.id)
        activation_link = url_for('club_leader.activate_role', token=token, _external=True)
        send_email(
            leader_member.user.email,
            "CAMS - Accept Leadership Role",
            f"""
Hello {leader_member.user.first_name},

The club '{club.name}' has been officially approved!

You were nominated for the role of {leader_member.role.replace('_', ' ').title()}. 
Please click the link below to accept your leadership position. Once accepted, you can manage the club via the Club Leader portal using your existing Student login credentials.

{activation_link}

Welcome aboard!
CAMS Administration
"""
        )

    flash("Club approved successfully. Activation instructions have been sent to interim leaders.", "success")
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

        patron = User.query.get(club.patron_id) if club.patron_id else None

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
        return redirect(url_for("dashboard.clubs_list"))

    return render_template("admin/confirm_deregister.html", club=club)

@dashboard.route("/clubs/<int:club_id>/edit", methods=["GET", "POST"], endpoint="edit_club")
@login_required
def edit_club(club_id):
    club = Club.query.get_or_404(club_id)

    # Check if current user is a leader or admin
    is_leader = ClubMembership.query.filter(
        ClubMembership.club_id == club_id,
        ClubMembership.user_id == current_user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"])
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

        success_count = 0
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


# =====================================================
# DEAN – LEADERSHIP APPLICATION REVIEW
# =====================================================
@dashboard.route("/admin/applications/review")
@login_required
@dean_required
def application_review_list():
    """Dean sees all pending leadership applications."""
    pending = (
        LeadershipApplication.query
        .filter_by(status="pending")
        .order_by(LeadershipApplication.created_at.asc())
        .all()
    )
    return render_template("admin/application_review_list.html", applications=pending)


@dashboard.route("/admin/applications/<int:app_id>/review", methods=["GET", "POST"])
@login_required
@dean_required
def application_review(app_id):
    """Dean approves or rejects a single leadership application."""
    application = LeadershipApplication.query.get_or_404(app_id)

    if application.status != "pending":
        flash("This application has already been reviewed.", "info")
        return redirect(url_for("dashboard.application_review_list"))

    if request.method == "POST":
        action      = request.form.get("action")          # "approve" | "reject"
        review_note = request.form.get("review_note", "").strip()

        if action == "approve":
            application.status = "approved"
        elif action == "reject":
            if not review_note:
                flash("Please provide a reason for rejection.", "danger")
                return render_template("admin/application_review.html", application=application)
            application.status = "rejected"
        else:
            flash("Invalid action.", "danger")
            return render_template("admin/application_review.html", application=application)

        application.reviewed_by  = current_user.id
        application.review_note  = review_note
        application.reviewed_at  = datetime.now(timezone.utc)
        db.session.commit()

        # Notify the student
        try:
            subject = f"CAMS - Leadership Application {action.title()}d"
            body = f"""Hello {application.student.first_name},

Your leadership application for the role of {application.position.replace('_', ' ').title()} in {application.club.name} has been {action}d.

"""
            if review_note:
                body += f"Reviewer Note: {review_note}\n\n"
            
            body += "Regards,\nCAMS System"
            send_email(application.student.email, subject, body)
        except Exception as e:
            current_app.logger.error(f"Error sending email to {application.student.email}: {e}")

        flash(f"Application {action}d successfully.", "success")
        return redirect(url_for("dashboard.application_review_list"))

    return render_template("admin/application_review.html", application=application)


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
    new_admin.set_password(password)

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
    
    if assistant.check_password_reuse(new_password):
        flash("Cannot reuse a previous password for this Assistant.", "danger")
        return redirect(url_for("dashboard.assistants"))
        
    assistant.set_password(new_password)
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

# -------------------------------------------------
# NOTIFICATIONS
# -------------------------------------------------
@dashboard.route("/notifications")
@login_required
def notifications():
    from cams.models import Notification
    notifications_list = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_date.desc()).all()
    return render_template("dashboard/notifications.html", notifications=notifications_list)

@dashboard.route("/notifications/<int:id>/read", methods=["POST"])
@login_required
def mark_read(id):
    from cams.models import Notification
    notif = Notification.query.get_or_404(id)
    if notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
    return redirect(url_for('dashboard.notifications'))

@dashboard.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    from cams.models import Notification
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(dict(is_read=True))
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for('dashboard.notifications'))

# -------------------------------------------------
# ANNOUNCEMENTS
# -------------------------------------------------
@dashboard.route("/admin/announcements", methods=["GET", "POST"])
@login_required
@dean_only
def announcements():
    from cams.models import Announcement
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        target_audience = request.form.get("target_audience", "all")
        expires_at_str = request.form.get("expires_at")
        
        expires_at = None
        if expires_at_str:
            from datetime import datetime
            expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d')
            
        ann = Announcement(
            title=title,
            content=content,
            target_audience=target_audience,
            author_id=current_user.id,
            expires_at=expires_at
        )
        db.session.add(ann)
        db.session.commit()
        flash("Announcement created successfully.", "success")
        return redirect(url_for('dashboard.announcements'))
        
    all_announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("dashboard/announcements.html", announcements=all_announcements)

@dashboard.route("/admin/announcements/<int:id>/delete", methods=["POST"])
@login_required
@dean_only
def delete_announcement(id):
    from cams.models import Announcement
    ann = Announcement.query.get_or_404(id)
    db.session.delete(ann)
    db.session.commit()
    flash("Announcement deleted.", "success")
    return redirect(url_for("dashboard.announcements"))

# -------------------------------------------------
# SYSTEM REPORTS
# -------------------------------------------------
@dashboard.route("/admin/reports", methods=["GET"])
@login_required
@admin_required
def system_reports():
    from datetime import datetime, timedelta
    
    # Get date filters from request
    end_date_str = request.args.get("end_date")
    start_date_str = request.args.get("start_date")
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        end_date = datetime.utcnow()
        
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    else:
        start_date = end_date - timedelta(days=30)
    
    # Make sure end_date includes the entire day
    end_date = end_date.replace(hour=23, minute=59, second=59)

    # 1. Fetch Clubs (All statuses as requested)
    clubs = Club.query.filter(
        Club.registration_date >= start_date,
        Club.registration_date <= end_date
    ).order_by(Club.registration_date.asc()).all()

    # 2. Fetch Members (active members or all members? Let's just do all for timeline, but filter by join_date)
    memberships = ClubMembership.query.filter(
        ClubMembership.join_date >= start_date,
        ClubMembership.join_date <= end_date
    ).order_by(ClubMembership.join_date.asc()).all()

    # Prepare timeline data (Group by Date)
    from collections import defaultdict
    club_timeline = defaultdict(int)
    member_timeline = defaultdict(int)

    for c in clubs:
        if c.registration_date:
            date_str = c.registration_date.strftime('%Y-%m-%d')
            club_timeline[date_str] += 1

    for m in memberships:
        if m.join_date:
            date_str = m.join_date.strftime('%Y-%m-%d')
            member_timeline[date_str] += 1

    # Generate complete list of dates between start and end
    delta = (end_date.date() - start_date.date()).days
    all_dates = [(start_date.date() + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(delta + 1)]

    # Format data for ChartJS
    chart_labels = all_dates
    chart_clubs_data = [club_timeline.get(d, 0) for d in all_dates]
    chart_members_data = [member_timeline.get(d, 0) for d in all_dates]

    stats = {
        "total_clubs_period": len(clubs),
        "total_members_period": len(memberships),
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d')
    }

    return render_template(
        "admin/reports.html",
        stats=stats,
        clubs=clubs,
        memberships=memberships,
        chart_labels=chart_labels,
        chart_clubs_data=chart_clubs_data,
        chart_members_data=chart_members_data
    )