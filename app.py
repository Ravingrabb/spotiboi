import os
import spotipy
import pylast

from modules import *
from pages.index import get_session_cache_path, auth_scopes
import pages
import smart_playlist
import tasks

from flask import session, request, redirect, render_template, jsonify, make_response
from flask_babel import gettext
from functools import wraps


# декоратор проверки авторизации
def auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if get_session_cache_path():
            auth_manager = spotipy.oauth2.SpotifyOAuth(scope=auth_scopes,
                                                       cache_path=get_session_cache_path(),
                                                       show_dialog=True)
            if not auth_manager.get_cached_token():
                return redirect('/')
            get_user = tasks.UserSettings(auth_manager)
            return func(UserSettings=get_user)
        else:
            return redirect('/')

    return wrapper


# ---------------PAGES START HERE-------------------
@app.route('/', methods=['POST', 'GET'])
def index():
    return pages.index_page()


@app.route('/test2')
@auth
def test2(UserSettings):
    return pages.test_mood_page(UserSettings)


@app.route('/test')
@auth
def test():
    return 0/1


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
        user_playlists = smart_playlist.sort_playlist(UserSettings.get_user_playlists())
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
        tasks.restart_smart_with_new_settings(UserSettings.smart_query, scheduler_s, UserSettings)
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
        history_time_diff = tasks.time_worker2(UserSettings.history_query)
        return jsonify({'response': tasks.time_converter(history_time_diff)})
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
        exclude_artists = tasks.decode_to_bool(request.form['excludeArtists'])
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
    app.run(threaded=True, debug=DEBUG)
