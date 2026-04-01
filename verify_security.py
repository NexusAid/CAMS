from cams import create_app, db
from cams.models import User, PasswordHistory
from sqlalchemy.exc import IntegrityError
import uuid

app = create_app()

with app.app_context():
    # Setup test users
    email1 = f"test_{uuid.uuid4()}@example.com"
    email2 = f"test_{uuid.uuid4()}@example.com"
    
    # Test 1: Multiple NULLs for unique registration number
    print("Test 1: Creating multiple users with None for registration_number...")
    u1 = User(first_name="Null", last_name="One", email=email1, registration_number=None, role="assistant_admin")
    u1.set_password("SecurePass1!")
    db.session.add(u1)
    
    u2 = User(first_name="Null", last_name="Two", email=email2, registration_number=None, role="assistant_admin")
    u2.set_password("SecurePass2!")
    db.session.add(u2)
    
    try:
        db.session.commit()
        print("SUCCESS: Multiple NULL registration numbers allowed.")
    except Exception as e:
        db.session.rollback()
        print("FAILED: Multiple NULL registration numbers rejected:", str(e))

    # Test 2: Cannot reuse old passwords
    print("\nTest 2: Validating PasswordHistory uniqueness rule...")
    u1 = User.query.filter_by(email=email1).first()
    
    # Store old password check
    if u1.check_password_reuse("SecurePass1!"):
        print("SUCCESS: Identified active password reuse.")
    else:
        print("FAILED: Did not identify active password reuse.")
        
    u1.set_password("NewPass2!")
    db.session.commit()
    
    if u1.check_password_reuse("SecurePass1!"):
        print("SUCCESS: Identified historical password reuse from PasswordHistory table.")
    else:
        print("FAILED: Did not identify historical password reuse from PasswordHistory table.")
    
    # Cleanup
    db.session.delete(u1)
    db.session.delete(u2)
    db.session.commit()
    print("\nDone.")

