from datetime import datetime, timedelta
from cams.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import event
from datetime import datetime, timezone, date
from enum import Enum as PyEnum


class PasswordHistory(db.Model):
    __tablename__ = "password_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

# -----------------------------
# USER MODEL
# Represents all human actors in the system (students, admins, deans, etc.)
# -----------------------------
class User(UserMixin, db.Model):
    __tablename__ = "user"

    # Primary key for uniquely identifying a user
    id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    registration_number = db.Column(db.String(50), unique=True, nullable=True)
    course = db.Column(db.String(150), nullable=True)
    profile_image = db.Column(db.String(300), nullable=True)

    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default="student")
    # student | club_leader | admin | dean | assistant_admin | staff

    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=False)

    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    memberships = db.relationship("ClubMembership", backref="user", lazy=True)
    password_history = db.relationship("PasswordHistory", backref="user", lazy=True, cascade="all, delete-orphan")

    @property
    def full_name(self):
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        return (f"{first} {last}").strip()

    @property
    def name(self):
        """
        Compatibility alias used across templates.
        Falls back to email if names are missing.
        """
        return self.full_name or (self.email or "")

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_club_leader(self):
        return any(m.role in ["president", "vice_president", "secretary", "treasurer"] and m.status == "active" for m in self.memberships)

    def set_password(self, password):
        # Save current password to history before changing
        if self.password_hash:
            history = PasswordHistory(password_hash=self.password_hash)
            self.password_history.append(history)
            
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def check_password_reuse(self, new_password):
        """Returns True if the new password has been used before (in current or history)"""
        # Check current password
        if self.password_hash and check_password_hash(self.password_hash, new_password):
            return True
            
        # Check history
        for history in self.password_history:
            if check_password_hash(history.password_hash, new_password):
                return True
                
        return False

    def __repr__(self):
        return f"<User {self.email}>"



# ============================================================
# CLUB MODEL
# ============================================================

class Club(db.Model):
    __tablename__ = "club"

    id = db.Column(db.Integer, primary_key=True)

    # ----------------------------------------------------------
    # BASIC INFORMATION
    # ----------------------------------------------------------
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(120))

    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))

    # ----------------------------------------------------------
    # LIFECYCLE STATUS
    # ----------------------------------------------------------
    status = db.Column(db.String(20), default="pending")
    # pending | active | warning | non_compliant | suspended | deregistered | merged

    registration_date = db.Column(db.DateTime)
    last_review_date = db.Column(db.DateTime)

    # ----------------------------------------------------------
    # PATRON (External or Internal)
    # ----------------------------------------------------------
    patron_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    patron = db.relationship("User", backref="patroned_clubs")

    patron_name = db.Column(db.String(150), nullable=True)
    patron_email = db.Column(db.String(120), nullable=True)
    patron_status = db.Column(db.String(20), default="pending")  # pending | accepted | rejected

    # ----------------------------------------------------------
    # REGISTRATION
    # ----------------------------------------------------------
    registration_number = db.Column(db.String(50), unique=True, nullable=True)

    # ----------------------------------------------------------
    # DOCUMENT FLAGS
    # ----------------------------------------------------------
    has_constitution = db.Column(db.Boolean, default=False)
    constitution_file = db.Column(db.String(255))

    has_minutes = db.Column(db.Boolean, default=False)
    minutes_file = db.Column(db.String(255))

    has_patron_letter = db.Column(db.Boolean, default=False)
    patron_letter_file = db.Column(db.String(255))

    has_members_list = db.Column(db.Boolean, default=False)
    members_list_file = db.Column(db.String(255))

    has_rules = db.Column(db.Boolean, default=False)
    rules_file = db.Column(db.String(255))

    # ----------------------------------------------------------
    # MEETINGS
    # ----------------------------------------------------------
    last_meeting_approval = db.Column(db.DateTime)
    next_meeting_date = db.Column(db.DateTime)

    # ----------------------------------------------------------
    # TIMESTAMPS
    # ----------------------------------------------------------
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    date_modified = db.Column(db.DateTime,
                              default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    # ----------------------------------------------------------
    # RELATIONSHIPS
    # ----------------------------------------------------------
    memberships = db.relationship("ClubMembership",
                                   backref="club",
                                   lazy=True,
                                   cascade="all, delete-orphan")

    events = db.relationship("Event",
                             backref="club",
                             lazy=True,
                             cascade="all, delete-orphan")

    elections = db.relationship(
                             "Election",
                             back_populates="club",
                             lazy=True,
                             cascade="all, delete-orphan")
    

    financial_reports = db.relationship("FinancialReport",
                                        backref="club",
                                        lazy=True,
                                        cascade="all, delete-orphan")

    notifications = db.relationship("Notification",
                                     backref="club",
                                     lazy=True,
                                     cascade="all, delete-orphan")

    # ============================================================
    # DYNAMIC PROPERTIES
    # ============================================================

    @property
    def active_members(self):
        return ClubMembership.query.filter_by(
            club_id=self.id,
            status="active"
        ).count()

    @property
    def member_count(self):
        # Calculate total memberships tied to this club regardless of status
        return len(self.memberships)


    @property
    def min_members_required(self):
        return 20

    @property
    def member_count(self): # Added new member_count property as per instruction
        from cams.models import ClubMembership
        return ClubMembership.query.filter_by(
            club_id=self.id,
            status="active"
        ).count()

    @property
    def latest_election(self):
        from cams.models import Election
        return Election.query.filter_by(
            club_id=self.id,
            status="completed"
        ).order_by(Election.voting_end.desc()).first()

    @property
    def latest_financial_report(self):
        return FinancialReport.query.filter_by(
            club_id=self.id
        ).order_by(FinancialReport.report_date.desc()).first()

    # ============================================================
    # LEADERSHIP LOOKUP
    # ============================================================

    def get_official(self, role):
        return ClubMembership.query.filter_by(
            club_id=self.id,
            role=role,
            status="active"
        ).first()

    # ============================================================
    # DORMANCY CHECK
    # ============================================================

    def is_dormant(self):
        if not self.events:
            return True

        latest_event = max(self.events, key=lambda e: e.date)
        return (datetime.utcnow() - latest_event.date).days > 180

    # ============================================================
    # COMPLIANCE ENGINE
    # ============================================================

    def check_compliance_issues(self):
        issues = []

        # Minimum members
        if self.active_members < 20:
            issues.append(f"Insufficient members ({self.active_members}/20)")

        # Patron
        if not self.patron_id:
            issues.append("No patron assigned")

        # Constitution
        if not self.has_constitution:
            issues.append("Missing constitution")

        # Minutes
        if not self.has_minutes:
            issues.append("Missing approval minutes")

        # Patron Letter
        if not self.has_patron_letter:
            issues.append("Missing patron letter")

        # Financial report
        report = self.latest_financial_report
        if not report:
            issues.append("No financial report submitted")
        elif (datetime.utcnow() - report.report_date).days > 365:
            issues.append("Financial report overdue")

        # Elections
        election = self.latest_election
        if not election:
            issues.append("No election records")
        elif (datetime.utcnow() - election.election_date).days > 365:
            issues.append("Elections overdue")

        # Dormancy
        if self.is_dormant():
            issues.append("Club inactive for over 6 months")

        return issues

    def is_compliant(self):
        return len(self.check_compliance_issues()) == 0

    def compliance_score(self):
        total_checks = 8
        passed = total_checks - len(self.check_compliance_issues())
        return max(int((passed / total_checks) * 100), 0)

    def evaluate_status(self):
        issues = self.check_compliance_issues()

        if not issues:
            self.status = "active"
            self.last_review_date = None
            return

        if issues and not self.last_review_date:
            self.status = "warning"
            self.last_review_date = datetime.utcnow()
            return

        if issues and (datetime.utcnow() - self.last_review_date).days >= 14:
            self.status = "non_compliant"

    def __repr__(self):
        return f"<Club {self.name}>"

# -----------------------------

# CLUB MEMBERSHIP MODEL
# -----------------------------
class ClubMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)

    status = db.Column(db.String(20), default='pending')
    # pending | active | inactive

    role = db.Column(db.String(20), default='member')
    # member | president | secretary | treasurer
    
    rejection_count = db.Column(db.Integer, default=0)

    has_paid_fees = db.Column(db.Boolean, default=False)
    fee_amount = db.Column(db.Float, default=0.0)
    payment_date = db.Column(db.DateTime, nullable=True)

    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'club_id', name='unique_membership'),
    )

    def __repr__(self):
        return f"<Membership User:{self.user_id} Club:{self.club_id}>"

# -----------------------------
# CLUB DOCUMENTS
# -----------------------------
class ClubDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=False)

    document_type = db.Column(db.String(50))
    file_name = db.Column(db.String(255))
    file_path = db.Column(db.String(255))

    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploaded_date = db.Column(db.DateTime, default=datetime.utcnow)

    approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approval_date = db.Column(db.DateTime, nullable=True)


# -----------------------------
# EVENTS
# -----------------------------
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    club_id = db.Column(db.Integer, db.ForeignKey("club.id"))
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    
    date = db.Column(db.DateTime, nullable=False) # Start time
    end_date = db.Column(db.DateTime, nullable=True) # End time
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendance = db.relationship("Attendance", backref="event", lazy=True)

    def __repr__(self):
        return f"<Event {self.title}>"


# -----------------------------
# ATTENDANCE
# -----------------------------
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    event_id = db.Column(db.Integer, db.ForeignKey("event.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # attended | absent | apology
    status = db.Column(db.String(20), default="attended")

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Attendance User:{self.user_id} Event:{self.event_id} Status:{self.status}>"


class DeregistrationRecord(db.Model):
    __tablename__ = "deregistration_records"

    id = db.Column(db.Integer, primary_key=True)

    club_id = db.Column(
        db.Integer,
        db.ForeignKey("club.id"),
        nullable=False
    )

    reason = db.Column(db.Text, nullable=False)

    deregistered_by = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    deregistration_date = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    # Optional relationships
    club = db.relationship("Club", backref="deregistration_records")
    admin = db.relationship("User", backref="deregistrations")

# -----------------------------
# NOTIFICATIONS
# -----------------------------
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    title = db.Column(db.String(200))
    message = db.Column(db.Text)

    notification_type = db.Column(db.String(50))
    priority = db.Column(db.String(20), default='normal')

    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(255), nullable=True)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)


# -----------------------------
# ACTIVITY LOGS
# -----------------------------
class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(255))

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Log {self.action}>"
    

#financial report model

class FinancialReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    club_id = db.Column(db.Integer,
                        db.ForeignKey("club.id"),
                        nullable=False)

    report_date = db.Column(db.DateTime, nullable=False)
    file = db.Column(db.String(255))
    verified = db.Column(db.Boolean, default=False)

    date_created = db.Column(db.DateTime, default=datetime.utcnow)


# -----------------------------
# ADMIN TASKS
# -----------------------------
class AdminTask(db.Model):
    __tablename__ = "admin_tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.String(50), default="pending")
    # pending | in_progress | completed

    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id], backref="tasks_assigned")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id], backref="tasks_received")

    def __repr__(self):
        return f"<AdminTask {self.title} ({self.status})>"


# ─────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────

class ElectionStatus(PyEnum):
    DRAFT       = "draft"        # admin is still configuring
    NOMINATION  = "nomination"   # open for candidate submissions
    REVIEW      = "review"       # dean reviewing nominations
    VOTING      = "voting"       # active voting window
    CLOSED      = "closed"       # voting ended
    PUBLISHED   = "published"    # results visible to all


class NominationStatus(PyEnum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"


# ─────────────────────────────────────────
# ELECTION
# ─────────────────────────────────────────

class Election(db.Model):
    __tablename__ = "elections"

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(200), nullable=False)
    description      = db.Column(db.Text, nullable=True)
    club_id          = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False)
    created_by       = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    status           = db.Column(
        db.Enum(ElectionStatus),
        default=ElectionStatus.DRAFT,
        nullable=False
    )

    nomination_start = db.Column(db.DateTime, nullable=True)
    nomination_end   = db.Column(db.DateTime, nullable=True)
    voting_start     = db.Column(db.DateTime, nullable=True)
    voting_end       = db.Column(db.DateTime, nullable=True)

    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    club = db.relationship("Club", back_populates="elections")
    creator = db.relationship(
              "User",
               foreign_keys=[created_by]
        )

    positions = db.relationship(
       "ElectionPosition",
        back_populates="election",
        cascade="all, delete-orphan"
        ) 

    @property
    def is_nomination_open(self):
        now = datetime.utcnow()
        return (self.status == ElectionStatus.NOMINATION
                and self.nomination_start and self.nomination_end
                and self.nomination_start <= now <= self.nomination_end)

    @property
    def is_voting_open(self):
        now = datetime.utcnow()
        return (self.status == ElectionStatus.VOTING
                and self.voting_start and self.voting_end
                and self.voting_start <= now <= self.voting_end)

    @property
    def total_votes_cast(self):
        return Vote.query.filter(
            Vote.election_id == self.id
        ).count()

    def __repr__(self):
        return f"<Election {self.id}: {self.title} [{self.status.value}]>"


# ─────────────────────────────────────────
# ELECTION POSITION  (President, Secretary …)
# ─────────────────────────────────────────

class ElectionPosition(db.Model):
    __tablename__ = "election_positions"

    id          = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id"), nullable=False)
    title       = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    max_winners = db.Column(db.Integer, default=1)

    election    = db.relationship("Election", back_populates="positions")

    def __repr__(self):
        return f"<Position {self.title} (Election {self.election_id})>"


# ─────────────────────────────────────────
# VOTE
# ─────────────────────────────────────────

class Vote(db.Model):
    __tablename__ = "votes"
    __table_args__ = (
        db.UniqueConstraint("election_id", "position_id", "voter_id",
                            name="uq_vote_per_position"),
    )

    id            = db.Column(db.Integer, primary_key=True)
    election_id   = db.Column(db.Integer, db.ForeignKey("elections.id"),          nullable=False)
    position_id   = db.Column(db.Integer, db.ForeignKey("election_positions.id"), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey("leadership_application.id"), nullable=False)
    voter_id      = db.Column(db.Integer, db.ForeignKey("user.id"),              nullable=False)
    cast_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    application   = db.relationship("LeadershipApplication", back_populates="votes")
    voter         = db.relationship("User", foreign_keys=[voter_id])

    def __repr__(self):
        return f"<Vote voter={self.voter_id} application={self.application_id}>"


# ─────────────────────────────────────────
# ELIGIBILITY HELPERS
# ─────────────────────────────────────────

def _is_final_year_student(user):
    """
    Helper to guess if a student is in their final year based on their reg_no.
    Example: S13/07803/22 -> admission year 2022.
    Assuming a 4-year degree, if current_year - 2022 >= 3, they are in their final year.
    """
    if not user.registration_number:
        return False  # Can't determine, assume not final year
        
    parts = user.registration_number.split('/')
    if len(parts) == 3 and parts[2].isdigit():
        admission_year = 2000 + int(parts[2])
        current_year = date.today().year
        # If they are in their 4th year (or beyond), consider them final year
        if current_year - admission_year >= 3:
            return True
            
    return False


def check_nomination_eligibility(member, club_id):
    """
    Returns (is_eligible: bool, reason: str)
    Rules: active member of the club AND NOT in final year of study
    """
    membership = ClubMembership.query.filter_by(
        user_id=member.id, club_id=club_id, status='active'
    ).first()

    if not membership:
        return False, "You are not an active member of this club."

    if _is_final_year_student(member):
        return False, "Final year students are not eligible to stand for election."
        
    return True, "Eligible"


def check_voting_eligibility(voter, election):
    """
    Returns (can_vote: bool, reason: str)
    Rule: any active member of the election's club can vote.
    """
    membership = ClubMembership.query.filter_by(
        user_id=voter.id, club_id=election.club_id, status='active'
    ).first()

    if not membership:
        return False, "You are not an active member of this club."

    return True, "Eligible"

@event.listens_for(Club, "before_update")
def auto_evaluate_status(mapper, connection, target):
    target.evaluate_status()



# ─────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────

class AuditStatus(PyEnum):
    DRAFT     = "draft"      # saved but not yet submitted
    SUBMITTED = "submitted"  # awaiting dean review
    UNDER_REVIEW = "under_review"  # dean has opened it
    APPROVED  = "approved"   # dean approved
    REJECTED  = "rejected"   # dean rejected → leader must resubmit


class AuditPeriod(PyEnum):
    Q1          = "Q1"           # Jan–Mar
    Q2          = "Q2"           # Apr–Jun
    Q3          = "Q3"           # Jul–Sep
    Q4          = "Q4"           # Oct–Dec
    ANNUAL      = "Annual"
    SEMESTER_1  = "Semester 1"
    SEMESTER_2  = "Semester 2"


# ─────────────────────────────────────────
# AUDIT REPORT
# ─────────────────────────────────────────

class AuditReport(db.Model):
    __tablename__ = "audit_report"
    __table_args__ = (
        # Only one APPROVED or SUBMITTED audit per club per period per year
        db.UniqueConstraint(
            "club_id", "period", "year",
            name="uq_audit_club_period_year"
        ),
    )

    id          = db.Column(db.Integer, primary_key=True)

    # Which club this audit belongs to
    club_id     = db.Column(db.Integer, db.ForeignKey("club.id"), nullable=False)

    # Who submitted it (a club leader / club_leader role)
    submitted_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # ── Audit period ──────────────────────────────────────
    period      = db.Column(db.Enum(AuditPeriod), nullable=False)
    year        = db.Column(db.Integer, nullable=False)   # e.g. 2025

    # ── Status ────────────────────────────────────────────
    status      = db.Column(
        db.Enum(AuditStatus),
        default=AuditStatus.DRAFT,
        nullable=False
    )

    # ── Audit content fields ──────────────────────────────
    # Membership
    total_members           = db.Column(db.Integer, default=0)
    active_members          = db.Column(db.Integer, default=0)
    new_members             = db.Column(db.Integer, default=0)
    members_left            = db.Column(db.Integer, default=0)

    # Events
    events_held             = db.Column(db.Integer, default=0)
    events_planned          = db.Column(db.Integer, default=0)
    average_attendance      = db.Column(db.Float,   default=0.0)

    # Finances
    opening_balance         = db.Column(db.Float, default=0.0)
    total_income            = db.Column(db.Float, default=0.0)
    total_expenditure       = db.Column(db.Float, default=0.0)
    closing_balance         = db.Column(db.Float, default=0.0)
    fees_collected          = db.Column(db.Float, default=0.0)
    outstanding_fees        = db.Column(db.Float, default=0.0)

    # Compliance documents present at time of audit
    has_constitution        = db.Column(db.Boolean, default=False)
    has_patron_letter       = db.Column(db.Boolean, default=False)
    has_meeting_minutes     = db.Column(db.Boolean, default=False)
    elections_held          = db.Column(db.Boolean, default=False)
    financial_report_filed  = db.Column(db.Boolean, default=False)

    # Free-text sections
    achievements            = db.Column(db.Text, nullable=True)
    challenges              = db.Column(db.Text, nullable=True)
    recommendations         = db.Column(db.Text, nullable=True)
    additional_notes        = db.Column(db.Text, nullable=True)

    # ── Submission / review timestamps ────────────────────
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at  = db.Column(db.DateTime, nullable=True)
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                              onupdate=lambda: datetime.now(timezone.utc))

    # ── Dean review ───────────────────────────────────────
    reviewed_by   = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at   = db.Column(db.DateTime, nullable=True)
    review_note   = db.Column(db.Text,    nullable=True)  # required on rejection

    # ── Generated report path (set after approval) ────────
    report_file   = db.Column(db.String(300), nullable=True)
    report_generated_at = db.Column(db.DateTime, nullable=True)

    # ── Revision tracking ─────────────────────────────────
    # How many times was this report resubmitted after rejection?
    revision_number = db.Column(db.Integer, default=1)

    # ── Relationships ─────────────────────────────────────
    club      = db.relationship("Club", backref="audit_reports")
    submitter = db.relationship("User", foreign_keys=[submitted_by])
    reviewer  = db.relationship("User", foreign_keys=[reviewed_by])

    # ── Computed helpers ──────────────────────────────────

    @property
    def net_balance(self):
        return self.total_income - self.total_expenditure

    @property
    def compliance_checklist(self):
        """Returns a dict of compliance items and their boolean state."""
        return {
            "Constitution on file":        self.has_constitution,
            "Patron letter on file":        self.has_patron_letter,
            "Meeting minutes recorded":     self.has_meeting_minutes,
            "Elections held this period":   self.elections_held,
            "Financial report filed":       self.financial_report_filed,
        }

    @property
    def compliance_score(self):
        checks = self.compliance_checklist
        passed = sum(1 for v in checks.values() if v)
        return int((passed / len(checks)) * 100)

    @property
    def label(self):
        return f"{self.period.value} {self.year} Audit — {self.club.name}"

    def __repr__(self):
        return f"<AuditReport {self.id}: {self.label} [{self.status.value}]>"


class LeadershipApplication(db.Model):
    __tablename__ = "leadership_application"

    id           = db.Column(db.Integer, primary_key=True)
    student_id   = db.Column(db.Integer, db.ForeignKey("user.id"),  nullable=False)
    club_id      = db.Column(db.Integer, db.ForeignKey("club.id"),   nullable=False)
    position     = db.Column(db.String(50), nullable=False)
        # values: president | vice_president | secretary | treasurer
    motivation   = db.Column(db.Text, nullable=False)
    experience   = db.Column(db.Text, nullable=True)
    goals        = db.Column(db.Text, nullable=True)
    availability = db.Column(db.String(20), nullable=True)
        # values: full | most | limited
    status       = db.Column(db.String(20), default="pending")
        # values: pending | approved | rejected
    review_note  = db.Column(db.Text, nullable=True)
    photo_url    = db.Column(db.String(300), nullable=True)
    reviewed_by  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at  = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    student  = db.relationship("User", foreign_keys=[student_id], backref="leadership_applications")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    club     = db.relationship("Club", backref="leadership_applications")
    votes    = db.relationship("Vote", back_populates="application", cascade="all, delete-orphan")

    @property
    def vote_count(self):
        return len(self.votes)


# -----------------------------
# ANNOUNCEMENTS
# -----------------------------
class Announcement(db.Model):
    __tablename__ = "announcement"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    
    # Target audience: all, student, club_leader, admin
    target_audience = db.Column(db.String(50), default="all")

    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", foreign_keys=[author_id])

    @property
    def is_active(self):
        if self.expires_at:
            return datetime.utcnow() < self.expires_at
        return True

    def __repr__(self):
        return f"<Announcement {self.title}>"

