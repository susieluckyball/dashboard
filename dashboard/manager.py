import os
from flask_script import Manager
import logging

from app import create_app

hdler = logging.handlers.RotatingFileHandler('dashboard.log', maxBytes=20000, backupCount=1)
hdler.setLevel(logging.INFO)
app = create_app(os.getenv('FLASK_CONFIG') or 'default')
app.logger.addHandler(hdler)
manager = Manager(app)

@manager.command
def dummy():
    print("hello")

if __name__ == "__main__":
    manager.run()