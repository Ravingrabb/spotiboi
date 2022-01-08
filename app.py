import spotipy
import uuid

from modules import *
import userdata
import pages
from workers import tasks, smart_playlist
from workers.autoupdate_worker import create_job

from flask import session, request, redirect, render_template, jsonify, make_response
from flask_babel import gettext
from functools import wraps

auth_scopes = 'playlist-modify-private playlist-read-private playlist-modify-public playlist-read-collaborative ' \
              'user-read-recently-played user-library-read  ugc-image-upload '


def get_session_cache_path():
    if not session.get('uuid'):
        if request.cookies.get('uuid'):
            session['uuid'] = request.cookies.get('uuid')
        else:
            session['uuid'] = str(uuid.uuid4())

    caches_folder = './.spotify_caches/'
    if not os.path.exists(caches_folder):
        os.makedirs(caches_folder)

    return caches_folder + session['uuid']


def get_auth_manager():
    cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=get_session_cache_path())
    auth_manager = spotipy.oauth2.SpotifyOAuth(scope=auth_scopes,
                                               cache_handler=cache_handler,
                                               show_dialog=True,
                                               )
    return auth_manager


# декоратор проверки авторизации
def auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if get_session_cache_path():
            auth_manager = get_auth_manager()
            token = auth_manager.get_cached_token()
            if not token:
                return redirect('/')
            if auth_manager.is_token_expired(token):
                auth_manager.refresh_access_token(token['refresh_token'])
                
            get_user = userdata.UserSettings(auth_manager)
            return func(UserSettings=get_user)
        else:
            return redirect('/')

    return wrapper


# ---------------PAGES START HERE-------------------
@app.route('/', methods=['POST', 'GET'])
def index():
    # Step 1. Visitor is unknown, give random ID

    auth_manager = get_auth_manager()
    if not auth_manager.get_cached_token():
        session['uuid'] = str(uuid.uuid4())
        auth_manager = get_auth_manager()

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

    UserSettings = userdata.UserSettings(auth_manager)
    return pages.index_page(UserSettings)


@app.route('/test2')
@auth
def test2(UserSettings):
    from rq import Queue
    q = Queue('update_history', connection=Redis())
    return str(q.count)


@app.route('/test')
@auth
def test(UserSettings):
    auth_manager = UserSettings.spotify.auth_manager
    token = auth_manager.cache_handler.get_cached_token()
    auth_manager.validate_token(token['refresh_token'])
    return token

@app.route('/debug')
@auth
def debug(UserSettings):
    return pages.debug_page(UserSettings)


@app.route('/donate')
def donate():
    return render_template('donate.html')


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/sign_out')
def sign_out():
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(get_session_cache_path())
        session.clear()
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/')


@app.route('/currently_playing')
@auth
def currently_playing(UserSettings):
    """Start here"""
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
        user_playlists = smart_playlist.sort_playlist(get_user_playlists(UserSettings))
        return render_template('create_smart.html', user_playlists=user_playlists)
    else:
        return redirect('/')


@app.route('/smart_settings', methods=['POST', 'GET'])
@auth
def smart_settings(UserSettings):
    return pages.smart_settings_page(UserSettings)


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
    if UserSettings.smart_query.job_id or UserSettings.smart_query in scheduler_s:
        restart_job_with_new_settings(UserSettings, UserSettings.smart_query, tasks.update_smart_playlist, scheduler_s)
    return jsonify({'response': response})


@app.route('/update_settings', methods=['POST'])
@auth
def update_settings(UserSettings):
    return pages.update_settings_post(UserSettings)


@app.route('/auto_update', methods=['POST'])
@auth
def auto_update(UserSettings):
    history_query = UserSettings.history_query
    try:
        if request.form['update'] == 'true':
            history_query.update = True
            if not history_query.job_id or history_query.job_id not in scheduler_h:
                create_job(UserSettings, history_query, tasks.update_history, scheduler_h)
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
                create_job(UserSettings, favorite_query, tasks.update_favorite_playlist, scheduler_f)
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
                create_job(UserSettings, smart_query, tasks.update_smart_playlist, scheduler_s)
        elif request.form['update'] == 'false':
            smart_query.update = False
            if smart_query.job_id in scheduler_s:
                scheduler_s.cancel(smart_query.job_id)
        db.session.commit()
        return jsonify({'response': gettext('Success!')})
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
        exclude_artists = decode_to_bool(request.form['excludeArtists'])
        # exclude_tracks = tasks.decode_to_bool(request.form['excludeTracks'])
        if 'addUrlToSmart' in request.form:
            try:
                smart_playlist.add_playlists_to_smart(request.form['addUrlToSmart'], UserSettings, exclude_artists)
                return jsonify({'response': 'OK'})
            except:
                return jsonify({'response': None})
    else:
        return jsonify({'response': None})


# ------------------- DON'T CROSS THE LINE :) -------------------
if __name__ == '__main__':
    app.run(threaded=True, debug=DEBUG, host='0.0.0.0')
