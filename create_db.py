from cams import create_app
from cams.extensions import db
import cams.models

app = create_app()

with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully.")
