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
    Nomination, NominationStatus, Vote,
    check_nomination_eligibility, check_voting_eligibility,
)

elections_bp = Blueprint("elections", __name__, template_folder="templates/elections")


# ─────────────────────────────────────────
# DECORATORS / GUARDS
# ─────────────────────────────────────────
from cams.utils.decorators import admin_required, dean_required


# ─────────────────────────────────────────
# ADMIN — ELECTION MANAGEMENT
# ─────────────────────────────────────────

@elections_bp.route("/")
@admin_required
def election_list():
    """All elections across all clubs."""
    elections = Election.query.order_by(Election.created_at.desc()).all()
    return render_template("elections/election_list.html", elections=elections)


@elections_bp.route("/create", methods=["GET", "POST"])
@admin_required
def election_create():
    """Admin creates a new election and adds positions."""
    from cams.models import Club  # your Club model

    clubs = Club.query.filter_by(status="active").all()

    if request.method == "POST":
        title            = request.form.get("title", "").strip()
        description      = request.form.get("description", "").strip()
        club_id          = request.form.get("club_id", type=int)
        nomination_start = _parse_dt(request.form.get("nomination_start"))
        nomination_end   = _parse_dt(request.form.get("nomination_end"))
        position_titles  = request.form.getlist("position_title")
        position_descs   = request.form.getlist("position_description")

        if not title or not club_id or not position_titles:
            flash("Title, club and at least one position are required.", "danger")
            return render_template("elections/election_create.html", clubs=Club)

        election = Election(
            title=title,
            description=description,
            club_id=club_id,
            created_by=current_user.id,
            status=ElectionStatus.DRAFT,
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

        db.session.commit()
        flash(f'Election "{title}" created successfully.', "success")
        return redirect(url_for("elections.election_detail", election_id=election.id))

    return render_template("elections/election_create.html", clubs=Club)


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
                Nomination.query
                .filter_by(position_id=pos.id, status=NominationStatus.APPROVED)
                .all()
            )
            tallies[pos.id] = sorted(candidates, key=lambda n: n.vote_count, reverse=True)

    # Has current user already voted per position?
    voted_positions = set()
    if current_user.is_authenticated:
        my_votes = Vote.query.filter_by(
            election_id=election_id, voter_id=current_user.id
        ).all()
        voted_positions = {v.position_id for v in my_votes}

    return render_template(
        "elections/election_detail.html",
        election=election,
        tallies=tallies,
        voted_positions=voted_positions,
        ElectionStatus=ElectionStatus,
        NominationStatus=NominationStatus,
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

    election.status = next_status
    db.session.commit()
    flash(f"Election status updated to: {next_status.value.upper()}", "success")
    return redirect(url_for("elections.election_detail", election_id=election_id))


# ─────────────────────────────────────────
# MEMBER — NOMINATIONS
# ─────────────────────────────────────────

@elections_bp.route("/<int:election_id>/nominate", methods=["GET", "POST"])
@login_required
def nominate(election_id):
    """Member submits their candidacy for a position."""
    election = Election.query.get_or_404(election_id)

    if not election.is_nomination_open:
        flash("Nominations are not currently open for this election.", "warning")
        return redirect(url_for("elections.election_detail", election_id=election_id))

    eligible, reason = check_nomination_eligibility(current_user, election.club_id)
    if not eligible:
        flash(reason, "danger")
        return redirect(url_for("elections.election_detail", election_id=election_id))

    if request.method == "POST":
        position_id = request.form.get("position_id", type=int)
        manifesto   = request.form.get("manifesto", "").strip()

        # Check not already nominated for this position
        existing = Nomination.query.filter_by(
            election_id=election_id,
            position_id=position_id,
            member_id=current_user.id
        ).first()
        if existing:
            flash("You have already submitted a nomination for this position.", "warning")
            return redirect(url_for("elections.election_detail", election_id=election_id))

        nom = Nomination(
            election_id=election_id,
            position_id=position_id,
            member_id=current_user.id,
            manifesto=manifesto,
            status=NominationStatus.PENDING,
        )
        db.session.add(nom)
        db.session.commit()
        flash("Your nomination has been submitted and is awaiting the Dean's approval.", "success")
        return redirect(url_for("elections.election_detail", election_id=election_id))

    return render_template(
        "elections/nominate.html",
        election=election,
    )


# ─────────────────────────────────────────
# DEAN — NOMINATION REVIEW
# ─────────────────────────────────────────

@elections_bp.route("/nominations/review")
@dean_required
def nomination_review_list():
    """Dean sees all pending nominations across all elections."""
    pending = (
        Nomination.query
        .filter_by(status=NominationStatus.PENDING)
        .join(Election)
        .order_by(Election.id, Nomination.submitted_at)
        .all()
    )
    return render_template("elections/nomination_review_list.html", nominations=pending)


@elections_bp.route("/nominations/<int:nom_id>/review", methods=["GET", "POST"])
@dean_required
def nomination_review(nom_id):
    """Dean approves or rejects a single nomination."""
    nom = Nomination.query.get_or_404(nom_id)

    if nom.status != NominationStatus.PENDING:
        flash("This nomination has already been reviewed.", "info")
        return redirect(url_for("elections.nomination_review_list"))

    if request.method == "POST":
        action      = request.form.get("action")          # "approve" | "reject"
        review_note = request.form.get("review_note", "").strip()

        if action == "approve":
            nom.status = NominationStatus.APPROVED
        elif action == "reject":
            if not review_note:
                flash("Please provide a reason for rejection.", "danger")
                return render_template("elections/nomination_review.html", nom=nom)
            nom.status = NominationStatus.REJECTED
        else:
            flash("Invalid action.", "danger")
            return render_template("elections/nomination_review.html", nom=nom)

        nom.reviewed_by  = current_user.id
        nom.review_note  = review_note
        nom.reviewed_at  = datetime.now(timezone.utc)
        db.session.commit()

        flash(f"Nomination {action}d successfully.", "success")
        return redirect(url_for("elections.nomination_review_list"))

    return render_template("elections/nomination_review.html", nom=nom,
                           NominationStatus=NominationStatus)


# ─────────────────────────────────────────
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
            candidates = Nomination.query.filter_by(
                position_id=pos.id,
                status=NominationStatus.APPROVED
            ).all()
            if candidates:
                positions_with_candidates.append((pos, candidates))

    if request.method == "POST":
        errors = []
        votes_to_add = []

        for pos, candidates in positions_with_candidates:
            nom_id = request.form.get(f"position_{pos.id}", type=int)
            if not nom_id:
                errors.append(f"Please select a candidate for {pos.title}.")
                continue

            # Validate the nomination belongs to this position
            nom = Nomination.query.filter_by(
                id=nom_id,
                position_id=pos.id,
                status=NominationStatus.APPROVED
            ).first()
            if not nom:
                errors.append(f"Invalid candidate selection for {pos.title}.")
                continue

            votes_to_add.append(Vote(
                election_id=election_id,
                position_id=pos.id,
                nomination_id=nom_id,
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

    return render_template(
        "elections/vote.html",
        election=election,
        positions_with_candidates=positions_with_candidates,
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
            Nomination.query
            .filter_by(position_id=pos.id, status=NominationStatus.APPROVED)
            .all()
        )
        tallies[pos.id] = {
            "position": pos,
            "candidates": sorted(candidates, key=lambda n: n.vote_count, reverse=True),
            "total_votes": sum(c.vote_count for c in candidates),
        }

    total_eligible = _count_eligible_voters(election)

    return render_template(
        "elections/results.html",
        election=election,
        tallies=tallies,
        total_eligible=total_eligible,
        ElectionStatus=ElectionStatus,
    )


# ─────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────

def _parse_dt(value):
    """Parse datetime-local input string → UTC datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _count_eligible_voters(election):
    """Count active members of the club (eligible voters)."""
    from cams.models import ClubMembership
    return ClubMembership.query.filter_by(
        club_id=election.club_id, status='active'
    ).count()