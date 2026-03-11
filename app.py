from cams import create_app
from flask_mail import Message
from cams.extensions import mail

app = create_app()

@app.route("/test-email")
def test_email():

    msg = Message(
        subject="CAMS Email Test",
        recipients=["nexusaidtechnologies@gmail.com"]
    )

    msg.body = "Your CAMS email system is working!"

    mail.send(msg)

    return "Email Sent!"


if __name__ == "__main__":
    app.run(debug=True)