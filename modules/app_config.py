import os
from dotenv import load_dotenv

DEV_FLAG = True
basedir = os.path.abspath(os.path.dirname(__file__))


def _env_load(path):
    dotenv_path = os.path.join(basedir, path)
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path, override=True)


class Config(object):
    SECRET_KEY = os.urandom(64)
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '../.flask_session/'
    BABEL_DEFAULT_LOCALE = 'en'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_MIGRATE_REPO = os.path.join(basedir, 'db_repository')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///../database.db'
    if DEV_FLAG:
        DEBUG = True
        _env_load('../.env-beta')
    else:
        DEBUG = False
        _env_load('../.env')
