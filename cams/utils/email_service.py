import smtplib
from email.mime.text import MIMEText

EMAIL_USER = "nexusaidtechnologies@gmail.com"
EMAIL_PASS = "tgcg hmbn trjw ddoo"

def send_email(receiver, subject, body):

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = receiver

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.sendmail(EMAIL_USER, receiver, msg.as_string())
    server.quit()