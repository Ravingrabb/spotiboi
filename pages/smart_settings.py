import pylast

import modules.common_functions
import workers.playlist_functions
from modules import *
from flask import request, redirect, render_template, jsonify
from flask_babel import gettext

from workers import tasks, smart_playlist
from workers.autoupdate_worker import create_job


def smart_settings_page(UserSettings):
    """ Render smart settings HTML page """
    smart_query = UserSettings.smart_query

    def get_worker_bool(input_name: str):
        return True if input_name in request.form else False

    if UserSettings.smart_query.playlist_id:
        # POST
        try:
            if request.method == "POST":
                if 'unpinID' in request.form:
                    id = request.form['unpinID']
                    try:
                        UsedPlaylist.query.filter_by(user_id=UserSettings.user_id, playlist_id=id).delete()
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

                smart_query.exclude_history = get_worker_bool('excludeHistorySwitch')
                smart_query.exclude_favorite = get_worker_bool('excludeFavoriteSwitch')
                smart_query.auto_clean = get_worker_bool('autoCleanSwitch')

                # TIME
                if UserSettings.smart_query.update_time != modules.common_functions.convert_days_in_minutes(request.form['updateTime']):
                    UserSettings.smart_query.update_time = modules.common_functions.convert_days_in_minutes(request.form['updateTime'])

                    if UserSettings.smart_query.job_id in scheduler_s:
                        scheduler_s.cancel(UserSettings.smart_query.job_id)

                db.session.commit()
                return redirect('/')
        except Exception as e:
            print(e)

        # сбор ATTACHED
        pl_ids = UsedPlaylist.query.filter_by(user_id=UserSettings.user_id, exclude=False, exclude_artists=False).all()
        used_playlists = get_several_playlists_data(UserSettings, pl_ids)

        # сбор EXCLUDED
        ex_ar_ids = UsedPlaylist.query.filter_by(user_id=UserSettings.user_id, exclude=False,
                                                 exclude_artists=True).all()
        excluded_playlists = get_several_playlists_data(UserSettings, ex_ar_ids)

        # сбор инфы об оставшихся, не прикреплённых плейлистах
        user_pl = smart_playlist.sort_playlist(get_user_playlists(UserSettings))
        main_attached_playlists = smart_playlist.get_main_attached_ids(UserSettings)
        user_playlists = [item for item in user_pl if
                          item['id'] not in workers.playlist_functions.get_dict_items_by_key(used_playlists, 'id') and item[
                              'id'] not in main_attached_playlists and item['id'] not in workers.playlist_functions.get_dict_items_by_key(
                              excluded_playlists, 'id')]

        # settings
        return render_template('smart_settings.html',
                               used_playlists=used_playlists,
                               user_playlists=user_playlists,
                               excluded_playlists=excluded_playlists,
                               settings=UserSettings.get_playlists_settings(),
                               history=UserSettings.history_query.playlist_id,
                               auto_clean=get_updater_status(UserSettings.smart_query.ac_job_id, scheduler_a))
    else:
        return redirect('/')


def update_settings_post(UserSettings):
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
            """Функция проверяет статус настройки. Если true, то значение переходи в БД.
            Если false, то в бд присваивается None """
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
                create_job(UserSettings, history_query, tasks.update_history, scheduler_h)
            else:
                db.session.commit()

        return jsonify({'response': gettext('Success!')})
    else:
        return jsonify({'response': gettext('bruh')})
