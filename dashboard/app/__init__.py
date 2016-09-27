from flask import Blueprint
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask.ext.bootstrap import Bootstrap
from flask.ext.sqlalchemy import SQLAlchemy

from config import config

main = Blueprint('main', __name__, template_folder='templates')
from . import views

bootstrap = Bootstrap()
db = None

def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    global bootstrap, db
    bootstrap.init_app(app)
    db = SQLAlchemy(app)

    app.register_blueprint(main)
    return app
