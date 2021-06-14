# flask db migrate -m "users table"
# flask db upgrade

from modules.app_init import app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../database.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(80), unique=True, nullable=False)
    last_uuid = db.Column(db.String(80), nullable=True)
    lastfm_username = db.Column(db.String(80), nullable=True)

    def __repr__(self):
        return '<User %r>' % self.spotify_id


class HistoryPlaylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80), db.ForeignKey('user.spotify_id'))
    playlist_id = db.Column(db.String(80), unique=True)
    update = db.Column(db.Boolean, default=False)
    update_time = db.Column(db.Integer, default=60)
    last_update = db.Column(db.String(80))
    job_id = db.Column(db.String(80), default=0)
    fixed_dedup = db.Column(db.Integer, nullable=True, default=200)
    fixed_capacity = db.Column(db.Integer, nullable=True, default=0)

    def __repr__(self):
        return '<HistoryPlaylist %r>' % self.playlist_id


class FavoritePlaylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80), db.ForeignKey('user.spotify_id'))
    playlist_id = db.Column(db.String(80), unique=True)
    update = db.Column(db.Boolean, default=False)
    update_time = db.Column(db.Integer, default=1440)
    last_update = db.Column(db.String(80))
    job_id = db.Column(db.String(80), default=0)

    def __repr__(self):
        return '<FavoritePlaylist %r>' % self.playlist_id


class UsedPlaylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attached_playlist_id = db.Column(db.String(80), db.ForeignKey('smart_playlist.id'))
    playlist_id = db.Column(db.String(80))
    user_id = db.Column(db.String(80), db.ForeignKey('user.spotify_id'))
    exclude = db.Column(db.Boolean, default=False)
    exclude_artists = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return '<UsedPlaylist %r>' % self.playlist_id


class SmartPlaylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80), db.ForeignKey('user.spotify_id'))
    playlist_id = db.Column(db.String(80), unique=True)
    update = db.Column(db.Boolean, default=False)
    update_time = db.Column(db.Integer, default=1440)
    last_update = db.Column(db.String(80))
    job_id = db.Column(db.String(80), default=0)
    max_tracks = db.Column(db.Integer, default=100)
    exclude_history = db.Column(db.Boolean, default=True)
    exclude_favorite = db.Column(db.Boolean, default=False)
    auto_clean = db.Column(db.Boolean, default=False)
    ac_job_id = db.Column(db.String(80), default=0)

    def __repr__(self):
        return '<SmartPlaylist %r>' % self.playlist_id

