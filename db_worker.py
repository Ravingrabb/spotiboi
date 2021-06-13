from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import sqlite3
import json

app = Flask(__name__)

app.config.from_object('config')
SQLALCHEMY_DATABASE_URI = 'sqlite:///database.db'
db = SQLAlchemy(app)
conn = sqlite3.connect("database_old.db")

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
    playlist_id = db.Column(db.String(80), unique=True)
    user_id = db.Column(db.String(80), db.ForeignKey('user.spotify_id'))
    
    def __repr__(self):
            return '<UsedPlaylist %r>' % self.playlist_id
        
        
class SmartPlaylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80), db.ForeignKey('user.spotify_id'), unique=True)
    playlist_id = db.Column(db.String(80), unique=True)
    update = db.Column(db.Boolean, default=False)
    update_time = db.Column(db.Integer, default=1440)
    last_update = db.Column(db.String(80))
    job_id = db.Column(db.String(80), default=0)
        
    def __repr__(self):
            return '<SmartPlaylist %r>' % self.playlist_id
        
        
def move_old_database_to_new():
    sql = "SELECT * FROM user"
    
    cursor = conn.cursor()
    cursor.execute(sql)
    
    for data in cursor:
        spotify_id = data[1]
        history_update = data[2]
        history_playlist_id = data[3]
        update_time = data[4]
        last_update = data[5]
        job_id = data[6]
        last_uuid = data[7]
        fixed_capacity = data[8]
        fixed_dedup = data[9]
        lastfm_username = data[10]
        favorite_playlist_id = data[11]
        if favorite_playlist_id:
            favorite_playlist_id = json.loads(favorite_playlist_id)
            favorite_playlist_id = favorite_playlist_id['id']
            
        db.session.add(User(spotify_id = spotify_id, last_uuid = last_uuid, lastfm_username = lastfm_username))
        db.session.add(HistoryPlaylist(user_id = spotify_id, playlist_id = history_playlist_id, update = history_update, update_time = update_time, last_update = last_update, job_id = job_id, fixed_dedup = fixed_dedup, fixed_capacity = fixed_capacity))
        db.session.add(FavoritePlaylist(user_id = spotify_id, playlist_id = favorite_playlist_id))
        db.session.commit()
        
        
def create_blank_smartplaylist_columns():
    sql = "SELECT * FROM user"
    
    cursor = conn.cursor()
    cursor.execute(sql)
    
    for data in cursor:
        db.session.add(SmartPlaylist(user_id = data[1]))
        db.session.commit()

if __name__ == '__main__':
    create_blank_smartplaylist_columns()
    
    
        
        
        
        
        