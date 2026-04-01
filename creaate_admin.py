from cams import create_app
from cams.extensions import db
from cams.models import User, Club, ClubMembership

app = create_app()

with app.app_context():

    db.create_all()

    # -------------------------------
    # ADMIN USER
    # -------------------------------
    admin_email = "nexusaidtechnologies@gmail.com"

    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            first_name="NexusAid",
            last_name="Admin",
            email=admin_email,
            role="admin",
            is_active=True,
            must_change_password=False
        )
        admin.set_password("password1234")
        db.session.add(admin)
        print("Admin created")

    # -------------------------------
    # CLUB LEADER
    # -------------------------------
    leader_email = "keyobrah20@gmail.com"

    leader = User.query.filter_by(email=leader_email).first()
    if not leader:
        leader = User(
            first_name="Gachema",
            last_name="Brian",
            email=leader_email,
            registration_number="S12/07804/25",
            role="club_leader",
            is_active=True
        )
        leader.set_password("millionaire123")
        db.session.add(leader)
        print("Leader created")

    # -------------------------------
    # STUDENTS
    # -------------------------------
    students_data = [
        ("Brian", "Ngunyi", "S13/07803/22", "keyobrah11@gmail.com"),
        ("Dorinn", "Ooyi", "E12/04435/24", "keyobrah3@gmail.com"),
        ("Ke", "Yobrah", "S13/07772/22", "keyobrah47@gmail.com"),
    ]

    for first, last, reg_no, email in students_data:
        user = User.query.filter_by(registration_number=reg_no).first()

        if not user:
            user = User(
                first_name=first,
                last_name=last,
                email=email,
                registration_number=reg_no.upper(),
                role="student",
                is_active=True
            )
            user.set_password("brayoh254")
            db.session.add(user)
            print(f"Student created: {first} {last}")
        else:
            print(f"Student already exists: {first} {last}")

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
        db.session.commit()
        print("Club created")

    # -------------------------------
    # ASSIGN LEADER TO CLUB
    # -------------------------------
    leader = User.query.filter_by(email=leader_email).first()
    club = Club.query.filter_by(name=club_name).first()

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
        print("Leader assigned to club")

    print("✅ Setup complete!")