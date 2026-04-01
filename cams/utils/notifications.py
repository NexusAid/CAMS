# cams/utils/notifications.py
from datetime import datetime
from ..models import db, Notification

def send_notification(title, message, notification_type, priority="normal", user_id=None, club_id=None, link=None):
    """
    Helper function to create and save notifications
    
    Args:
        title: Notification title
        message: Notification message
        notification_type: Type of notification (compliance, registration, etc.)
        priority: Priority level (low, normal, high, urgent)
        user_id: Target user ID (optional)
        club_id: Associated club ID (optional)
        link: Clickable action link (optional)
    """
    notification = Notification(
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        user_id=user_id,
        club_id=club_id,
        link=link,
        created_date=datetime.now(),
        is_read=False
    )
    
    db.session.add(notification)
    db.session.commit()
    
    return notification