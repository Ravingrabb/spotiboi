# pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot .
# pybabel update -i messages.pot -d translations
# pybabel compile -d translations

from flask_babel import Babel
from flask import Flask, request

from modules.app_config import *

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config.from_object(Config)
babel = Babel(app)

DEBUG = app.config['DEBUG']


# default lang
@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(['en', 'ru'])
