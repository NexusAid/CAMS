from datetime import timedelta

import os

class Config:
    SECRET_KEY = "your-secret-key"

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    
    SQLALCHEMY_DATABASE_URI = "sqlite:///cams.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ⏱ Auto-logout after 60 minutes of inactivity
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)

    # -------------------------
    # Email configuration
    # -------------------------
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    MAIL_USERNAME = "nexusaidtechnologies@gmail.com"
    MAIL_PASSWORD = "APP_PASSWORD"

    MAIL_DEFAULT_SENDER = "nexusaidtechnologies@gmail.com"