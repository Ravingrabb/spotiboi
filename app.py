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
import rq_scheduler_dashboard


import spotipy
import uuid
import dotenv
import os
import time
from datetime import datetime
import logging



#создаём приложуху
app = Flask(__name__)

#Конфиги
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

basedir = os.path.abspath(os.path.dirname(__file__))

SQLALCHEMY_MIGRATE_REPO = os.path.join(basedir, 'db_repository')
if os.environ.get('DATABASE_URL') is None:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database.db'
else:
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(80), unique=True, nullable=False)
    update = db.Column(db.Boolean,unique=False, nullable=False)
    history_id = db.Column(db.String(80), unique=True, nullable=True)
    update_time = db.Column(db.Integer, nullable=True)
    last_update = db.Column(db.String(80), nullable=True)
    job_id = db.Column(db.String(80), nullable=True)

    def __repr__(self):
        return '<User %r>' % self.id

import tasks
#расписания
scheduler = Scheduler(connection=Redis()) # Get a scheduler for the "default" queue

#сессии
Session(app)  
#логи
logging.basicConfig(filename='logs.log', level=logging.INFO)
#иниц. БД

#создание кэша для авторизации
caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)

#специальный скрипт для того, чтобы вытаскивать логины и пасс из файла envgit rm --cached <file-name> 
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

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

    try:
        if not auth_manager.get_cached_token():
        # Step 2. Display sign in link when no token
            auth_url = auth_manager.get_authorize_url()
            return render_template('start.html', auth_url=auth_url)
    except spotipy.SpotifyException:
        return redirect('/sign_out')

    # Step 4. Signed in, display data

    #ЗАПУСК
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    addictional_info=None
    session_user_id = spotify.current_user()['id']
    user = get_user_query_by_id(session_user_id)

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

        if 'de-attach_playlist' in request.form:
            user.history_id = None
            db.session.commit()


    #поиск плейлиста
    history_playlist_data = {
            'name' : None,
            'id' : None,
            'images': None
        }

    #просматриваем плейлисты и находим нужный
    #is_following = spotify.playlist_is_following(user.history_id, [session_user_id])[0]
    find_playlist(spotify, user, history_playlist_data)

 
    #CRON
    if user.update == True and history_playlist_data['name'] and user.history_id:
        updateChecked = "checked"
        if not user.job_id or user.job_id not in scheduler:
            job = scheduler.schedule(datetime.utcnow(), tasks.update_history, args=[user.spotify_id, user.history_id, spotify], interval=1800, repeat=None)
            scheduler.enqueue_job(job)
            user.job_id = job.id
            db.session.commit()
    else:
        updateChecked = None
        try:
            if user.job_id in scheduler:
                scheduler.cancel(user.job_id)
        except:
            pass
            
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

def find_playlist(spotify, user, history_playlist_data):
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

def attach_playlist(spotify, user):
    #создаётся заготовок пустого плейлиста
    history_playlist_data = {
            'name' : None,
            'id' : None,
            'images': None
        }
    #посмотреть все плейлисты юзера
    try:
        #сморим все плейлисты
        playlists = spotify.current_user_playlists()
        #если привязан ID плейлиста и юзер подписан на него, то выводим инфу
        if user.history_id and spotify.playlist_is_following(user.history_id, [user.spotify_id])[0]:
            current_playlist = spotify.playlist(user.history_id, fields="name, id, images")
            history_playlist_data['name'] = current_playlist['name']
            history_playlist_data['id'] = current_playlist['id']
            history_playlist_data['images'] = current_playlist['images'][0]['url']
        # если ID плейлиста привязан, но юзер не подписан на плейлист
        elif user.history_id and not spotify.playlist_is_following(user.history_id, [user.spotify_id])[0]:
            user.history_id = None
            db.session.commit()
        # если ID плейлиста не привязан, например если только что создали плейлист History через спотибой
        elif not user.history_id:
            for idx, item in enumerate(playlists['items']):
                if item['name'] == "History":
                    history_playlist_data['name'] = item['name']
                    history_playlist_data['id'] = item['id']
                    image_item = item['images']
                if image_item:
                    history_playlist_data['images'] = image_item[0]['url']
    except:
        app.logger.info(user.spotify_id + ': Плейлист не прикреплён, нечего показывать')
    finally:
        return history_playlist_data
        
@app.route('/test')
def test_drive():
    menu = [
    {'url' : url_for('currently_playing'),'title' : 'recently played'},
    ]
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')

    #ЗАПУСК
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    addictional_info=None
    session_user_id = spotify.current_user()['id']
    user = get_user_query_by_id(session_user_id)

    time_difference = time_worker(user)

    #поиск плейлиста

    #просматриваем плейлисты и находим нужный
    #is_following = spotify.playlist_is_following(user.history_id, [session_user_id])[0]
    history_playlist_data = attach_playlist(spotify, user)
            
    return render_template(
        'index.html', 
        username=spotify.me()["display_name"], 
        menu = menu,
        updateChecked = True,
        addictional_info = user,
        history_playlist_data = history_playlist_data,
        time_difference = time_difference
        )


@app.route('/sign_out')
def sign_out():
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(session_cache_path())
        session.clear()
    except OSError as e:
        print ("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/')


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

@app.route('/make_history')
def make_history():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user = get_user_query_by_id(spotify.current_user()['id'])

    tasks.update_history(user.spotify_id, user.history_id, spotify)
    return "Updated"

@app.route('/test')
def test_my_ass():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user = get_user_query_by_id(spotify.current_user()['id'])

    test_job = scheduler.schedule(datetime.utcnow(), tasks.test_task, args=[spotify.current_user()['id']], interval=10, repeat=1)
    scheduler.enqueue_job(test_job)
    return "slolok"

@app.route('/logs')
def open_logs():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user = get_user_query_by_id(spotify.current_user()['id'])
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

def get_user_query_by_id(session_user_id):
    query= User.query.filter_by(spotify_id=session_user_id).first()
    if not query:
        db.session.add(User(spotify_id=session_user_id, update=False))
        db.session.commit()
        query = User.query.filter_by(spotify_id=session_user_id).first()
    return query

if __name__ == '__main__':
	app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
