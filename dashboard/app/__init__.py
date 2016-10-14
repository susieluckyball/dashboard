from flask import Blueprint
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
# from flask.ext.sqlalchemy import SQLAlchemy
from flask_login import LoginManager

from config import config

main = Blueprint('main', __name__, template_folder='templates')
auth = Blueprint('auth', __name__)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

from . import views

bootstrap = Bootstrap()

# db = None

def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    Bootstrap(app)
    login_manager.init_app(app)
    # global db
    # db = SQLAlchemy(app)

    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix='/auth')
    return app
