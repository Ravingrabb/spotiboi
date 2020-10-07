import os

SECRET_KEY = os.urandom(64)
SESSION_TYPE = 'filesystem'
SESSION_FILE_DIR = './.flask_session/'
SQLALCHEMY_TRACK_MODIFICATIONS = False
BABEL_DEFAULT_LOCALE = 'en'

basedir = os.path.abspath(os.path.dirname(__file__))

SQLALCHEMY_MIGRATE_REPO = os.path.join(basedir, 'db_repository')
if os.environ.get('DATABASE_URL') is None:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database.db'
else:
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
