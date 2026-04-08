from datetime import datetime, timezone
from flask import (
    Blueprint, abort, flash, redirect,
    render_template, request, url_for
)
from flask_login import current_user, login_required
from sqlalchemy import func
from cams.models import db
from cams.models import (
    Election, ElectionPosition, ElectionStatus,
    Vote, LeadershipApplication,
    check_voting_eligibility,
)

elections_bp = Blueprint("elections", __name__, template_folder="templates/elections")


from cams.utils.decorators import admin_required, dean_required

def get_election_base_tmpl(user):
    from flask import session
    portal = session.get('active_portal')
    
    if not getattr(user, 'is_authenticated', False):
        return "base/base.html"
        
    if portal == 'student':
        return "base/base.html"
        
    if user.role in ['admin', 'dean']:
        return "base/admin_base.html"
        
    from cams.models import ClubMembership
    is_leader = ClubMembership.query.filter(
        ClubMembership.user_id == user.id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active"
    ).first() is not None
    
    if is_leader and portal == 'leader':
        return "base/club_leader.html"
        
    # Default to base.html if none of the above match, or if it's a leader 
    # but their portal isn't specifically set to 'leader' (though base fallback handles that)
    return "base/club_leader.html" if is_leader else "base/base.html"


# ─────────────────────────────────────────
# ADMIN — ELECTION MANAGEMENT
# ─────────────────────────────────────────

@elections_bp.route("/")
@login_required
def election_list():
    """All elections across all clubs."""
    if current_user.role in ['admin', 'dean']:
        elections = Election.query.order_by(Election.created_at.desc()).all()
    else:
        from cams.models import ClubMembership
        my_clubs = [m.club_id for m in ClubMembership.query.filter_by(user_id=current_user.id, status='active').all()]
        elections = Election.query.filter(Election.club_id.in_(my_clubs)).order_by(Election.created_at.desc()).all()
        
    base_tmpl = get_election_base_tmpl(current_user)
        
    return render_template("elections/election_list.html", elections=elections, base_template=base_tmpl)


@elections_bp.route("/create", methods=["GET", "POST"])
@admin_required
def election_create():
    """Admin creates a new election and adds positions."""
    from cams.models import Club, ClubMembership
    from cams.utils.notifications import send_notification
    from cams.utils.email_service import send_email
    from flask import current_app

    clubs = Club.query.filter(~Club.status.in_(['deregistered', 'rejected'])).all()

    if request.method == "POST":
        title            = request.form.get("title", "").strip()
        description      = request.form.get("description", "").strip()
        club_id_raw      = request.form.get("club_id", "").strip()
        nomination_start = _parse_dt(request.form.get("nomination_start"))
        nomination_end   = _parse_dt(request.form.get("nomination_end"))
        position_titles  = request.form.getlist("position_title")
        position_descs   = request.form.getlist("position_description")

        if not title or not club_id_raw or not position_titles:
            flash("Title, club and at least one position are required.", "danger")
            return render_template("elections/election_create.html", clubs=clubs)

        target_clubs = []
        if club_id_raw == "ALL":
            target_clubs = Club.query.filter_by(status='active').all()
        else:
            try:
                cid = int(club_id_raw)
                club_obj = Club.query.get(cid)
                if club_obj:
                    target_clubs.append(club_obj)
            except ValueError:
                pass

        if not target_clubs:
            flash("Invalid club selection or no active clubs available.", "danger")
            return redirect(url_for('elections.election_create'))

        created_election_ids = []

        for c_obj in target_clubs:
            election = Election(
                title=title,
                description=description,
                club_id=c_obj.id,
                created_by=current_user.id,
                status=ElectionStatus.NOMINATION,
                nomination_start=nomination_start,
                nomination_end=nomination_end,
            )
            db.session.add(election)
            db.session.flush()   # get election.id before commit

            for t, d in zip(position_titles, position_descs):
                if t.strip():
                    db.session.add(ElectionPosition(
                        election_id=election.id,
                        title=t.strip(),
                        description=d.strip()
                    ))
            
            created_election_ids.append(election.id)

        db.session.commit()
        
        # Notify active members
        for c_obj in target_clubs:
            members = ClubMembership.query.filter_by(club_id=c_obj.id, status='active').all()
            subject = f"New Election: {title}"
            message = f"An election '{title}' has been created for {c_obj.name}. Nominations are now open. Please review the positions and apply if you are interested!"
            
            for m in members:
                # In-app notification
                send_notification(
                    title=subject,
                    message=message,
                    notification_type="election_created",
                    priority="high",
                    user_id=m.user_id,
                    club_id=c_obj.id
                )
                # Email notification
                if m.user and m.user.email:
                    try:
                        send_email(m.user.email, subject, message)
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email to {m.user.email}: {e}")

        if len(target_clubs) == 1:
            flash(f'Election "{title}" created successfully.', "success")
            return redirect(url_for("elections.election_detail", election_id=created_election_ids[0]))
        else:
            flash(f'Successfully created batch elections for {len(target_clubs)} active clubs.', "success")
            return redirect(url_for("elections.election_list"))

    return render_template("elections/election_create.html", clubs=clubs)


@elections_bp.route("/<int:election_id>")
@login_required
def election_detail(election_id):
    """Detail view — different content based on role & election status."""
    election = Election.query.get_or_404(election_id)

    # Build per-position vote tallies (only after voting)
    tallies = {}
    if election.status in (ElectionStatus.CLOSED, ElectionStatus.PUBLISHED):
        for pos in election.positions:
            candidates = (
                LeadershipApplication.query
                .filter_by(club_id=election.club_id, position=pos.title.lower().replace(" ", "_"), status="approved")
                .all()
            )
            tallies[pos.id] = sorted(candidates, key=lambda n: n.vote_count, reverse=True)

    # Has current user already voted per position?
    voted_positions = set()
    can_vote = False
    can_stand = False
    
    if getattr(current_user, 'is_authenticated', False):
        from cams.models import check_voting_eligibility, _is_final_year_student, ClubMembership
        my_votes = Vote.query.filter_by(
            election_id=election_id, voter_id=current_user.id
        ).all()
        voted_positions = {v.position_id for v in my_votes}
        
        can_vote, _ = check_voting_eligibility(current_user, election)
        
        if current_user.role == 'member' and not _is_final_year_student(current_user):
             membership = ClubMembership.query.filter_by(user_id=current_user.id, club_id=election.club_id, status='active', role='member').first()
             if membership:
                 can_stand = True

    base_tmpl = get_election_base_tmpl(current_user)
    return render_template(
        "elections/election_detail.html",
        election=election,
        tallies=tallies,
        voted_positions=voted_positions,
        ElectionStatus=ElectionStatus,
        base_template=base_tmpl,
        can_vote=can_vote,
        can_stand=can_stand,
    )


@elections_bp.route("/<int:election_id>/advance", methods=["POST"])
@admin_required
def election_advance(election_id):
    """
    Move election through the status pipeline:
    DRAFT → NOMINATION → REVIEW → VOTING → CLOSED → PUBLISHED
    """
    election = Election.query.get_or_404(election_id)

    transitions = {
        ElectionStatus.DRAFT:      ElectionStatus.NOMINATION,
        ElectionStatus.NOMINATION: ElectionStatus.REVIEW,
        ElectionStatus.REVIEW:     ElectionStatus.VOTING,
        ElectionStatus.VOTING:     ElectionStatus.CLOSED,
        ElectionStatus.CLOSED:     ElectionStatus.PUBLISHED,
    }

    # When advancing to VOTING, accept updated voting window from form
    if election.status == ElectionStatus.REVIEW:
        voting_start = _parse_dt(request.form.get("voting_start"))
        voting_end   = _parse_dt(request.form.get("voting_end"))
        if voting_start and voting_end:
            election.voting_start = voting_start
            election.voting_end   = voting_end
        else:
            flash("Please set the voting start and end times before opening voting.", "danger")
            return redirect(url_for("elections.election_detail", election_id=election_id))

    next_status = transitions.get(election.status)
    if not next_status:
        flash("This election cannot be advanced further.", "warning")
        return redirect(url_for("elections.election_detail", election_id=election_id))
        
    if next_status == ElectionStatus.PUBLISHED:
        # 1. Demote old leaders to regular members
        from cams.models import ClubMembership
        from cams.student.routes import generate_token
        from cams.utils.email_service import send_email
        from flask import current_app
        import uuid
        from werkzeug.security import generate_password_hash

        old_leaders = ClubMembership.query.filter(
            ClubMembership.club_id == election.club_id,
            ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
            ClubMembership.status == "active"
        ).all()
        for old_leader in old_leaders:
            old_leader.role = "member"
            # Invalidate current password so they are forced out
            old_leader.user.set_password(str(uuid.uuid4()))
            
            # Send password reset for new plain student access
            token = generate_token(old_leader.user.email, "student-password-reset-salt")
            reset_link = url_for("student.reset_password", token=token, _external=True)
            subject = "CAMS - Leadership Term Concluded"
            body = f"""Hello {old_leader.user.first_name},

Your term as a leader for {election.club.name} has concluded, and you have been transitioned back to a regular member role.

For security purposes, your current password has been invalidated and your access has been temporarily restricted. Please click the link below to set a new password and log back in as a student:
{reset_link}

This link will expire in 1 hour.

Regards,
CAMS System"""
            try:
                send_email(old_leader.user.email, subject, body)
            except Exception as e:
                current_app.logger.error(f"Failed to send email to {old_leader.user.email}: {e}")

        # 2. Promote Winners
        for pos in election.positions:
            # Match the position name from the election to the application's position
            candidates = (
                LeadershipApplication.query
                .filter_by(club_id=election.club_id, position=pos.title.lower().replace(" ", "_"), status="approved")
                .all()
            )
            # Find the winner (assuming single winner per position for now, sort by votes)
            if candidates:
                winner = sorted(candidates, key=lambda n: n.vote_count, reverse=True)[0]
                if winner.vote_count > 0:
                    # Update their membership role
                    winner_membership = ClubMembership.query.filter_by(
                        user_id=winner.student_id, 
                        club_id=election.club_id
                    ).first()
                    
                    if winner_membership:
                        # Convert space-separated title like 'Vice President' to snake_case 'vice_president'
                        role_slug = pos.title.lower().replace(" ", "_")
                        winner_membership.role = role_slug
                        
                        user = winner.student
                        # Enforce password rotation for new privileges
                        user.set_password(str(uuid.uuid4()))
                        
                        # Generate pass reset token
                        token = generate_token(user.email, "student-password-reset-salt")
                        reset_link = url_for("student.reset_password", token=token, _external=True)
                        
                        subject = "CAMS - Congratulations on your Election Win!"
                        body = f"""Hello {user.first_name},

Congratulations! You have been elected as the {pos.title} for {election.club.name}.

For security purposes, you are required to set a new password to access your new club leader privileges. Please click the link below to set a new password:
{reset_link}

This link will expire in 1 hour.

Regards,
CAMS System"""
                        try:
                            send_email(user.email, subject, body)
                        except Exception as e:
                            current_app.logger.error(f"Failed to send email to {user.email}: {e}")


    election.status = next_status
    db.session.commit()
    flash(f"Election status updated to: {next_status.value.upper()}", "success")
    return redirect(url_for("elections.election_detail", election_id=election_id))


# MEMBER — VOTING
# ─────────────────────────────────────────

@elections_bp.route("/<int:election_id>/vote", methods=["GET", "POST"])
@login_required
def vote(election_id):
    """Member casts their votes (one per position)."""
    election = Election.query.get_or_404(election_id)

    if not election.is_voting_open:
        flash("Voting is not currently open for this election.", "warning")
        return redirect(url_for("elections.election_detail", election_id=election_id))

    can_vote, reason = check_voting_eligibility(current_user, election)
    if not can_vote:
        flash(reason, "danger")
        return redirect(url_for("elections.election_detail", election_id=election_id))

    # Already-voted positions
    already_voted = {
        v.position_id for v in
        Vote.query.filter_by(election_id=election_id, voter_id=current_user.id).all()
    }

    positions_with_candidates = []
    for pos in election.positions:
        if pos.id not in already_voted:
            candidates = LeadershipApplication.query.filter_by(
                club_id=election.club_id,
                position=pos.title.lower().replace(" ", "_"),
                status="approved"
            ).all()
            if candidates:
                positions_with_candidates.append((pos, candidates))

    if request.method == "POST":
        errors = []
        votes_to_add = []

        for pos, candidates in positions_with_candidates:
            app_id = request.form.get(f"position_{pos.id}", type=int)
            if not app_id:
                errors.append(f"Please select a candidate for {pos.title}.")
                continue

            # Validate the application belongs to this position and is approved
            app = LeadershipApplication.query.filter_by(
                id=app_id,
                club_id=election.club_id,
                position=pos.title.lower().replace(" ", "_"),
                status="approved"
            ).first()
            if not app:
                errors.append(f"Invalid candidate selection for {pos.title}.")
                continue

            votes_to_add.append(Vote(
                election_id=election_id,
                position_id=pos.id,
                application_id=app_id,
                voter_id=current_user.id,
            ))

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            for v in votes_to_add:
                db.session.add(v)
            db.session.commit()
            flash("Your votes have been cast successfully! Thank you for participating.", "success")
            return redirect(url_for("elections.election_detail", election_id=election_id))

    if not positions_with_candidates:
        flash("You have already voted in all positions for this election.", "info")
        return redirect(url_for("elections.election_detail", election_id=election_id))

    base_tmpl = get_election_base_tmpl(current_user)
    return render_template(
        "elections/vote.html",
        election=election,
        positions_with_candidates=positions_with_candidates,
        base_template=base_tmpl,
    )


# ─────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────

@elections_bp.route("/<int:election_id>/results")
@login_required
def results(election_id):
    """Published results page with vote tallies per position."""
    election = Election.query.get_or_404(election_id)

    if election.status not in (ElectionStatus.CLOSED, ElectionStatus.PUBLISHED):
        if current_user.role != "admin":
            flash("Results are not yet available.", "warning")
            return redirect(url_for("elections.election_detail", election_id=election_id))

    tallies = {}
    for pos in election.positions:
        candidates = (
            LeadershipApplication.query
            .filter_by(club_id=election.club_id, position=pos.title.lower().replace(" ", "_"), status="approved")
            .all()
        )
        tallies[pos.id] = {
            "position": pos,
            "candidates": sorted(candidates, key=lambda n: n.vote_count, reverse=True),
            "total_votes": sum(c.vote_count for c in candidates),
        }

    total_eligible = _count_eligible_voters(election)

    base_tmpl = get_election_base_tmpl(current_user)
    return render_template(
        "elections/results.html",
        election=election,
        tallies=tallies,
        total_eligible=total_eligible,
        ElectionStatus=ElectionStatus,
        base_template=base_tmpl,
    )


# ─────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────

def _parse_dt(value):
    """Parse datetime-local input string → UTC datetime."""
    if not value:
        return None
    try:
        from datetime import timedelta
        # Convert from EAT (UTC+3) local time to UTC
        local_dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        return local_dt - timedelta(hours=3)
    except ValueError:
        return None


def _count_eligible_voters(election):
    """Count active members of the club (eligible voters)."""
    from cams.models import ClubMembership
    return ClubMembership.query.filter_by(
        club_id=election.club_id, status='active'
    ).count()