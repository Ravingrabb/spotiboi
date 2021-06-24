from datetime import datetime
from modules import *


def check_autoupdate_status(UserSettings, playlist_query, func, scheduler, session):
    """ Функция для проверки и перезапуска менеджера расписаний и статуса авто-обновления """
    print(session)
    spotify = UserSettings.spotify
    user_id = UserSettings.user_id
    user_query = UserSettings.user_query
    playlist_id = playlist_query.playlist_id

    # если autoupdate = ON
    if playlist_query.update and playlist_id and spotify.playlist_is_following(playlist_id, [user_id])[0]:
        is_user_own_playlist = check_playlist_owner(user_id, spotify, playlist_query, scheduler)
        if not is_user_own_playlist:
            return None

        # если работа не задана или она не в расписании
        elif not playlist_query.job_id or playlist_query.job_id not in scheduler:
            create_job(UserSettings, playlist_query, func, scheduler)

        # если работа работается, но uuid не совпадает
        elif playlist_query.job_id in scheduler and user_query.last_uuid != session.get('uuid'):
            recreate_job(UserSettings, func, playlist_query, scheduler)

        return "checked"

    # если autoupdate = OFF
    else:
        cancel_job_in_scheduler(playlist_query, scheduler)
        return None


def create_job(UserSettings, playlist_query, func, scheduler, job_time=30) -> None:
    if playlist_query.update_time:
        job_time = int(playlist_query.update_time)

    job_time_in_seconds = job_time * 60

    try:
        job = scheduler.schedule(datetime.utcnow(),
                                 func,
                                 args=[UserSettings.user_id, UserSettings],
                                 interval=job_time_in_seconds,
                                 repeat=None)
        scheduler.enqueue_job(job)
        playlist_query.job_id = job.id
        db.session.commit()
    except Exception as e:
        app.logger.error(e)


def recreate_job(UserSettings, func, playlist_query, scheduler) -> None:
    try:
        scheduler.cancel(playlist_query.job_id)
        create_job(UserSettings, playlist_query, func, scheduler)
        UserSettings.user_query.last_uuid = session.get('uuid')
        db.session.commit()
    except Exception as e:
        app.logger.error(e)


def check_playlist_owner(user_id, spotify, playlist_query, scheduler) -> bool:
    """ If user is not owner, scheduler task will be stopped and db data is cleared """
    if user_id != spotify.playlist(playlist_query.playlist_id, fields='owner')['owner']['id']:
        if playlist_query.job_id in scheduler:
            scheduler.cancel(playlist_query.job_id)
        playlist_query.update = False
        playlist_query.job_id = 0
        db.session.commit()
        return False
    else:
        return True


def cancel_job_in_scheduler(playlist_query, scheduler) -> None:
    try:
        if playlist_query.job_id in scheduler:
            scheduler.cancel(playlist_query.job_id)
    except Exception as e:
        app.logger.error(e)
