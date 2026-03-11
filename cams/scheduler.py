# cams/scheduler.py - FIXED IMPORTS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
import atexit

# Configure logging
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.INFO)

scheduler = None

def init_scheduler(app):
    """Initialize the scheduler with the Flask app context"""
    global scheduler
    
    if scheduler is not None:
        return scheduler
    
    scheduler = BackgroundScheduler(daemon=True)
    
    # Add jobs - NOTE: We're passing the function objects, not calling them
    scheduler.add_job(
        id='daily_compliance_check',
        func=check_club_compliance,
        trigger=CronTrigger(hour=2, minute=0),  # Run daily at 2 AM
        args=[app],
        name='Daily Club Compliance Check',
        replace_existing=True
    )
    
    scheduler.add_job(
        id='weekly_notification_cleanup',
        func=cleanup_old_notifications,
        trigger=CronTrigger(day_of_week='mon', hour=3, minute=0),  # Weekly on Monday at 3 AM
        args=[app],
        name='Weekly Notification Cleanup',
        replace_existing=True
    )
    
    scheduler.add_job(
        id='hourly_pending_check',
        func=check_pending_items,
        trigger='interval',
        minutes=60,  # Run every hour
        args=[app],
        name='Hourly Pending Items Check',
        replace_existing=True
    )
    
    # For development/testing: Run compliance check every 10 minutes
    if app.config.get('DEBUG', False):
        scheduler.add_job(
            id='dev_compliance_check',
            func=check_club_compliance,
            trigger='interval',
            minutes=10,
            args=[app],
            name='Development Compliance Check',
            replace_existing=True
        )
    
    scheduler.start()
    
    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown() if scheduler else None)
    
    print("✅ Scheduler initialized with jobs:")
    for job in scheduler.get_jobs():
        print(f"   - {job.name} (Next run: {job.next_run_time})")
    
    return scheduler

def check_club_compliance(app):
    """Check club compliance - main compliance checker"""
    with app.app_context():
        try:
            # Import inside function to avoid circular imports
            from .models import db, Club, Notification, User, ClubMembership
            from .utils.notifications import send_notification
            
            today = datetime.now()
            clubs = Club.query.filter(Club.status.in_(['active', 'warning'])).all()
            
            print(f"🔍 Running compliance check on {len(clubs)} clubs at {today}")
            
            for club in clubs:
                issues = []
                
                # 1. Check minimum members (20 members required)
                if club.member_count < club.min_members_required:
                    issues.append(f"Insufficient members: {club.member_count}/{club.min_members_required}")
                
                # 2. Check patron exists
                if not club.patron_id:
                    issues.append("No patron assigned")
                
                # 3. Check required documents
                if not club.has_constitution:
                    issues.append("Constitution not uploaded")
                if not club.has_minutes:
                    issues.append("Approval minutes not uploaded")
                if not club.has_patron_letter:
                    issues.append("Patron letter not uploaded")
                
                # 4. Check financial report (annual)
                if club.last_financial_report:
                    days_since_report = (today - club.last_financial_report).days
                    if days_since_report > 365:
                        issues.append("Annual financial report overdue")
                else:
                    issues.append("No financial report submitted")
                
                # 5. Check elections (annual)
                if club.last_election_date:
                    days_since_election = (today - club.last_election_date).days
                    if days_since_election > 365:
                        issues.append("Annual elections overdue")
                else:
                    issues.append("No election records")
                
                # Process issues
                if issues:
                    # Update club status
                    if club.status == 'active':
                        club.status = 'warning'
                        if not club.first_warning_date:
                            club.first_warning_date = today
                        club.last_review_date = today
                    
                    # Send notifications
                    send_compliance_notification(club, issues, app)
                    
                    # Check if should be marked for deregistration (14 days)
                    if club.first_warning_date:
                        days_since_warning = (today - club.first_warning_date).days
                        
                        # Send warnings at intervals
                        warning_intervals = {3: 11, 7: 7, 10: 4, 12: 2, 13: 1}
                        if days_since_warning in warning_intervals:
                            days_left = warning_intervals[days_since_warning]
                            send_notification(
                                title=f"⏰ Deregistration in {days_left} day(s)",
                                message=f"Club '{club.name}' will be automatically deregistered in {days_left} day(s) if issues aren't resolved.",
                                notification_type="deregistration_warning",
                                priority="high",
                                club_id=club.id
                            )
                        
                        # Auto-deregister after 14 days
                        if days_since_warning >= 14 and getattr(club, 'auto_deregister_enabled', True):
                            club.status = 'pending_deregistration'
                            club.pending_deregistration_date = today
                            
                            send_notification(
                                title="🚨 Club Pending Deregistration",
                                message=f"Club '{club.name}' has unresolved compliance issues for 14+ days. Pending admin approval for deregistration.",
                                notification_type="deregistration",
                                priority="urgent",
                                club_id=club.id
                            )
                            
                            # Notify admin
                            admins = User.query.filter_by(is_admin=True).all()
                            for admin in admins:
                                send_notification(
                                    title="Action Required: Club Pending Deregistration",
                                    message=f"Club '{club.name}' is pending deregistration due to 14+ days of non-compliance.",
                                    notification_type="admin_alert",
                                    priority="urgent",
                                    user_id=admin.id
                                )
                
                else:
                    # Club is compliant
                    if club.status == 'warning':
                        club.status = 'active'
                        club.first_warning_date = None
                        club.last_review_date = None
                        
                        send_notification(
                            title="✅ Compliance Restored",
                            message=f"Club '{club.name}' is now compliant with all university regulations.",
                            notification_type="compliance",
                            priority="normal",
                            club_id=club.id
                        )
                
                club.last_compliance_check = today
                db.session.commit()
            
            print(f"✅ Compliance check completed. Checked {len(clubs)} clubs.")
            
        except Exception as e:
            print(f"❌ Error in compliance check: {str(e)}")
            import traceback
            traceback.print_exc()

def send_compliance_notification(club, issues, app):
    """Send compliance issue notifications"""
    with app.app_context():
        from .models import User, ClubMembership
        from .utils.notifications import send_notification
        
        # Get club leaders
        leaders = User.query.join(ClubMembership).filter(
            ClubMembership.club_id == club.id,
            ClubMembership.role.in_(['president', 'secretary', 'treasurer']),
            ClubMembership.status == 'active'
        ).all()
        
        issue_list = "\n• " + "\n• ".join(issues[:5])  # Show first 5 issues
        
        # Notify club leaders
        for leader in leaders:
            send_notification(
                title="⚠️ Compliance Issues Detected",
                message=f"Club '{club.name}' has compliance issues:{issue_list}\n\nPlease address these within 14 days to avoid deregistration.",
                notification_type="compliance",
                priority="high",
                user_id=leader.id,
                club_id=club.id
            )
        
        # Notify patron
        if club.patron_id:
            send_notification(
                title="Club Compliance Warning",
                message=f"As patron, please note compliance issues for club '{club.name}':{issue_list}",
                notification_type="compliance",
                priority="normal",
                user_id=club.patron_id,
                club_id=club.id
            )

def cleanup_old_notifications(app):
    """Clean up old notifications (older than 90 days)"""
    with app.app_context():
        try:
            from .models import db, Notification
            
            cutoff_date = datetime.now() - timedelta(days=90)
            old_notifications = Notification.query.filter(
                Notification.created_date < cutoff_date,
                Notification.is_read == True
            ).all()
            
            count = len(old_notifications)
            for notification in old_notifications:
                db.session.delete(notification)
            
            db.session.commit()
            print(f"🧹 Cleaned up {count} old notifications")
            
        except Exception as e:
            print(f"❌ Error cleaning up notifications: {str(e)}")

def check_pending_items(app):
    """Check for pending items that need attention"""
    with app.app_context():
        try:
            from .models import db, Club, Notification, User
            from .utils.notifications import send_notification
            
            # Check clubs pending approval
            pending_clubs = Club.query.filter_by(status='pending').count()
            
            # Check clubs pending deregistration
            pending_dereg = Club.query.filter_by(status='pending_deregistration').count()
            
            # Notify admin if there are pending items
            if pending_clubs > 0 or pending_dereg > 0:
                admins = User.query.filter_by(is_admin=True).all()
                for admin in admins:
                    send_notification(
                        title="📋 Pending Items Review",
                        message=f"You have {pending_clubs} club(s) pending approval and {pending_dereg} club(s) pending deregistration.",
                        notification_type="reminder",
                        priority="normal",
                        user_id=admin.id
                    )
            
            print(f"⏰ Pending check: {pending_clubs} clubs pending, {pending_dereg} pending deregistration")
            
        except Exception as e:
            print(f"❌ Error in pending check: {str(e)}")