import gc
from datetime import timedelta
from flask import request, render_template, url_for, flash
from flask_babel import gettext

from workers import tasks, rq_tasks, smart_playlist
from workers.autoupdate_worker import *
from modules import *


def index_page(UserSettings):
    # ------------------ НАЧАЛО НАСТРОЕК СТРАНИЦЫ ------------------

    menu = [
        {'url': url_for('currently_playing'), 'title': gettext('Recently played tracks')},
        {'url': url_for('faq'), 'title': 'FAQ'},
    ]
    spotify = UserSettings.spotify

    # settings
    UserSettings.get_playlists_settings()

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
                if spotify.playlist_is_following(data, [user_query.spotify_id])[0] \
                        and playlist_owner_uri == current_user_uri:
                    history_query.playlist_id = data
                    db.session.commit()
                    flash(gettext('Success!'), category='alert-success')
                else:
                    flash(gettext('You are not playlist creator or you are not following it'), category='alert-danger')
            else:
                flash(gettext('Wrong URI'), category='alert-danger')

    # поиск плейлиста
    history_playlist_data = get_playlist_data_for_html(UserSettings, UserSettings.history_query, scheduler_h)
    smart_playlist_data = get_playlist_data_for_html(UserSettings, UserSettings.smart_query, scheduler_s)

    # CRON
    history_checked = check_autoupdate_status(UserSettings, UserSettings.history_query,
                                              rq_tasks.update_history_task, scheduler_h)
    favorite_checked = check_autoupdate_status(UserSettings, UserSettings.favorite_query,
                                               rq_tasks.update_favorite_playlist_task, scheduler_f)
    smart_checked = check_autoupdate_status(UserSettings, UserSettings.smart_query,
                                            rq_tasks.update_smart_playlist_task, scheduler_s)
    tasks.auto_clean_checker(UserSettings, scheduler_a)

    # вычислятор времени
    history_time_diff = get_time_from_last_update(UserSettings.history_query)
    time_difference = convert_time_to_string(minutes=history_time_diff)

    # smart
    # TODO: перенести в smart
    try:
        if get_updater_status(UserSettings.smart_query.job_id, scheduler_s):
            # прошло времени
            job = scheduler_s.job_class.fetch(UserSettings.smart_query.job_id, connection=Redis())
            diff = datetime.now() - job.started_at
            diff_minutes = round((diff.days * 24 * 60) + (diff.seconds / 60)) - 180
            # время до след. задачи
            smart_query = UserSettings.new_smart_query()
            next_job_diff = (job.started_at + timedelta(minutes=smart_query.update_time)) - datetime.now()
            next_job_diff_minutes = round((next_job_diff.days * 24 * 60) + (next_job_diff.seconds / 60)) + 180
        else:
            diff_minutes = None
            next_job_diff_minutes = None
    except Exception as e:
        diff_minutes = None
        next_job_diff_minutes = None
        app.logger.error(e)

    smart_time_difference = [convert_time_to_string(minutes=diff_minutes),
                             convert_time_to_string(minutes=next_job_diff_minutes)]

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
        settings=UserSettings.get_playlists_settings()
    )
