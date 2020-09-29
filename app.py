"""
    python3 -m flask run --port=8080
    NOTE: If receiving "port already in use" error, try other ports: 5000, 8090, 8888, etc...
        (will need to be updated in your Spotify app and SPOTIPY_REDIRECT_URI variable)
"""
from dotenv import load_dotenv
import tasks
import logging
from datetime import datetime
import os
import uuid
import spotipy

from pprint import pprint
from flask_migrate import Migrate
from rq_scheduler import Scheduler
from redis import Redis
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from flask import Flask, session, request, redirect, render_template, url_for, flash, jsonify, json
DEBUG = True


# создаём приложуху
app = Flask(__name__)

# Конфиги
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
migrate = Migrate(app, db)


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


# расписания
# Get a scheduler for the "default" queue
scheduler = Scheduler(connection=Redis())

# сессии
Session(app)
# логи
logging.basicConfig(filename='logs.log', level=logging.INFO)
#иниц. БД

# создание кэша для авторизации
caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)

# специальный скрипт для того, чтобы вытаскивать логины и пасс из файла envgit rm --cached <file-name>
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


def session_cache_path():
    return caches_folder + session.get('uuid')


@app.route('/', methods=['POST', 'GET'])
def index():
    menu = [
        {'url': url_for('currently_playing'), 'title': 'Recently played'},
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

    # ЗАПУСК
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    session_user_id = spotify.current_user()['id']
    user = get_user_query_by_id(session_user_id)

    # вычислятор времени
    time_difference = time_worker(user)

    # settings
    settings = {
        'dedup_status': None,
        'dedup_value': 0,
        'fixed_status': None,
        'fixed_value': 0,
        'update_time': user.update_time
    }
    if user.fixed_dedup and user.fixed_dedup > 0:
        settings['dedup_status'] = 'checked'
        settings['dedup_value'] = user.fixed_dedup
    if user.fixed_capacity and user.fixed_capacity > 0:
        settings['fixed_status'] = 'checked'
        settings['fixed_value'] = user.fixed_capacity

    # POST запросы
    if request.method == "POST":
        if 'create_playlist' in request.form:
            spotify.user_playlist_create(
                user=session_user_id, name='History (fresh!)', description='Listening history. Created by SpotiBoi')

        if 'detach_playlist' in request.form:
            user.history_id = None
            user.update = False
            db.session.commit()

        if 'uriInput' in request.form:
            data = request.form.get('uriInput')
            # если рандом текст какой-то
            if "spotify:playlist:" not in data:
                flash('Wrong URI', category='alert-danger')
            else:
                data = data.replace('spotify:playlist:', '')
                if ' ' in data:
                    data = data.replace(' ', '')
                if spotify.playlist_is_following(data, [user.spotify_id])[0]:
                    user.history_id = data
                    db.session.commit()
                    flash('Success!', category='alert-success')
                else:
                    flash(
                        'You are not playlist creator or you are not following it', category='alert-danger')

    # поиск плейлиста
    history_playlist_data = attach_playlist(spotify, user)

    # CRON
    # если autoupdate = ON
    if user.update == True and user.history_id:
        updateChecked = "checked"
        # если работа не задана или она не в расписании
        if not user.job_id or user.job_id not in scheduler:
            create_job(user, spotify)
        # если работа работается, но uuid не совпадает
        if user.job_id in scheduler and user.last_uuid != session.get('uuid'):
            scheduler.cancel(user.job_id)
            create_job(user, spotify)
            user.last_uuid = session.get('uuid')
            db.session.commit()
    # если autoupdate = OFF
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
        menu=menu,
        updateChecked=updateChecked,
        history_playlist_data=history_playlist_data,
        time_difference=time_difference,
        settings=settings
    )


def time_worker(user):
    if user.last_update:
        time_past = user.last_update
        time_now = datetime.now()
        FMT = '%H:%M:%S'
        duration = time_now - datetime.strptime(time_past, FMT)
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
    # создаётся заготовок пустого плейлиста
    history_playlist_data = {
        'name': None,
        'id': None,
        'images': None
    }
    # посмотреть все плейлисты юзера
    try:
        # сморим все плейлисты
        playlists = spotify.current_user_playlists()
        # если привязан ID плейлиста и юзер подписан на него, то выводим инфу
        if user.history_id and spotify.playlist_is_following(user.history_id, [user.spotify_id])[0]:
            current_playlist = spotify.playlist(
                user.history_id, fields="name, id, images")
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
                if item['name'] == "History (fresh!)":
                    history_playlist_data['name'] = "History"
                    history_playlist_data['id'] = item['id']
                    image_item = item['images']
                if image_item:
                    history_playlist_data['images'] = image_item[0]['url']
            user.history_id = history_playlist_data['id']
            db.session.commit()
            spotify.playlist_change_details(
                history_playlist_data['id'], name="History")
    except:
        app.logger.info(user.spotify_id +
                        ': Плейлист не прикреплён, нечего показывать')
    finally:
        return history_playlist_data


def create_job(user, spotify, job_time=30):
    if user.update_time:
        job_time = int(user.update_time)
    job_time = job_time * 60
    job = scheduler.schedule(datetime.utcnow(), tasks.update_history, args=[
                             user.spotify_id, user.history_id, spotify], interval=job_time, repeat=None)
    scheduler.enqueue_job(job)
    user.job_id = job.id
    db.session.commit()


@app.route('/sign_out')
def sign_out():
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(session_cache_path())
        session.clear()
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
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
        currently_played.append(item['track'])
    return render_template('recent.html', bodytext=currently_played)


@app.route('/make_history', methods=['POST'])
def make_history():
    auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
    if not auth_manager.get_cached_token():
        return redirect('/')
    spotify = spotipy.Spotify(auth_manager=auth_manager)
    user = get_user_query_by_id(spotify.current_user()['id'])

    response = tasks.update_history(user.spotify_id, user.history_id, spotify)

    return jsonify({'response': response})


@app.route('/update_settings', methods=['POST'])
def update_settings():
    if request.method == "POST":
        auth_manager = spotipy.oauth2.SpotifyOAuth(
            cache_path=session_cache_path())
        if not auth_manager.get_cached_token():
            return redirect('/')
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        user = get_user_query_by_id(spotify.current_user()['id'])

        # TODO: удалить, если всё работает
        dedup_status = request.form['dedupStatus']
        dedup_value = request.form['dedupValue']
        fixed_status = request.form['fixedStatus']
        fixed_value = request.form['fixedValue']
        update_time = request.form['updateTimeValue']
        
        user.fixed_dedup = settings_worker(request.form['dedupStatus'], request.form['dedupValue'])
        user.fixed_capacity = settings_worker(request.form['fixedStatus'], request.form['fixedValue'])
        if user.update_time != request.form['updateTimeValue']:
            user.update_time = request.form['updateTimeValue']
            # если работа работается, но uuid не совпадает
            if user.job_id in scheduler:
                scheduler.cancel(user.job_id)
                db.session.commit()
                create_job(user, spotify)
            else:
                db.session.commit()

        return jsonify({'response': "Success!"})
    else:
        return jsonify({'response': "bruh"})

def settings_worker(var_status, var_value):
    if var_status == "true":
        return var_value
    if var_status == 'false':
        return None
    


@app.route('/auto_update', methods=['POST'])
def auto_update():
    if request.method == "POST":
        auth_manager = spotipy.oauth2.SpotifyOAuth(
            cache_path=session_cache_path())
        if not auth_manager.get_cached_token():
            return redirect('/')
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        user = get_user_query_by_id(spotify.current_user()['id'])

        try:
            if request.form['update'] == 'true':
                user.update = True
                if not user.job_id or user.job_id not in scheduler:
                    create_job(user, spotify)
            elif request.form['update'] == 'false':
                user.update = False
                if user.job_id in scheduler:
                    scheduler.cancel(user.job_id)
            db.session.commit()

            return jsonify({'response': "Success!"})
        except:
            return jsonify({'response': "bruh"})


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


@app.route('/logs/clear')
def clear_logs():
    with open('logs.log', 'w'):
        pass
    return 'Success!'


def get_user_query_by_id(session_user_id):
    query = User.query.filter_by(spotify_id=session_user_id).first()
    if not query:
        db.session.add(User(spotify_id=session_user_id, update=False))
        db.session.commit()
        query = User.query.filter_by(spotify_id=session_user_id).first()
    return query


if __name__ == '__main__':
    app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
