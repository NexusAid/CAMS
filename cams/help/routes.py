from flask import Blueprint, request, jsonify
import re

help_bp = Blueprint("help", __name__)

@help_bp.route("/ask", methods=["POST"])
def ask_ai():
    data = request.get_json()
    question = data.get("question", "").strip().lower()
    
    if not question:
        return jsonify({"error": "Please provide a question."}), 400

    # Extremely comprehensive rule-based matching engine using broad synonyms
    if any(k in question for k in ["register", "sign up", "create account", "new account", "registration", "onboard", "enroll", "make an account", "join the system", "join cams", "get started"]):
        answer = (
            "**Registration & Account Setup:**<br>"
            "1. **Students**: Navigate to the CAMS homepage and click on the **Register** button. You will need your Full Name, Email, and Registration Number (e.g., S13/07803/22).<br>"
            "2. **Club Leaders, Admins, & Dean Staff**: Accounts for leadership and administration are provisioned manually by the Dean of Students office. Please contact system administrators for access."
        )
    elif any(k in question for k in ["login", "log in", "sign in", "password", "auth", "authenticate", "forgot password", "reset password", "change password", "can't access", "locked out"]):
        answer = (
            "**Login & Authentication:**<br>"
            "- Use your registered email address and password on the respective login portal (Student, Club Leader, or Admin).<br>"
            "- **Passwords**: For security, CAMS prevents reusing your previous passwords when changing or resetting them. If you are forced to change your password on first login, follow the prompts."
        )
    elif any(k in question for k in ["club", "create club", "new club", "register club", "society", "association", "group", "organization", "chapter", "dormant", "dormancy", "start a club", "form a club", "new society", "suspend"]):
        answer = (
            "**Club Management & Registration:**<br>"
            "- **Starting a New Club**: Submit an application including the club name, category, and patron details. The system generates a Patron Verification link sent to the chosen patron.<br>"
            "- **Status Lifecycle**: A club starts as `pending`, moves to `active` once approved by admins, and can fall into `warning`, `non_compliant`, `suspended`, or `deregistered` if it fails compliance checks.<br>"
            "- **Dormancy**: A club is marked dormant if it hasn't hosted an event in the last 180 days (6 months)."
        )
    elif any(k in question for k in ["join", "membership", "how to join", "become a member", "participate", "enter club", "enroll in club", "roles", "president", "secretary", "treasurer", "member list", "roster", "add member"]):
        answer = (
            "**Joining a Club & Memberships:**<br>"
            "1. Navigate to **Available Clubs** on the Student Dashboard.<br>"
            "2. Click **Request to Join**. Your request becomes `pending`.<br>"
            "3. A Club Leader (President/Secretary) must approve your application from their portal.<br>"
            "4. **Roles**: Members can hold roles like `member`, `president`, `secretary`, or `treasurer`. To hold a leadership role, you must be elected."
        )
    elif any(k in question for k in ["event", "propose", "activities", "attendance", "meeting", "gathering", "function", "schedule", "calendar", "book", "host", "session", "workshop", "activity"]):
        answer = (
            "**Events & Attendance Tracking:**<br>"
            "- **Proposing Events**: Club Leaders use the Events module to propose activities, including date, location, and budget. Admins review and approve these proposals.<br>"
            "- **Attendance**: Event attendance is tracked by the system. Students can be marked as `attended`, `absent`, or having sent an `apology`.<br>"
            "- **Public Events**: Approved events are showcased on the public Events calendar for all university members to see."
        )
    elif any(k in question for k in ["election", "vote", "nominate", "position", "candidate", "campaign", "voting", "poll", "ballot", "run for office", "elect", "leader"]):
        answer = (
            "**Elections, Nominations & Voting:**<br>"
            "- **Elections Lifecycle**: Elections go through `draft`, `nomination` (open for applications), `review` (Dean approval), `voting` (active voting window), `closed`, and `published` stages.<br>"
            "- **Nominations**: Only active club members can nominate themselves. *Final year students (Year 4+) are not eligible to stand for election.*<br>"
            "- **Voting**: During the active voting window, any active club member can cast exactly one anonymous vote per position. The system calculates winners automatically."
        )
    elif any(k in question for k in ["compliance", "document", "constitution", "minutes", "rules", "regulations", "score", "warning", "non_compliant", "deregistration", "requirements", "guidelines", "bylaws"]):
        answer = (
            "**Club Compliance & Documents:**<br>"
            "- CAMS enforces strict compliance rules. Clubs must maintain at least 20 active members and have an active Patron.<br>"
            "- **Documents Required**: Clubs must upload their Constitution, Meeting Minutes, Patron Letter, Members List, and Rules.<br>"
            "- **Scoring**: The system calculates a live Compliance Score based on these 8 factors. Falling behind results in warnings or deregistration."
        )
    elif any(k in question for k in ["audit", "finance", "money", "report", "budget", "expenses", "income", "funding", "treasury", "funds", "financial", "accounts", "cash"]):
        answer = (
            "**Financial Audits & Reporting:**<br>"
            "- **Submitting Audits**: Club Treasurers or Presidents must submit periodic Financial Reports (Q1, Q2, Annual, etc.) covering Income, Expenses, and active member metrics.<br>"
            "- **Review Process**: Audits move from `draft` to `submitted`, are set to `under_review` by the Dean, and are finally `approved` or `rejected`."
        )
    elif any(k in question for k in ["patron", "sponsor", "advisor", "mentor", "staff advisor", "lecturer in charge", "verification"]):
        answer = (
            "**Patrons:**<br>"
            "- Every club must have a Patron (e.g., a university lecturer or staff member).<br>"
            "- When a club is registered, the system emails the Patron. They use a secure link to accept or reject the nomination. The club cannot be approved without an accepted Patron."
        )
    elif any(k in question for k in ["admin", "approve", "reject", "task", "notification", "dean", "dean of students", "system administrator", "alerts", "messages", "inbox"]):
        answer = (
            "**Admin Operations & Notifications:**<br>"
            "- **Admins & Dean of Students**: Can approve/reject clubs, events, and audits. They manage election workflows and can issue compliance warnings or deregistrations.<br>"
            "- **Tasks**: Admins can assign and track internal system Tasks (`pending`, `in_progress`, `completed`).<br>"
            "- **Notifications**: CAMS automatically sends system notifications regarding application statuses, warnings, and upcoming deadlines."
        )
    elif any(k in question for k in ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "howdy", "hiya", "what's up", "sup"]):
        answer = "Hello! I am your fully integrated CAMS AI Assistant. I know everything about clubs, events, elections, compliance, financial audits, and university policies. How can I help you today?"
    elif any(k in question for k in ["thank", "thanks", "appreciate", "cheers", "good job", "awesome", "great"]):
        answer = "You're very welcome! If you need anything else, I'm always here."
    else:
        answer = (
            "I'm not quite sure how to answer that specific question yet. "
            "However, I am fully trained on all CAMS functionalities. You can ask me about:<br>"
            "- **Accounts:** Registration, Passwords, Logging in, Enrollment<br>"
            "- **Clubs:** Creating societies, Patrons, Compliance, Constitutions<br>"
            "- **Members:** Joining groups, Rosters, Participating<br>"
            "- **Events:** Proposing activities, Meetings, Tracking attendance<br>"
            "- **Elections:** Nominations, Polls, Eligibility, Voting<br>"
            "- **Finances:** Audit reports, Budgets, Treasury"
        )

    return jsonify({"answer": answer})


