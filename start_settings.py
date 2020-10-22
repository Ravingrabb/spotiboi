from flask import Flask
from rq_scheduler import Scheduler
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
import logging
import logging.handlers
from flask_babel import gettext

app = Flask(__name__)

app.config.from_object('config')

db = SQLAlchemy(app)
scheduler = Scheduler(connection=Redis())

#logging.basicConfig(filename='logs.log', level=logging.ERROR)
handler = logging.handlers.RotatingFileHandler(
        'logs.log',
        maxBytes=1024 * 1024)
handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('werkzeug').addHandler(handler)
app.logger.setLevel(logging.ERROR)
app.logger.addHandler(handler)


# flask db migrate -m "users table"
# flask db upgrade
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(80), unique=True, nullable=False)
    update = db.Column(db.Boolean, unique=False, nullable=False)
    history_id = db.Column(db.String(80), unique=True, nullable=True)
    update_time = db.Column(db.Integer, default=60)
    last_update = db.Column(db.String(80), nullable=True)
    job_id = db.Column(db.String(80), nullable=True)
    last_uuid = db.Column(db.String(80), nullable=True)
    fixed_dedup = db.Column(db.Integer, nullable=True, default=100)
    fixed_capacity = db.Column(db.Integer, nullable=True, default=0)
    lastfm_username = db.Column(db.String(80), nullable=True)

    def __repr__(self):
        return '<User %r>' % self.id

