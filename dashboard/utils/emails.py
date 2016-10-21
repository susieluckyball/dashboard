from email.mime.text import MIMEText
import smtplib

from dashboard.configuration import conf 


SMTP_SERVER = conf.get('smtp', 'mail_server')
SMTP_PORT = int(conf.get('smtp', 'mail_port'))
SMTP_FROM = conf.get('smtp', 'mail_from')

# TODO:
# should have a better email util...
def send_email(subject, to, body): 
    s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    msg = MIMEText(body)
    msg["Subject"] = subject 
    msg["From"] = SMTP_FROM

    if isinstance(to, list):
        to = ", ".join(to)
        recipients = to
    else:
        recipients = [to]
    msg["To"] = to
    try:
        s.sendmail(SMTP_FROM, recipients, msg.as_string())
    finally:
        s.quit()
