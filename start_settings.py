from flask import Flask
from rq_scheduler import Scheduler
from flask_sqlalchemy import SQLAlchemy
from redis import Redis

app = Flask(__name__)

app.config.from_object('config')

db = SQLAlchemy(app)
scheduler = Scheduler(connection=Redis())

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(80), unique=True, nullable=False)
    update = db.Column(db.Boolean, unique=False, nullable=False)
    history_id = db.Column(db.String(80), unique=True, nullable=True)
    update_time = db.Column(db.Integer, default=30)
    last_update = db.Column(db.String(80), nullable=True)
    job_id = db.Column(db.String(80), nullable=True)
    last_uuid = db.Column(db.String(80), nullable=True)
    fixed_dedup = db.Column(db.Integer, nullable=True, default=100)
    fixed_capacity = db.Column(db.Integer, nullable=True, default=0)

    def __repr__(self):
        return '<User %r>' % self.id
