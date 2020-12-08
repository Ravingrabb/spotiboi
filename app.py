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

from start_settings import UsedPlaylist, app, db, scheduler_h, scheduler_f, scheduler_s
import smart_playlist

from flask_migrate import Migrate
from flask_session import Session
from flask import session, request, redirect, render_template, url_for, flash, jsonify, make_response
from flask_babel import Babel, gettext
from functools import wraps
from dotenv import load_dotenv
# test
import objgraph
import gc

DEBUG = 0

# objects
migrate = Migrate(app, db)
babel = Babel(app)
Session(app)

import tasks

auth_scopes = 'playlist-modify-private playlist-read-private playlist-modify-public playlist-read-collaborative user-read-recently-played user-library-read  ugc-image-upload'

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
                data = spotify.user_playlist_create(
                    user = UserSettings.user_id, 
                    name = 'History', 
                    description = 'Listening history. Created by SpotiBoi'
                    )
                UserSettings.history_query.playlist_id = data['id']
                db.session.commit()

        # TODO: проверить и перенести на отдельную страницу
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
    history_playlist_data = UserSettings.attach_playlist(UserSettings.history_query, scheduler_h)
    smart_playlist_data = UserSettings.attach_playlist(UserSettings.smart_query, scheduler_s)
    
    # CRON
    history_checked = tasks.check_worker_status(UserSettings, UserSettings.history_query, tasks.update_history, scheduler_h)
    favorite_checked = tasks.check_worker_status(UserSettings, UserSettings.favorite_query, tasks.update_favorite_playlist, scheduler_f)
    smart_checked = tasks.check_worker_status(UserSettings, UserSettings.smart_query, tasks.update_smart_playlist, scheduler_s)
    # вычислятор времени
    time_difference = UserSettings.time_worker()
    
    gc.collect()
    
    return render_template(
        'index.html', 
        username=spotify.me()["display_name"],
        menu=menu,
        history_checked = history_checked,
        favorite_checked = favorite_checked,
        smart_checked = smart_checked,
        history_playlist_data = history_playlist_data,
        smart_playlist_data = smart_playlist_data,
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
def test2():
    test = [1,2,3]
    test.pop(3)
    return render_template('test.html')

@app.route('/debug')
@auth
def debug(UserSettings):
    return UserSettings.user_id
        
@app.route('/donate')
def donate():
    return render_template('donate.html')       
 
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
    return redirect('/logs')


@app.route('/create_cookie')
def create_cookie():
    resp = make_response(render_template('cookie.html'))
    resp.set_cookie('uuid', session.get('uuid'))
    return resp

@app.route('/create_smart')
@auth
def create_smart(UserSettings):
    if not UserSettings.smart_query.playlist_id:
        user_playlists = smart_playlist.sort_playlist(UserSettings.get_user_playlists())
        return render_template('create_smart.html', user_playlists = user_playlists)
    else:
        return redirect('/')
    

@app.route('/smart_settings', methods=['POST', 'GET'])
@auth
def smart_settings(UserSettings):
    if UserSettings.smart_query.playlist_id:
        #POST
        if request.method == "POST":
            if 'unpinID' in request.form:
                id = request.form['unpinID']
                try:
                    UsedPlaylist.query.filter_by(user_id = UserSettings.user_id, playlist_id = id).delete()
                    db.session.commit()
                    return jsonify({'response': 'OK'})
                except Exception as e:
                    app.logger.error(e)
                    return jsonify({'response': None})
                
            # НАСТРОЙКИ POST
            # MAX
            if 'capacity' in request.form:
                UserSettings.smart_query.max_tracks = request.form['capacity']
            # EXCLUDE
            if 'excludeHistorySwitch' in request.form:
                result = tasks.decode_to_bool(request.form['excludeHistorySwitch'])
                UserSettings.smart_query.exclude_history = result
            else:
                pass
                UserSettings.smart_query.exclude_history = 0
            if 'excludeFavoriteSwitch' in request.form:
                result = tasks.decode_to_bool(request.form['excludeFavoriteSwitch'])
                UserSettings.smart_query.exclude_favorite = result
            else:
                UserSettings.smart_query.exclude_favorite = 0
            # TIME
            UserSettings.smart_query.update_time = tasks.days_to_minutes(request.form['updateTime'])
            
            if UserSettings.smart_query.job_id in scheduler_s:
                    scheduler_s.cancel(UserSettings.smart_query.job_id)
                    
            db.session.commit()
            return redirect('/')
    
        # сбор уже прикреплённых плейлистов на добавление  
        pl_ids = UsedPlaylist.query.filter_by(user_id = UserSettings.user_id, exclude = False, exclude_artists = False).all()
        playlist_data = UserSettings.get_several_playlists_data(pl_ids)
        
        # сбор инфы об оставшихся, не прикреплённых плейлистах
        user_pl = smart_playlist.sort_playlist(UserSettings.get_user_playlists())
        main_attached_playlists = smart_playlist.get_main_attached_ids(UserSettings)
        user_playlists = [item for item in user_pl if item['id'] not in tasks.get_items_by_key(playlist_data, 'id') and item['id'] not in main_attached_playlists]
        
        UserSettings.settings_worker()

        return render_template('smart_settings.html', 
                               used_playlists = playlist_data, 
                               user_playlists = user_playlists,
                               settings = UserSettings.settings)
    else:
        return redirect('/')
    


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


@app.route('/make_smart', methods=['POST'])
@auth
def make_smart(UserSettings):
    response = tasks.update_smart_playlist(UserSettings.user_id, UserSettings)   
    return jsonify({'response': response})


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
        
        
@app.route('/auto_update_smart', methods=['POST'])
@auth
def auto_update_smart(UserSettings):
        smart_query = UserSettings.smart_query
        
        try:
            if request.form['update'] == 'true':
                smart_query.update = True
                if not smart_query.job_id or smart_query.job_id not in scheduler_s:
                    tasks.create_job(UserSettings, smart_query, tasks.update_smart_playlist, scheduler_s)
            elif request.form['update'] == 'false':
                smart_query.update = False
                if smart_query.job_id in scheduler_s:
                    scheduler_s.cancel(smart_query.job_id)
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

@app.route('/postworker', methods=['POST'])
@auth
def postworker(UserSettings):
    
    def detach_playlist(query):
        query.playlist_id = None
        query.update = False
        db.session.commit()
        
    if 'detach_playlist' in request.form:
            history_query = UserSettings.history_query
            detach_playlist(history_query) 
    elif 'detach_smart_playlist' in request.form:
            smart_query = UserSettings.smart_query
            detach_playlist(smart_query)
    return redirect('/')

@app.route('/playlist_worker', methods=['POST'])
@auth
def playlist_worker(UserSettings):
    # проверяльщик на существование
    if 'url' in request.form:
            output = smart_playlist.check_and_get_pldata(request.form['url'], UserSettings)
            if output:
                return jsonify({'response': output})
            else:
                return jsonify({'response': None})
            
    # создание smart плейлиста, если его нет
    if not UserSettings.smart_query.playlist_id:
        if 'urlArray' in request.form:
            try:
                smart_playlist.create_new_smart_playlist(request.form['urlArray'], UserSettings)
                return jsonify({'response': 'OK'})
            except Exception as e:
                app.logger.error(e)
                return jsonify({'response': None})
    # если плейлист существует
    elif UserSettings.smart_query.playlist_id:
        if 'addUrlToSmart' in request.form:
            try:
                smart_playlist.add_playlists_to_smart(request.form['addUrlToSmart'], UserSettings)
                return jsonify({'response': 'OK'})
            except:
                return jsonify({'response': None})
    else:
        return jsonify({'response': None})


########### DON'T CROSS THE LINE :)
if __name__ == '__main__':
    app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
