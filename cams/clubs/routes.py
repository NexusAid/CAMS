from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from cams.extensions import db
from cams.models import Club, ClubMembership
from . import clubs
from datetime import datetime, timedelta




# -------------------------
# LIST CLUBS
# Displays all clubs in the system for general browsing
# -------------------------
@clubs.route("/")
@login_required
def list_clubs():
    all_clubs = Club.query.all()
    return render_template("clubs/list.html", clubs=all_clubs)


# -------------------------
# CREATE CLUB
# -------------------------
@clubs.route("/create", methods=["GET", "POST"])
@login_required
def create_club():
    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]

        if Club.query.filter_by(name=name).first():
            flash("Club already exists!", "danger")
            return redirect(url_for("clubs.create_club"))

        club = Club(name=name, description=description)
        db.session.add(club)
        db.session.commit()
        flash("Club created successfully!", "success")
        return redirect(url_for("clubs.list_clubs"))

    return render_template("clubs/create.html")


# -------------------------
# EDIT CLUB
# -------------------------
@clubs.route("/edit/<int:club_id>", methods=["GET", "POST"])
@login_required
def edit_club(club_id):
    club = Club.query.get_or_404(club_id)

    if request.method == "POST":
        club.name = request.form["name"]
        club.description = request.form["description"]
        db.session.commit()

        flash("Club updated successfully!", "success")
        return redirect(url_for("clubs.list_clubs"))

    return render_template("clubs/edit.html", club=club)


# -------------------------
# DELETE CLUB
# -------------------------
@clubs.route("/delete/<int:club_id>")
@login_required
def delete_club(club_id):
    club = Club.query.get_or_404(club_id)
    db.session.delete(club)
    db.session.commit()
    flash("Club deleted successfully!", "success")
    return redirect(url_for("clubs.list_clubs"))


# users functionalities
@clubs.route("/join/<int:club_id>")
@login_required
def join_club(club_id):
    club = Club.query.get_or_404(club_id)
    
    # Check if already a member
    existing = ClubMembership.query.filter_by(
        user_id=current_user.id,
        club_id=club_id
    ).first()
    
    if existing:
        flash("You are already locally tracked or have a pending request for this club", "info")
        return redirect(url_for("dashboard.dashboard_home"))
    
    # Check if club is active
    if club.status != 'active':
        flash("This club is not currently accepting new members", "warning")
        return redirect(url_for("dashboard.dashboard_home"))
    
    # Create membership as PENDING
    membership = ClubMembership(
        user_id=current_user.id,
        club_id=club_id,
        status='pending',
        role='member'
    )
    
    db.session.add(membership)
    db.session.commit()

    # Notify leaders
    leaderships = ClubMembership.query.filter(
        ClubMembership.club_id == club.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).all()
    
    from cams.utils.email_service import send_email
    for lead in leaderships:
        if lead.user and lead.user.email:
            subject = f"New Join Request: {club.name}"
            body = f"Hello {lead.user.first_name},\n\n{current_user.full_name} ({current_user.email}) has requested to join your club '{club.name}'.\n\nPlease log in to the Club Leader portal to review and approve their request.\n\nBest Regards,\nCAMS System"
            try:
                send_email(lead.user.email, subject, body)
            except Exception as e:
                pass
    
    flash(f"Your request to join {club.name} has been sent successfully! The club leaders will review your request.", "success")
    return redirect(url_for("dashboard.dashboard_home"))

@clubs.route("/pay-fees/<int:membership_id>", methods=["POST"])
@login_required
def pay_fees(membership_id):
    membership = ClubMembership.query.get_or_404(membership_id)
    
    # Verify ownership
    if membership.user_id != current_user.id:
        flash("Unauthorized action", "danger")
        return redirect(url_for("dashboard.clubs_list"))
    
    # Process payment (simplified)
    membership.has_paid_fees = True
    membership.payment_date = datetime.utcnow()
    membership.fee_amount = request.form.get("amount", 0)
    
    db.session.commit()
    
    flash("Fees paid successfully", "success")
    # Fixed URL route reference from the non-existent 'club.view' to 'dashboard.club_details'
    return redirect(url_for("dashboard.club_details", club_id=membership.club_id))