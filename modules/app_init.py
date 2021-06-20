# commands for translate update
# pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot .
# pybabel update -i messages.pot -d translations
# pybabel compile -d translations

from flask import Flask, request
from flask_babel import Babel
from flask_session import Session

from .app_config import Config
# from app_config import Config

# ----------------------- APP INIT -----------------------
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config.from_object(Config)

babel = Babel(app)
Session(app)

DEBUG = app.config['DEBUG']


# ----------------------- SET DEFAULT LANG -----------------------
@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(['en', 'ru'])
