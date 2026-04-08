import os
from datetime import datetime, timezone

from flask import (
    Blueprint, abort, current_app, flash, redirect,
    render_template, request, send_file, url_for
)
from flask_login import current_user, login_required

from cams.extensions import db
from cams.models import Club, ClubMembership, Notification, User
from cams.models import AuditPeriod, AuditReport, AuditStatus
from cams.audit.reports import generate_audit_docx

audit_bp = Blueprint("audit", __name__, template_folder="templates/audit")


# ─────────────────────────────────────────
# ROLE GUARDS
# ─────────────────────────────────────────

def leader_or_admin(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or \
           current_user.role not in ("club_leader", "admin"):
            abort(403)
        return f(*args, **kwargs)
    return login_required(wrapper)


def dean_or_admin(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or \
           current_user.role not in ("dean", "admin", "assistant_admin"):
            abort(403)
        return f(*args, **kwargs)
    return login_required(wrapper)


# ─────────────────────────────────────────
# HELPER — get clubs the current leader manages
# ─────────────────────────────────────────

def _leader_clubs():
    return (
        Club.query
        .join(ClubMembership, ClubMembership.club_id == Club.id)
        .filter(
            ClubMembership.user_id == current_user.id,
            ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
            ClubMembership.status == "active",
        )
        .all()
    )


# ═══════════════════════════════════════════════════════════
# CLUB LEADER ROUTES
# ═══════════════════════════════════════════════════════════

@audit_bp.route("/")
@login_required
def audit_home():
    # Direct users to the appropriate view based on their role
    # Deans/Admins see the review queue, Leaders see their club's audit history
    """
    Leader → their clubs' audit history.
    Dean/Admin → all audits pending review.
    """
    if current_user.role in ("dean", "admin"):
        return redirect(url_for("audit.dean_queue"))

    clubs = _leader_clubs()
    club_ids = [c.id for c in clubs]

    reports = (
        AuditReport.query
        .filter(AuditReport.club_id.in_(club_ids))
        .order_by(AuditReport.created_at.desc())
        .all()
    )
    return render_template(
        "audit/leader_home.html",
        clubs=clubs,
        reports=reports,
        AuditStatus=AuditStatus,
    )


@audit_bp.route("/submit", methods=["GET", "POST"])
@leader_or_admin
def submit_audit():
    # Provide the form for club leaders to submit new audit reports.
    # Handles both Drafts and Final Submissions depending on the 'action' passed in form data.
    """Club leader creates and submits an audit report."""
    clubs = _leader_clubs()
    periods = list(AuditPeriod)
    current_year = datetime.now().year
    years = list(range(current_year - 2, current_year + 1))

    if request.method == "POST":
        club_id = request.form.get("club_id", type=int)
        period  = request.form.get("period")
        year    = request.form.get("year", type=int)
        action  = request.form.get("action", "draft")  # "draft" or "submit"

        # Basic validation
        if not club_id or not period or not year:
            flash("Club, period and year are required.", "danger")
            return render_template("audit/submit_audit.html",
                                   clubs=clubs, periods=periods, years=years)

        # Prevent duplicate submission for same period/year
        existing = AuditReport.query.filter_by(
            club_id=club_id, period=AuditPeriod(period), year=year
        ).first()
        if existing and existing.status not in (AuditStatus.REJECTED,):
            flash("An audit for this period already exists. "
                  "Please edit the existing one.", "warning")
            return redirect(url_for("audit.edit_audit", report_id=existing.id))

        report = AuditReport(
            club_id      = club_id,
            submitted_by = current_user.id,
            period       = AuditPeriod(period),
            year         = year,
            # Membership
            total_members      = request.form.get("total_members",      0, type=int),
            active_members     = request.form.get("active_members",     0, type=int),
            new_members        = request.form.get("new_members",        0, type=int),
            members_left       = request.form.get("members_left",       0, type=int),
            # Events
            events_held        = request.form.get("events_held",        0, type=int),
            events_planned     = request.form.get("events_planned",     0, type=int),
            average_attendance = request.form.get("average_attendance", 0.0, type=float),
            # Finances
            opening_balance    = request.form.get("opening_balance",    0.0, type=float),
            total_income       = request.form.get("total_income",       0.0, type=float),
            total_expenditure  = request.form.get("total_expenditure",  0.0, type=float),
            closing_balance    = request.form.get("closing_balance",    0.0, type=float),
            fees_collected     = request.form.get("fees_collected",     0.0, type=float),
            outstanding_fees   = request.form.get("outstanding_fees",   0.0, type=float),
            # Compliance checkboxes
            has_constitution       = bool(request.form.get("has_constitution")),
            has_patron_letter      = bool(request.form.get("has_patron_letter")),
            has_meeting_minutes    = bool(request.form.get("has_meeting_minutes")),
            elections_held         = bool(request.form.get("elections_held")),
            financial_report_filed = bool(request.form.get("financial_report_filed")),
            # Text sections
            achievements     = request.form.get("achievements",     "").strip(),
            challenges       = request.form.get("challenges",       "").strip(),
            recommendations  = request.form.get("recommendations",  "").strip(),
            additional_notes = request.form.get("additional_notes", "").strip(),
        )

        # If resubmitting after rejection, increment revision
        if existing and existing.status == AuditStatus.REJECTED:
            report.revision_number = existing.revision_number + 1

        if action == "submit":
            report.status       = AuditStatus.SUBMITTED
            report.submitted_at = datetime.now(timezone.utc)
            flash("Audit submitted successfully for Dean review.", "success")
        else:
            report.status = AuditStatus.DRAFT
            flash("Audit saved as draft.", "info")

        db.session.add(report)
        db.session.commit()
        return redirect(url_for("audit.audit_detail", report_id=report.id))

    return render_template("audit/submit_audit.html",
                           clubs=clubs, periods=periods, years=years)


@audit_bp.route("/<int:report_id>")
@login_required
def audit_detail(report_id):
    """View a single audit report."""
    report = AuditReport.query.get_or_404(report_id)

    # Access control: leaders only see their own clubs; dean/admin see all
    if current_user.role == "club_leader":
        leader_club_ids = [c.id for c in _leader_clubs()]
        if report.club_id not in leader_club_ids:
            abort(403)

    return render_template(
        "audit/audit_detail.html",
        report=report,
        AuditStatus=AuditStatus,
    )


@audit_bp.route("/<int:report_id>/edit", methods=["GET", "POST"])
@leader_or_admin
def edit_audit(report_id):
    """Edit a DRAFT or REJECTED audit before resubmission."""
    report = AuditReport.query.get_or_404(report_id)

    if report.status not in (AuditStatus.DRAFT, AuditStatus.REJECTED):
        flash("Only draft or rejected audits can be edited.", "warning")
        return redirect(url_for("audit.audit_detail", report_id=report_id))

    clubs   = _leader_clubs()
    periods = list(AuditPeriod)
    current_year = datetime.now().year
    years = list(range(current_year - 2, current_year + 1))

    if request.method == "POST":
        action = request.form.get("action", "draft")

        # Update all fields
        report.total_members       = request.form.get("total_members",      0, type=int)
        report.active_members      = request.form.get("active_members",     0, type=int)
        report.new_members         = request.form.get("new_members",        0, type=int)
        report.members_left        = request.form.get("members_left",       0, type=int)
        report.events_held         = request.form.get("events_held",        0, type=int)
        report.events_planned      = request.form.get("events_planned",     0, type=int)
        report.average_attendance  = request.form.get("average_attendance", 0.0, type=float)
        report.opening_balance     = request.form.get("opening_balance",    0.0, type=float)
        report.total_income        = request.form.get("total_income",       0.0, type=float)
        report.total_expenditure   = request.form.get("total_expenditure",  0.0, type=float)
        report.closing_balance     = request.form.get("closing_balance",    0.0, type=float)
        report.fees_collected      = request.form.get("fees_collected",     0.0, type=float)
        report.outstanding_fees    = request.form.get("outstanding_fees",   0.0, type=float)
        report.has_constitution        = bool(request.form.get("has_constitution"))
        report.has_patron_letter       = bool(request.form.get("has_patron_letter"))
        report.has_meeting_minutes     = bool(request.form.get("has_meeting_minutes"))
        report.elections_held          = bool(request.form.get("elections_held"))
        report.financial_report_filed  = bool(request.form.get("financial_report_filed"))
        report.achievements     = request.form.get("achievements",     "").strip()
        report.challenges       = request.form.get("challenges",       "").strip()
        report.recommendations  = request.form.get("recommendations",  "").strip()
        report.additional_notes = request.form.get("additional_notes", "").strip()

        if action == "submit":
            report.status       = AuditStatus.SUBMITTED
            report.submitted_at = datetime.now(timezone.utc)
            # Clear previous rejection note
            report.review_note  = None
            flash("Audit resubmitted for Dean review.", "success")
        else:
            flash("Audit draft updated.", "info")

        db.session.commit()
        return redirect(url_for("audit.audit_detail", report_id=report.id))

    return render_template(
        "audit/submit_audit.html",
        clubs=clubs, periods=periods, years=years,
        report=report,   # pre-fill form for editing
        editing=True,
    )


# ═══════════════════════════════════════════════════════════
# DEAN ROUTES
# ═══════════════════════════════════════════════════════════

@audit_bp.route("/dean/queue")
@dean_or_admin
def dean_queue():
    """Dean sees all audits sorted by status."""
    submitted    = AuditReport.query.filter_by(status=AuditStatus.SUBMITTED)\
                       .order_by(AuditReport.submitted_at).all()
    under_review = AuditReport.query.filter_by(status=AuditStatus.UNDER_REVIEW)\
                       .order_by(AuditReport.submitted_at).all()
    approved     = AuditReport.query.filter_by(status=AuditStatus.APPROVED)\
                       .order_by(AuditReport.reviewed_at.desc()).limit(20).all()
    rejected     = AuditReport.query.filter_by(status=AuditStatus.REJECTED)\
                       .order_by(AuditReport.reviewed_at.desc()).limit(20).all()

    return render_template(
        "audit/dean_queue.html",
        submitted=submitted,
        under_review=under_review,
        approved=approved,
        rejected=rejected,
        AuditStatus=AuditStatus,
    )


@audit_bp.route("/dean/review/<int:report_id>", methods=["GET", "POST"])
@dean_or_admin
def dean_review(report_id):
    """Dean reviews a specific audit — approve or reject."""
    report = AuditReport.query.get_or_404(report_id)

    # Mark as under_review when dean opens it
    if report.status == AuditStatus.SUBMITTED:
        report.status = AuditStatus.UNDER_REVIEW
        db.session.commit()

    if request.method == "POST":
        action      = request.form.get("action")       # "approve" | "reject"
        review_note = request.form.get("review_note", "").strip()

        if action not in ("approve", "reject"):
            flash("Invalid action.", "danger")
            return redirect(url_for("audit.dean_review", report_id=report_id))

        report.reviewed_by  = current_user.id
        report.reviewed_at  = datetime.now(timezone.utc)
        report.review_note  = review_note

        if action == "approve":
            report.status = AuditStatus.APPROVED
            # Auto-generate the Word report
            try:
                output_dir  = os.path.join(current_app.root_path, "static", "audit_reports")
                os.makedirs(output_dir, exist_ok=True)
                filename    = f"audit_{report.id}_{report.club.name.replace(' ','_')}_{report.period.value}_{report.year}.docx"
                output_path = os.path.join(output_dir, filename)
                generate_audit_docx(report, output_path)
                report.report_file         = filename
                report.report_generated_at = datetime.now(timezone.utc)
            except Exception as e:
                current_app.logger.error(f"Audit report generation failed: {e}")
                flash("Audit approved but report generation failed. "
                      "Please try downloading again.", "warning")

            db.session.commit()
            flash(f"Audit approved and report generated for {report.club.name}.", "success")

        elif action == "reject":
            if not review_note:
                flash("A rejection reason is required.", "danger")
                return render_template("audit/dean_review.html",
                                       report=report, AuditStatus=AuditStatus)

            report.status = AuditStatus.REJECTED
            db.session.commit()

            # Send notifications to all active club leaders
            _notify_rejection(report, review_note)
            flash(f"Audit rejected. Club leaders have been notified.", "warning")

        return redirect(url_for("audit.dean_queue"))

    return render_template(
        "audit/dean_review.html",
        report=report,
        AuditStatus=AuditStatus,
    )


@audit_bp.route("/dean/report/<int:report_id>/download")
@dean_or_admin
def download_report(report_id):
    """Serve the generated .docx file for download."""
    report = AuditReport.query.get_or_404(report_id)

    if not report.report_file:
        flash("No report file found. Regenerate by re-approving the audit.", "warning")
        return redirect(url_for("audit.dean_review", report_id=report_id))

    file_path = os.path.join(
        current_app.root_path, "static", "audit_reports", report.report_file
    )
    if not os.path.exists(file_path):
        flash("Report file missing from server. Please regenerate.", "danger")
        return redirect(url_for("audit.dean_review", report_id=report_id))

    return send_file(
        file_path,
        as_attachment=True,
        download_name=report.report_file,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@audit_bp.route("/dean/report/<int:report_id>/regenerate", methods=["POST"])
@dean_or_admin
def regenerate_report(report_id):
    """Re-generate the Word report for an already-approved audit."""
    report = AuditReport.query.get_or_404(report_id)
    if report.status != AuditStatus.APPROVED:
        flash("Only approved audits can have reports generated.", "warning")
        return redirect(url_for("audit.dean_queue"))

    try:
        output_dir  = os.path.join(current_app.root_path, "static", "audit_reports")
        os.makedirs(output_dir, exist_ok=True)
        filename    = f"audit_{report.id}_{report.club.name.replace(' ','_')}_{report.period.value}_{report.year}.docx"
        output_path = os.path.join(output_dir, filename)
        generate_audit_docx(report, output_path)
        report.report_file         = filename
        report.report_generated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Report regenerated successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Regeneration failed: {e}")
        flash(f"Regeneration failed: {e}", "danger")

    return redirect(url_for("audit.dean_review", report_id=report_id))


# ─────────────────────────────────────────
# INTERNAL — send rejection notifications
# ─────────────────────────────────────────

def _notify_rejection(report: AuditReport, reason: str):
    """
    Create a Notification record for every active leader of the club.
    These surface in the CAMS notification panel automatically.
    """
    leaders = ClubMembership.query.filter(
        ClubMembership.club_id == report.club_id,
        ClubMembership.role.in_(["president", "vice_president", "secretary", "treasurer"]),
        ClubMembership.status == "active",
    ).all()

    for membership in leaders:
        notif = Notification(
            club_id           = report.club_id,
            user_id           = membership.user_id,
            title             = f"Audit Report Rejected — {report.period.value} {report.year}",
            message           = (
                f"Your {report.period.value} {report.year} audit for "
                f"{report.club.name} was rejected by the Dean.\n\n"
                f"Reason: {reason}\n\n"
                f"Please review the feedback, update your report, and resubmit."
            ),
            notification_type = "audit_rejected",
            priority          = "high",
            is_read           = False,
        )
        db.session.add(notif)

    db.session.commit()