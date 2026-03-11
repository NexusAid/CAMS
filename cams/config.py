from datetime import timedelta


class Config:
    SECRET_KEY = "your-secret-key"

    SQLALCHEMY_DATABASE_URI = "sqlite:///cams.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ⏱ Auto-logout after 3 minutes of inactivity
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=3)

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