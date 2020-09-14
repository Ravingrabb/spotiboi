"""
    python3 -m flask run --port=8080
    NOTE: If receiving "port already in use" error, try other ports: 5000, 8090, 8888, etc...
        (will need to be updated in your Spotify app and SPOTIPY_REDIRECT_URI variable)
"""
DEBUG = True

from flask import Flask, session, request, redirect, render_template, url_for
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
from datetime import timedelta


import spotipy
import uuid
import dotenv
import os
import time
from datetime import datetime
import logging
from jobs import test_shit


#создаём приложуху
app = Flask(__name__)

#SQLalchemy
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
if os.environ.get('DATABASE_URL') is None:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database.db'
else:
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
db = SQLAlchemy(app)
#расписания
scheduler = Scheduler(connection=Redis(host="192.168.0.101")) # Get a scheduler for the "default" queue




#сессии
Session(app)  
#логи
logging.basicConfig(filename='logs.log')
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
#иниц. БД
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(80), unique=True, nullable=False)
    update = db.Column(db.Boolean,unique=False, nullable=False)
    history_id = db.Column(db.String(80), unique=True, nullable=True)
    update_time = db.Column(db.Integer, nullable=True)
    last_update = db.Column(db.String(80), nullable=True)

    def __repr__(self):
        return '<User %r>' % self.id


#создание кэша для авторизации
caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)

#специальный скрипт для того, чтобы вытаскивать логины и пасс из файла envgit rm --cached <file-name> 
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print("Loaded")

def session_cache_path():
    return caches_folder + session.get('uuid')

@app.route('/', methods=['POST', 'GET'])
def index():
    menu = [
    {'url' : url_for('currently_playing'),'title' : 'recently played'},
    ]

    if not session.get('uuid'):
        # Step 1. Visitor is unknown, give random ID
        session['uuid'] = str(uuid.uuid4())

    auth_manager = spotipy.oauth2.SpotifyOAuth(scope='playlist-modify-private user-read-recently-played playlist-modify-public',
                                                cache_path=session_cache_path(), 
                                                show_dialog=True)

    if request.args.get("code"):
    # Step 3. Being redirected from Spotify auth page
        auth_manager.get_access_token(request.args.get("code"))
        return redirect('/')

    if not auth_manager.get_cached_token():
    # Step 2. Display sign in link when no token
        auth_url = auth_manager.get_authorize_url()
        return render_template('start.html', auth_url=auth_url)

    # Step 4. Signed in, display data

    #ЗАПУСК
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    addictional_info=None
    session_user_id = spotify.current_user()['id']
    user = get_user_by_id(session_user_id)

    time_difference = time_worker(user)

    #POST запросы
    if request.method == "POST":
        if 'updateSwitch' in request.form:
            user.update = True
            db.session.commit()
        else:
            user.update = False
            db.session.commit()

        if 'create_playlist' in request.form:
            spotify.user_playlist_create(user = session_user_id, name='History', description='Listening history. Created by SpotiBoi')


    #поиск плейлиста
    history_playlist_data = {
            'name' : None,
            'id' : None,
            'images': None
        }

    
    playlists = spotify.current_user_playlists()
    for idx, item in enumerate(playlists['items']):
        if "History" in item['name']:
            history_playlist_data['name'] = item['name']
            history_playlist_data['id'] = item['id']
            image_item = item['images']
            if image_item:
                history_playlist_data['images'] = image_item[0]['url']
    if not user.history_id or user.history_id != history_playlist_data['id']:    
        user.history_id = history_playlist_data['id']
        db.session.commit()


 
    #CRON
    if user.update == True and history_playlist_data['name']:
        updateChecked = "checked"
        #scheduler.add_job(id = 'update_history_job', func = update_history, args=[user, spotify], trigger = 'interval', minutes=30)
        #scheduler.add_job(id = session_user_id, func = test_shit, args=[user], trigger='cron', second='*/20')
        job2 = scheduler.schedule(datetime.utcnow(), test_shit, interval=10, repeat=5)
        scheduler.enqueue_job(job2)
    else:
        updateChecked = None
        #if scheduler.get_job(session_user_id):
        #    scheduler.remove_job(session_user_id)
            
    return render_template(
        'index.html', 
        username=spotify.me()["display_name"], 
        menu = menu,
        updateChecked = updateChecked,
        addictional_info = user,
        history_playlist_data = history_playlist_data,
        time_difference = time_difference
        )

def time_worker(user):
    if user.last_update:
        time_past = user.last_update
        time_now = datetime.now()
        FMT = '%H:%M:%S'
        duration =  time_now - datetime.strptime(time_past, FMT)
        time_difference = duration.seconds // 60
        return time_difference
    else:
        return None


@app.route('/sign_out')
def sign_out():
    os.remove(session_cache_path())
    session.clear()
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(session_cache_path())
    except OSError as e:
        print ("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/')


@app.route('/playlists')
def playlists():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return spotify.current_user_playlists()


@app.route('/currently_playing')
def currently_playing():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    '''Start here'''
    results = spotify.current_user_recently_played(limit=10)
    currently_played = []
    for i, item in enumerate(results['items']):
            track = item['track']
            currently_played.append(track['name'])
    return render_template('recent.html', bodytext=currently_played)

@app.route('/current_user')
def current_user():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return spotify.current_user()

@app.route('/make_history')
def make_history():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user = get_user_by_id(spotify.current_user()['id'])

    update_history(user, spotify)
    return "Updated"

@app.route('/logs')
def open_logs():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user = get_user_by_id(spotify.current_user()['id'])
    if spotify.current_user()['id'] == "21ymkhpptvowil6ku5ljhvbua":
        output = []
        jobs_and_times = scheduler.get_jobs(with_times=True)
        output.append(jobs_and_times)
        file = open('logs.log', encoding='utf-8')
        for row in file:
            output.append(row)
    else:
        output = ["no data"]
    
    return render_template('logs.html', bodytext=output)



''' Временные скрипты '''
def get_current_history_list(playlist_id, sp):
    results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri)), next")
    tracks = results['items']
    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])

    currentPlaylist = []
    for item in enumerate(tracks):
        track = item[1]['track']
        currentPlaylist.append(track['uri'])
    return currentPlaylist

def get_playlist_tracks(playlist_id, sp):
    results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri)), next")
    tracks = results['items']
    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])
    return tracks

def update_history(user, spotify):
     #создаётся плейлист из го
    history_playlist = get_current_history_list(user.history_id, spotify)
    #вытаскиваются последние прослушанные песни и сравниваются с текущей историей
    results = spotify.current_user_recently_played(limit=30)
    recently_played_uris = []
    try:
        for idx, item in enumerate(results['items']):
            track = item['track']
            if track['uri'] not in history_playlist:
                recently_played_uris.append(track['uri'])
        #если есть новые треки для добавления - они добавляются
        if recently_played_uris:
            recently_played_uris = list(dict.fromkeys(recently_played_uris))
            spotify.playlist_add_items(user.history_id, recently_played_uris)
            app.logger.info(user.spotify_id + ": History updated in " + datetime.strftime(datetime.now(), "%H:%M:%S"))
        #иначе пропускаем
        else:
            app.logger.info(user.spotify_id + ": List is empty. Nothing to update.")
    except spotipy.SpotifyException:
        print("Nothing to add for now")
    finally:
        with db.app.app_context():
            query = User.query.filter_by(spotify_id=spotify.current_user()['id']).first()
            query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
            db.session.commit()


def get_user_by_id(session_user_id):
    user_id = User.query.filter_by(spotify_id=session_user_id).first()
    if not user_id:
        db.session.add(User(spotify_id=session_user_id, update=False))
        db.session.commit()
        user_id = User.query.filter_by(spotify_id=session_user_id).first()
    return user_id




if __name__ == '__main__':
	app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
