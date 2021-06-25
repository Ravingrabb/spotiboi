import traceback
from datetime import datetime

from modules import exceptions
from modules.database import db
from modules.app_init import app

from workers.autoupdate_worker import create_job


def get_updater_status(job_id, scheduler) -> bool:
    return True if job_id in scheduler else False


def get_several_playlists_data(UserSettings, playlist_ids: list) -> tuple:
    """ Возвращает сырые данные плейлиста для HTML отображения """
    output = tuple(
        UserSettings.spotify.playlist(playlist.playlist_id, fields="name, images, external_urls, id")
        for playlist in playlist_ids)
    return output


def get_user_playlists(UserSettings) -> list:
    """ Get all user playlist to display on smart playlist settings HTML page """
    playlists = UserSettings.spotify.current_user_playlists()

    def get_image(image) -> list:
        if image:
            return image[0]['url']
        else:
            return None

    playlists_to_dict = [
        {
            'name': playlist['name'],
            'id': playlist['id'],
            'images': get_image(playlist['images']),
            'url': playlist['external_urls']['spotify'],
            'owner': playlist['owner']['display_name']
        }
        for playlist in playlists['items']]

    return playlists_to_dict


def get_playlist_data_for_html(UserSettings, query, scheduler):
    """ Функция, необходимая только для отображения плейлиста юзера, данные
        которого находятся в базе данных """

    try:
        user_id = UserSettings.user_query.spotify_id
        # создаётся заготовок пустого плейлиста
        playlist_data = {
            'name': None,
            'id': None,
            'images': None
        }
        # сморим все плейлисты
        playlists = UserSettings.spotify.current_user_playlists()

        # если привязан ID плейлиста и юзер подписан на него, то выводим инфу
        if query.playlist_id and UserSettings.spotify.playlist_is_following(query.playlist_id, [user_id])[0]:
            current_playlist = UserSettings.spotify.playlist(query.playlist_id, fields="name, id, images")
            playlist_data['name'] = current_playlist['name']
            playlist_data['id'] = current_playlist['id']
            try:
                if not current_playlist['images']:
                    playlist_data['images'] = None
                else:
                    playlist_data['images'] = current_playlist['images'][0]['url']
            except Exception as e:
                raise exceptions.PlaylistImageException
        # если ID плейлиста привязан, но юзер не подписан на плейлист
        elif query.playlist_id and not UserSettings.spotify.playlist_is_following(query.playlist_id, [user_id])[0]:
            query.playlist_id = None
            db.session.commit()
            if query.job_id in scheduler:
                scheduler.cancel(query.job_id)
                app.logger.error(f'Traceback: отключено автообновление у клиента, так как нет подписки на плейлист. {query.playlist_id}. Юзер {user_id}')
    except UserSettings.spotipy.exceptions.SpotifyException as e:
        app.logger.error(
            'Tasks -> Attach_playlist -> spotipy.exceptions.SpotifyException. Неправильно указан Playlist ID. '
            'Если ошибка будет поймана вновь - выводить её юзеру, а не в консоль')
    except Exception as e:
        app.logger.error(e)
        app.logger.error(traceback.format_exc())
    finally:
        return playlist_data


def get_time_from_last_update(query) -> int:
    """ Возвращает разницу между последним обновлением и текущим временем в минутах """
    if query.last_update:
        time_past = query.last_update
        time_now = datetime.now()
        FMT = '%H:%M:%S'
        duration = time_now - datetime.strptime(time_past, FMT)
        time_difference = duration.seconds // 60
        return time_difference
    else:
        return None


def convert_time_to_string(minutes: int) -> str:
    if minutes:
        if minutes >= 60:
            hours = minutes // 60
            if hours >= 24:
                days = hours // 24
                return str(days) + ' д.'
            else:
                return str(hours) + ' ч.'
        else:
            return str(minutes) + ' мин.'
    else:
        return '0 мин.'


def convert_days_in_minutes(number_string: str) -> int:
    """ Переводит число в дней в минуты для RQ"""
    return int(number_string) * 1440


def restart_job_with_new_settings(UserSettings, query, func, scheduler):
    if query.job_id in scheduler:
        scheduler.cancel(query.job_id)
        create_job(UserSettings, query, func, scheduler)


def decode_to_bool(text: str) -> bool:
    """ Переводит текстовые значения on или true в bool """
    words = {'on', 'true'}
    if text.lower() in words:
        return True
    else:
        return False