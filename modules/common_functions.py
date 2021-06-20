import traceback

from modules import exceptions
from modules.database import db
from modules.app_init import app


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
