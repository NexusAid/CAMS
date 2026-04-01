import click
from flask.cli import with_appcontext
from datetime import datetime, timedelta
from cams.extensions import db
from cams.models import ClubMembership, AuditReport, Election, Event, User, Club, Notification
from cams.utils.email_service import send_email

@click.group()
def reminders():
    """Commands for sending system reminders."""
    pass

@reminders.command()
@with_appcontext
def send_all():
    """Send all daily reminders."""
    click.echo("Starting reminder jobs...")
    
    send_membership_reminders()
    send_audit_reminders()
    send_election_reminders()
    send_event_reminders()
    
    click.echo("Finished reminder jobs.")

def send_membership_reminders():
    """Remind club leaders about pending memberships sitting for > 3 days."""
    click.echo("Checking pending memberships...")
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    
    # Get all pending memberships older than 3 days
    pending = ClubMembership.query.filter(
        ClubMembership.status == 'pending',
        ClubMembership.join_date <= three_days_ago
    ).all()
    
    # Group by club
    clubs_with_pending = {}
    for req in pending:
        if req.club_id not in clubs_with_pending:
            clubs_with_pending[req.club_id] = 0
        clubs_with_pending[req.club_id] += 1
        
    for club_id, count in clubs_with_pending.items():
        club = Club.query.get(club_id)
        if not club: continue
        
        # Find active leaders
        leaders = ClubMembership.query.filter(
            ClubMembership.club_id == club_id,
            ClubMembership.role.in_(['president', 'secretary']),
            ClubMembership.status == 'active'
        ).all()
        
        for leader_mem in leaders:
            leader = leader_mem.user
            if not leader.email: continue
            
            subject = f"Action Required: {count} Pending Memberships for {club.name}"
            body = f"Hello {leader.first_name},\n\nYou have {count} pending membership applications for {club.name} that have been waiting for over 3 days.\nPlease log in to the CAMS dashboard to review and approve them.\n\nBest Regards,\nCAMS System"
            try:
                send_email(leader.email, subject, body)
                click.echo(f"  Sent reminder to {leader.email} for {club.name}")
            except Exception as e:
                click.echo(f"  Failed to send to {leader.email}: {e}")

def send_audit_reminders():
    """Remind club leaders about overdue audits or due soon audits."""
    click.echo("Checking audit reminders...")
    # This requires specific logic depending on your periods, e.g., end of semester.
    # For now, let's remind if there are draft audits that haven't been submitted
    # and were created more than 14 days ago.
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    
    drafts = AuditReport.query.filter(
        AuditReport.status == 'draft',
        AuditReport.created_at <= fourteen_days_ago
    ).all()
    
    for report in drafts:
        club = report.club
        leaders = ClubMembership.query.filter(
            ClubMembership.club_id == club.id,
            ClubMembership.role.in_(['president', 'treasurer']),
            ClubMembership.status == 'active'
        ).all()
        
        for leader_mem in leaders:
            if not leader_mem.user.email: continue
            subject = f"Reminder: Submit {report.period.value} {report.year} Audit for {club.name}"
            body = f"Hello {leader_mem.user.first_name},\n\nYour audit report '{report.label}' is still in draft state. Please complete and submit it as soon as possible to remain compliant.\n\nBest Regards,\nCAMS System"
            try:
                send_email(leader_mem.user.email, subject, body)
                click.echo(f"  Sent audit reminder to {leader_mem.user.email}")
            except Exception as e:
                click.echo(f"  Failed audit reminder to {leader_mem.user.email}: {e}")

def send_election_reminders():
    """Remind students about opening/closing elections."""
    click.echo("Checking election reminders...")
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    
    # Elections closing tomorrow
    closing_soon = Election.query.filter(
        Election.status == 'voting',
        Election.voting_end > now,
        Election.voting_end <= tomorrow
    ).all()
    
    for election in closing_soon:
        # Notify all active members of the club who haven't voted yet
        # (A real implementation would filter out those who already voted)
        members = ClubMembership.query.filter_by(club_id=election.club_id, status='active').all()
        for mem in members:
            if not mem.user.email: continue
            subject = f"Urgent: Voting Closes Soon for {election.title}!"
            body = f"Hello {mem.user.first_name},\n\nThe voting period for '{election.title}' closes in less than 24 hours. If you haven't voted yet, please log in and cast your vote.\n\nBest Regards,\nCAMS System"
            try:
                send_email(mem.user.email, subject, body)
            except Exception:
                pass

def send_event_reminders():
    """Remind students of events happening tomorrow."""
    click.echo("Checking upcoming events...")
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    day_after = now + timedelta(days=2)
    
    upcoming_events = Event.query.filter(
        Event.date >= tomorrow,
        Event.date < day_after
    ).all()
    
    for event in upcoming_events:
        members = ClubMembership.query.filter_by(club_id=event.club_id, status='active').all()
        for mem in members:
            if not mem.user.email: continue
            subject = f"Reminder: {event.title} is Tomorrow!"
            body = f"Hello {mem.user.first_name},\n\nJust a reminder that {event.club.name}'s event '{event.title}' is happening tomorrow at {event.date.strftime('%I:%M %p')} in {event.location}.\n\nSee you there!\n\nBest Regards,\nCAMS System"
            try:
                send_email(mem.user.email, subject, body)
            except Exception:
                pass

def register_cli_commands(app):
    app.cli.add_command(reminders)
