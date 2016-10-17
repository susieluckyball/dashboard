from email.mime.text import MIMEText
import smtplib

from dashboard.config import config 



SMTP_SERVER = config["default"].MAIL_SERVER
SMTP_PORT = config["default"].MAIL_PORT


# TODO:
# should have a better email util...
def send_email(subject, to_, body, from_='dashboard@hbk.com'):
    s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    msg = MIMEText(body)
    msg["Subject"] = subject 
    msg["From"] = from_

    if isinstance(to_, list):
        to = ", ".join(to_)
        recipients = to_
    else:
        to = to_
        recipients = [to_]
    msg["To"] = to
    try:
        s.sendmail(from_, recipients, msg.as_string())
    finally:
        s.quit()
