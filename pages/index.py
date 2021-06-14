import gc
import uuid
import spotipy
from datetime import datetime, timedelta
from flask import session, request, redirect, render_template, url_for, flash
from flask_babel import gettext

from modules import *
import tasks
import smart_playlist

auth_scopes = 'playlist-modify-private playlist-read-private playlist-modify-public playlist-read-collaborative ' \
              'user-read-recently-played user-library-read  ugc-image-upload '


def get_session_cache_path():
    caches_folder = './.spotify_caches/'
    if not os.path.exists(caches_folder):
        os.makedirs(caches_folder)

    return caches_folder + session['uuid']


def index_page():
    #TODO исправить работу, убрать куки
    if not session.get('uuid'):
        # Step 1. Visitor is unknown, give random ID
        if request.cookies.get('uuid'):
            session['uuid'] = request.cookies.get('uuid')
        else:
            session['uuid'] = str(uuid.uuid4())

    auth_manager = spotipy.oauth2.SpotifyOAuth(scope=auth_scopes,
                                               cache_path=get_session_cache_path(),
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
                    user=UserSettings.user_id,
                    name='History',
                    description='Listening history. Created by SpotiBoi'
                )
                UserSettings.history_query.playlist_id = data['id']
                db.session.commit()

        # TODO: проверить и перенести на отдельную страницу
        if 'detach_playlist' in request.form:
            history_query = UserSettings.history_query
            history_query.playlist_id = None
            history_query.update = False
            db.session.commit()

        # проверка и прикрепление плейлиста истории
        if 'uriInput' in request.form:
            history_query = UserSettings.history_query
            user_query = UserSettings.user_query
            data = smart_playlist.is_exist(request.form.get('uriInput'), UserSettings)
            if data:
                playlist_owner_uri = UserSettings.spotify.playlist(data)['owner']['uri']
                current_user_uri = UserSettings.spotify.me()['uri']
                if spotify.playlist_is_following(data, [user_query.spotify_id])[0] and playlist_owner_uri == current_user_uri:
                    history_query.playlist_id = data
                    db.session.commit()
                    flash(gettext('Success!'), category='alert-success')
                else:
                    flash(gettext('You are not playlist creator or you are not following it'), category='alert-danger')
            else:
                flash(gettext('Wrong URI'), category='alert-danger')

    # поиск плейлиста
    history_playlist_data = UserSettings.attach_playlist(UserSettings.history_query, scheduler_h)
    smart_playlist_data = UserSettings.attach_playlist(UserSettings.smart_query, scheduler_s)

    # CRON
    history_checked = tasks.check_worker_status(UserSettings, UserSettings.history_query, tasks.update_history,
                                                scheduler_h)
    favorite_checked = tasks.check_worker_status(UserSettings, UserSettings.favorite_query,
                                                 tasks.update_favorite_playlist, scheduler_f)
    smart_checked = tasks.check_worker_status(UserSettings, UserSettings.smart_query, tasks.update_smart_playlist,
                                              scheduler_s)
    tasks.auto_clean_checker(UserSettings, scheduler_a)
    # вычислятор времени
    history_time_diff = tasks.time_worker2(UserSettings.history_query)
    time_difference = tasks.time_converter(minutes=history_time_diff)

    # smart
    try:
        # прошло времени
        job = scheduler_s.job_class.fetch(UserSettings.smart_query.job_id, connection=Redis())
        diff = datetime.now() - job.started_at
        diff_minutes = round((diff.days * 24 * 60) + (diff.seconds / 60)) - 180
        # время до след. задачи
        smart_query = UserSettings.new_smart_query()
        next_job_diff = (job.started_at + timedelta(minutes=smart_query.update_time)) - datetime.now()
        next_job_diff_minutes = round((next_job_diff.days * 24 * 60) + (next_job_diff.seconds / 60)) + 180
    except:
        diff_minutes = None
        next_job_diff_minutes = None

    smart_time_difference = [tasks.time_converter(minutes=diff_minutes),
                             tasks.time_converter(minutes=next_job_diff_minutes)]

    gc.collect()

    return render_template(
        'index.html',
        username=spotify.me()["display_name"],
        menu=menu,
        history_checked=history_checked,
        favorite_checked=favorite_checked,
        smart_checked=smart_checked,
        history_playlist_data=history_playlist_data,
        smart_playlist_data=smart_playlist_data,
        time_difference=time_difference,
        smart_time_difference=smart_time_difference,
        settings=UserSettings.settings
    )
