
# pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot .
# pybabel update -i messages.pot -d translations
# pybabel compile -d translations

# flask db migrate -m "users table"
# flask db upgrade

import os
import uuid
from requests.cookies import create_cookie
import spotipy
import sys
import pylast
from sqlalchemy.orm import query

from start_settings import app, db, scheduler_h, scheduler_f
from flask_migrate import Migrate
from flask_session import Session
from flask import session, request, redirect, render_template, url_for, flash, jsonify, make_response
from flask_babel import Babel, gettext
from functools import wraps
from dotenv import load_dotenv
# test
from transliterate import detect_language
import objgraph
import gc

DEBUG = True

# objects
migrate = Migrate(app, db)
babel = Babel(app)
Session(app)

import tasks

auth_scopes = 'playlist-modify-private user-read-recently-played playlist-modify-public user-library-read'

# декоратор для авторизации

def session_cache_path():
    try:
        return caches_folder + session['uuid']
    except:
        return caches_folder + request.cookies.get('uuid')
    

# создание кэша для авторизации
caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)

# специальный скрипт для того, чтобы вытаскивать логины и пасс из файла envgit rm --cached <file-name>
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


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


# ---------------PAGES START HERE-------------------

@app.route('/', methods=['POST', 'GET'])
def index():
    if not session.get('uuid'):
        # Step 1. Visitor is unknown, give random ID
        if request.cookies.get('uuid'):
            session['uuid'] = request.cookies.get('uuid')
        else:
            session['uuid'] = str(uuid.uuid4())
    
    auth_manager = spotipy.oauth2.SpotifyOAuth(scope=auth_scopes,
                                               cache_path=caches_folder + session['uuid'],
                                               show_dialog=True)

    if request.args.get("code"):
        # Step 3. Being redirected from Spotify auth page
        auth_manager.get_access_token(request.args.get("code"), as_dict=False)
        return redirect('/create_cookie')
    try:
        if not auth_manager.get_cached_token():
            # Step 2. Display sign in link when no token
            auth_url = auth_manager.get_authorize_url()
            return render_template('start.html', auth_url=auth_url)
    except spotipy.SpotifyException:
        return redirect('/sign_out')

    # Step 4. Signed in, display data
    
    # ------------------ НАЧАЛО НАСТРОЕК СТРАНИЦЫ ------------------
    UserSettings = tasks.UserSettings(auth_manager)
    menu = [
        {'url': url_for('currently_playing'), 'title': gettext('Recently played tracks')},
        {'url': url_for('faq'), 'title': 'FAQ'},
    ]
    spotify = UserSettings.spotify

    # settings
    UserSettings.settings_worker()

    # POST запросы
    if request.method == "POST":
        if 'create_playlist' in request.form:
            if not UserSettings.history_query.playlist_id:
                spotify.user_playlist_create(
                    user=UserSettings.user_id, 
                    name='History (fresh!)', 
                    description='Listening history. Created by SpotiBoi'
                    )


        if 'detach_playlist' in request.form:
            history_query = UserSettings.history_query
            history_query.playlist_id = None
            history_query.update = False
            db.session.commit()

        if 'uriInput' in request.form:
            history_query = UserSettings.history_query
            user_query = UserSettings.user_query
            data = request.form.get('uriInput')
            # если рандом текст какой-то
            if "spotify:playlist:" not in data:
                flash('Wrong URI', category='alert-danger')
            else:
                data = data.replace('spotify:playlist:', '')
                if ' ' in data:
                    data = data.replace(' ', '')
                if spotify.playlist_is_following(data, [user_query.spotify_id])[0]:
                    history_query.playlist_id = data
                    db.session.commit()
                    flash('Success!', category='alert-success')
                else:
                    flash(
                        'You are not playlist creator or you are not following it', category='alert-danger')

    # поиск плейлиста
    history_playlist_data = UserSettings.attach_playlist()
    
    # CRON
    history_checked = tasks.check_worker_status(UserSettings, UserSettings.history_query, tasks.update_history, scheduler_h)
    favorite_checked = tasks.check_worker_status(UserSettings, UserSettings.favorite_query, tasks.update_favorite_playlist, scheduler_f)
    # вычислятор времени
    time_difference = UserSettings.time_worker()
    
    gc.collect()
    

    
    return render_template(
        'index.html', 
        username=spotify.me()["display_name"],
        menu=menu,
        history_checked = history_checked,
        favorite_checked = favorite_checked,
        history_playlist_data = history_playlist_data,
        time_difference = time_difference,
        settings = UserSettings.settings
    )
    
def auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_manager = spotipy.oauth2.SpotifyOAuth(scope=auth_scopes,
                                               cache_path=session_cache_path(),
                                               show_dialog=True)
        if not auth_manager.get_cached_token():
            return redirect('/')
        get_user = tasks.UserSettings(auth_manager)
        return func(UserSettings = get_user)
    return wrapper

    
@app.route('/test2')
@auth
def test2(UserSettings):
    API_KEY = os.environ['LASTFM_API_KEY']
    API_SECRET = os.environ['LASTFM_API_SECRET']
    username = "Ravingrabb"

    network = pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET,
                               username=username)
    result = network.get_user(username).get_recent_tracks(limit=45)
    
    # достаём данные из lastfm
    data_with_duplicates = [
        {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
        for song in result
    ]
    
    last_fm_data = []
    for song in data_with_duplicates:
        if song not in last_fm_data:
            last_fm_data.append(song)
    
    # переводим эти данные в uri спотифай
    test = []
    for q in last_fm_data:
        # 1 попытка: проверка как есть
        lang = detect_language(q['artist'])
        try:
            if lang != 'ru':
                track = UserSettings.spotify.search(f"\"{q['name']}\" artist:{q['artist']} album:\"{q['album']}\"", limit=1, type="track")['tracks']['items'][0]
            else:
                track = UserSettings.spotify.search(f"\"{q['name']}\" album:\"{q['album']}\"", limit=1, type="track")['tracks']['items'][0]
            test.append(f"{q['name']} - {q['artist']} - ({q['album']})  ---  {str(track['name'])} - {str(track['artists'][0]['name'])} - ({str(track['album']['name'])})")
        except Exception as e:
            continue
            
    test.append(str(len(test)))

    return render_template('test.html', queries=test)
        
    
@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/leak')
def leak():
    objgraph.show_most_common_types(limit=5)
    print (objgraph.by_type('function')[0])
    print('________________')
    return "pizdec"


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
    results = UserSettings.spotify.current_user_recently_played(limit=30)
    currently_played = [
        [item['track'], UserSettings.spotify.track(item['track']['id'])]
        for i, item in enumerate(results['items'])
    ]
    
    return render_template('recent.html', bodytext=currently_played)


@app.route('/logs')
@auth
def open_logs(UserSettings):
    if UserSettings.user_id == "21ymkhpptvowil6ku5ljhvbua":
        output = []
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


@app.route('/create_cookie')
def create_cookie():
    resp = make_response(render_template('cookie.html'))
    resp.set_cookie('uuid', session.get('uuid'))
    return resp


# --------------- ONLY POST PAGES -----------------

@app.route('/make_history', methods=['POST'])
@auth
def make_history(UserSettings):
    response = tasks.update_history(UserSettings.user_id, UserSettings)
    return jsonify({'response': response})


@app.route('/make_liked', methods=['POST'])
@auth
def make_liked(UserSettings):
    tasks.update_favorite_playlist(UserSettings.user_id, UserSettings)   
    return jsonify({'response': "OK"})


@app.route('/update_settings', methods=['POST'])
@auth
def update_settings(UserSettings):
    if request.method == "POST":
        user_query = UserSettings.user_query
        history_query = UserSettings.history_query
        
        def check_lastfm_username():
            API_KEY = "b6d8eb5b11e5ea1e81a3f116cfa6169f"
            API_SECRET = "7108511ff8fee65ba231fba99902a1d5"
            network = pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET,
                               username=user_query.lastfm_username)
            
            try:
                lastfm_user = network.get_user(user_query.lastfm_username)
                lastfm_user.get_name(properly_capitalized=True)
            except:
                user_query.lastfm_username = None
                db.session.commit()
                return jsonify({'error': gettext("Error! Can't find that last.fm user")})
            
        def return_db_value(var_status, var_value):
            '''Функция проверяет статус настройки. Если true, то значение переходи в БД.
            Если false, то в бд присваивается None '''
            if var_status == "true":
                return var_value
            if var_status == 'false':
                return None 
    
        # прогоняем все данные из настроек
        history_query.fixed_dedup = return_db_value(request.form['dedupStatus'], request.form['dedupValue'])
        history_query.fixed_capacity = return_db_value(request.form['fixedStatus'], request.form['fixedValue'])
        user_query.lastfm_username = return_db_value(request.form['lastFmStatus'], request.form['lastFmValue'])
        
        if user_query.lastfm_username:
            check_lastfm_username()
            
            
        if history_query.update_time != request.form['updateTimeValue']:
            history_query.update_time = request.form['updateTimeValue']
            # если работа работается, но uuid не совпадает
            if history_query.job_id in scheduler_h:
                scheduler_h.cancel(history_query.job_id)
                db.session.commit()
                tasks.create_job(UserSettings, history_query, tasks.update_history, scheduler_h)
            else:
                db.session.commit()

        return jsonify({'response': gettext('Success!')})
    else:
        return jsonify({'response': gettext('bruh')})


@app.route('/auto_update', methods=['POST'])
@auth
def auto_update(UserSettings):
        history_query = UserSettings.history_query
        try:
            if request.form['update'] == 'true':
                history_query.update = True
                if not history_query.job_id or history_query.job_id not in scheduler_h:
                    tasks.create_job(UserSettings, history_query, tasks.update_history, scheduler_h)
            elif request.form['update'] == 'false':
                history_query.update = False
                if history_query.job_id in scheduler_h:
                    scheduler_h.cancel(history_query.job_id)
            db.session.commit()
            return jsonify({'response': gettext('Success!')})
        except:
            return jsonify({'response': gettext('bruh')})
        
        
@app.route('/auto_update_favorite', methods=['POST'])
@auth
def auto_update_favorite(UserSettings):
        favorite_query = UserSettings.favorite_query
        
        try:
            if request.form['update'] == 'true':
                favorite_query.update = True
                if not favorite_query.job_id or favorite_query.job_id not in scheduler_f:
                    tasks.create_job(UserSettings, favorite_query, tasks.update_favorite_playlist, scheduler_f)
            elif request.form['update'] == 'false':
                favorite_query.update = False
                if favorite_query.job_id in scheduler_f:
                    scheduler_f.cancel(favorite_query.job_id)
            db.session.commit()
            return jsonify({'response': gettext('Success!')})
        except:
            return jsonify({'response': gettext('bruh')})


@app.route('/get_time', methods=['POST'])
@auth
def get_time(UserSettings):
    try:
        return jsonify({'response': UserSettings.time_worker()})
    except:
        return jsonify({'response': gettext('bruh')})


if __name__ == '__main__':
    app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
