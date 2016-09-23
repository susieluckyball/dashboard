from flask import Blueprint
from flask import Flask
from flask.ext.bootstrap import Bootstrap


from flask.ext.sqlalchemy import SQLAlchemy
from celery import Celery
from config import config, Config


main = Blueprint('main', __name__, template_folder='templates')

bootstrap = Bootstrap()
db = SQLAlchemy()
celery = Celery(__name__, broker=Config.CELERY_BROKER_URL,
                backend=Config.CELERY_RESULT_BACKEND)

from . import views

def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    global bootstrap, db, celery
    bootstrap.init_app(app)
    db.init_app(app)
    celery.conf.update(app.config)

    app.register_blueprint(main)
    return app

