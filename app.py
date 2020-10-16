
# pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot .
# pybabel update -i messages.pot -d translations
# pybabel compile -d translations

import logging
import os
import uuid
import spotipy
import sys

from start_settings import app, db, scheduler, User
from flask_migrate import Migrate
from flask_session import Session
from flask import session, request, redirect, render_template, url_for, flash, jsonify, json
from flask_babel import Babel, gettext
from functools import wraps
from dotenv import load_dotenv

DEBUG = True

# objects
migrate = Migrate(app, db)
babel = Babel(app)
Session(app)


import tasks


logging.basicConfig(filename='logs.log', level=logging.INFO)

def auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_manager = spotipy.oauth2.SpotifyOAuth(cache_path=session_cache_path())
        if not auth_manager.get_cached_token():
            return redirect('/')
        get_user = tasks.UserSettings(auth_manager)
        return func(UserSettings = get_user)
    return wrapper


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


def db_commit() -> None:
    global db
    try:
        db.session.commit()
    except:
        print('Database commit returned error:\n')
        err = sys.exc_info()
        for e in err:
            print(e)


@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(['en', 'ru'])


@app.route('/', methods=['POST', 'GET'])
def index():
    menu = [
        {'url': url_for('currently_playing'), 'title': gettext('Recently played tracks')},
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
   
    UserSettings = tasks.UserSettings(auth_manager)
    # ЗАПУСК
    spotify = UserSettings.spotify
    session_user_id = spotify.current_user()['id']
    

    # вычислятор времени
    time_difference = UserSettings.time_worker()

    # settings
    UserSettings.settings_worker()

    # POST запросы
    if request.method == "POST":
        if 'create_playlist' in request.form:
            spotify.user_playlist_create(
                user=session_user_id, 
                name='History (fresh!)', 
                description='Listening history. Created by SpotiBoi'
                )

        if 'detach_playlist' in request.form:
            query = UserSettings.new_query()
            query.history_id = None
            query.update = False
            db_commit()

        if 'uriInput' in request.form:
            query = UserSettings.new_query()
            data = request.form.get('uriInput')
            # если рандом текст какой-то
            if "spotify:playlist:" not in data:
                flash('Wrong URI', category='alert-danger')
            else:
                data = data.replace('spotify:playlist:', '')
                if ' ' in data:
                    data = data.replace(' ', '')
                if spotify.playlist_is_following(data, [query.spotify_id])[0]:
                    query.history_id = data
                    db.session.commit()
                    flash('Success!', category='alert-success')
                else:
                    flash(
                        'You are not playlist creator or you are not following it', category='alert-danger')

    # поиск плейлиста
    history_playlist_data = UserSettings.attach_playlist()

    # CRON
    updateChecked = UserSettings.check_worker_status()

    return render_template(
        'index.html', 
        username=spotify.me()["display_name"],
        menu=menu,
        updateChecked=updateChecked,
        history_playlist_data=history_playlist_data,
        time_difference=time_difference,
        settings=UserSettings.settings
    )
@app.route('/faq')
def faq():
    return render_template('faq.html')


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
@auth
def currently_playing(UserSettings):
    '''Start here'''
    results = UserSettings.spotify.current_user_recently_played(limit=15)
    currently_played = [
        item['track']
        for i, item in enumerate(results['items'])
    ]
    #for i, item in enumerate(results['items']):
    #    currently_played.append(item['track'])
    return render_template('recent.html', bodytext=currently_played)


@app.route('/make_history', methods=['POST'])
@auth
def make_history(UserSettings):
    user = UserSettings.new_query()
    response = tasks.update_history(user.spotify_id, user.history_id, UserSettings.spotify)
    return jsonify({'response': response})


@app.route('/update_settings', methods=['POST'])
@auth
def update_settings(UserSettings):
    if request.method == "POST":
        user = UserSettings.new_query()
        
        user.fixed_dedup = return_db_value(request.form['dedupStatus'], request.form['dedupValue'])
        user.fixed_capacity = return_db_value(request.form['fixedStatus'], request.form['fixedValue'])
        if user.update_time != request.form['updateTimeValue']:
            user.update_time = request.form['updateTimeValue']
            # если работа работается, но uuid не совпадает
            if user.job_id in scheduler:
                scheduler.cancel(user.job_id)
                db.session.commit()
                UserSettings.create_job()
            else:
                db.session.commit()

        return jsonify({'response': gettext('Success!')})
    else:
        return jsonify({'response': gettext('bruh')})

def return_db_value(var_status, var_value):
    if var_status == "true":
        return var_value
    if var_status == 'false':
        return None
    


@app.route('/auto_update', methods=['POST'])
@auth
def auto_update(UserSettings):
        user = UserSettings.new_query()

        try:
            if request.form['update'] == 'true':
                user.update = True
                if not user.job_id or user.job_id not in scheduler:
                    UserSettings.create_job()
            elif request.form['update'] == 'false':
                user.update = False
                if user.job_id in scheduler:
                    scheduler.cancel(user.job_id)
            db.session.commit()
            return jsonify({'response': gettext('Success!')})
        except:
            return jsonify({'response': gettext('bruh')})


@app.route('/logs')
@auth
def open_logs(UserSettings):
    user = UserSettings.new_query()
    if UserSettings.user_id == "21ymkhpptvowil6ku5ljhvbua":
        output = []
        jobs_and_times = scheduler.get_jobs(with_times=True)
        output.append(jobs_and_times)
        with open('logs.log', encoding='utf-8') as file:
            for row in file:
                output.append(row)
    else:
        output = ["no data"]

    return render_template('logs.html', bodytext=output)


@app.route('/logs/clear')
def clear_logs():
    with open('logs.log', 'w'):
        pass
    return gettext('Success!')


def get_user_query_by_id(session_user_id):
    query = User.query.filter_by(spotify_id=session_user_id).first()
    if not query:
        db.session.add(User(spotify_id=session_user_id, update=False))
        db.session.commit()
        query = User.query.filter_by(spotify_id=session_user_id).first()
    return query


if __name__ == '__main__':
    app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
