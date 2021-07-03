import traceback

from modules import *
from workers.playlist_functions import get_limited_playlist_tracks, get_and_convert_every_playlist_tracks


def get_current_history_list(UserSettings, limit=None) -> tuple:
    """ Функция получения истории прослушиваний """

    history_query = UserSettings.new_history_query()
    sp = UserSettings.spotify
    playlist_id = history_query.playlist_id

    if playlist_id:
        try:
            results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")
            tracks = get_limited_playlist_tracks(sp, results, limit) if limit else get_and_convert_every_playlist_tracks(sp, results)
            return tuple(item for item in tracks)
        except Exception as e:
            if 'Couldn\'t refresh token' in str(e):
                cancel_job(history_query, history_query.job_id, scheduler_h)
                raise TokenError
            else:
                log_with_traceback(e)
            return None
    else:
        cancel_job(history_query, history_query.job_id, scheduler_h)
        return None


def cancel_job(new_query, job_id, scheduler):
    """ Отмена задачи. Требуется создания нового запроса, чтобы выполнялось без ошибок """
    query = new_query
    if job_id in scheduler:
        scheduler.cancel(job_id)
    job_id = 0
    db.session.commit()