from cams import create_app
from cams.extensions import db
from cams.models import User, Club, ClubMembership

app = create_app()

with app.app_context():

    db.create_all()

    # -------------------------------
    # CREATE ADMIN USER
    # -------------------------------
    admin_email = "admin@cams.com"
    admin = User.query.filter_by(email=admin_email).first()

    if not admin:
        admin = User(
            first_name="System",
            last_name="Administrator",
            email=admin_email,
            role="admin",
            must_change_password=False
        )
        admin.set_password("1234")
        db.session.add(admin)
        print(f"Admin created: {admin_email} / 1234")
    else:
        print("Admin already exists")

    # -------------------------------
    # CREATE STUDENT USER
    # -------------------------------
    student_reg = "S13/07803/22"
    student = User.query.filter_by(email=student_reg).first()

    if not student:
        student = User(
            first_name="Test",
            last_name="Student",
            email=student_reg,
            role="student"
        )
        student.set_password("password123")
        db.session.add(student)
        print(f"Student user created: {student_reg} / password123")
    else:
        print(f"Student user already exists: {student_reg}")

    db.session.commit()

    # -------------------------------
    # CREATE DEMO CLUB
    # -------------------------------
    club_name = "Demo Club"
    club = Club.query.filter_by(name=club_name).first()

    if not club:
        club = Club(
            name=club_name,
            description="Demo Club for testing leader module",
            status="active"
        )
        db.session.add(club)
        print("Demo Club created")

    db.session.commit()

    # -------------------------------
    # CREATE CLUB LEADER USER
    # -------------------------------
    leader_email = "leader@cams.com"
    leader = User.query.filter_by(email=leader_email).first()

    if not leader:
        leader = User(
            first_name="Club",
            last_name="Leader",
            email=leader_email,
            role="club_leader",
            must_change_password=False
        )
        leader.set_password("leader123")
        db.session.add(leader)
        db.session.commit()
        print(f"Club Leader created: {leader_email} / leader123")

    # Refresh objects
    club = Club.query.filter_by(name=club_name).first()
    leader = User.query.filter_by(email=leader_email).first()

    # -------------------------------
    # ASSIGN LEADER TO CLUB
    # -------------------------------
    membership = ClubMembership.query.filter_by(
        user_id=leader.id,
        club_id=club.id
    ).first()

    if not membership:
        membership = ClubMembership(
            user_id=leader.id,
            club_id=club.id,
            role="president",
            status="active"
        )
        db.session.add(membership)
        db.session.commit()

        print("Leader assigned as President of Demo Club")
    else:
        print("Leader already assigned to club")

    print("All demo users created successfully!")
