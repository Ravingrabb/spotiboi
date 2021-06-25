import gc
import random

import requests
import spotipy
from flask import session
from flask_babel import gettext
# for last
import pylast
from transliterate import detect_language

from modules import *
from modules.logging_settings import log_with_traceback
from modules.database import HistoryPlaylist, SmartPlaylist, UsedPlaylist
from workers.history_functions import *
from workers.playlist_functions import *


def update_history(user_id, UserSettings) -> str:
    """ Функция обновления истории """

    def limit_playlist_size():
        """ Обрезка плейлиста, если стоит настройка фиксированного плейлиста """
        # поулчаем кол-во треков
        playlist_size = spotify.playlist_tracks(history_id, fields='total')

        if playlist_size['total'] >= history_query.fixed_capacity:
            result = spotify.playlist_tracks(history_id, fields="items(track(uri,name))",
                                             limit=len(recently_played_uris), offset=history_query.fixed_capacity)
            tracks_to_delete = [item['track']['uri'] for item in result['items']]
            spotify.playlist_remove_all_occurrences_of_items(history_id, tracks_to_delete)

    spotify = UserSettings.spotify
    history_query = UserSettings.history_query
    history_id = history_query.playlist_id
    user_query = UserSettings.new_user_query()

    search_limit = 45
    try:
        # получаем историю прослушиваний (учитывая настройки )
        history_playlist = get_current_history_list(UserSettings, history_query.fixed_dedup)

        # если вернутся None из-за ошибки, то выдаём ошибку
        if history_playlist is None:
            return (gettext('Can\'t connect to Spotify server'))

        # вытаскиваются последние прослушанные песни
        results = spotify.current_user_recently_played(limit=search_limit)

        # песни из recently сравниваются с историей
        history_tracks_uris = list(get_dict_items_by_key(history_playlist, 'uri'))
        history_tracks_names = list(get_dict_items_by_key(history_playlist, 'name'))
        recently_played_uris = [item['track']['uri']
                                for item in results['items']
                                if item['track']['uri'] not in history_tracks_uris
                                and item['track']['name'].lower() not in history_tracks_names]

        # если в настройках указан логин lasfm, то вытаскиваются данные с него
        if user_query.lastfm_username:
            try:
                username = user_query.lastfm_username
                network = pylast.LastFMNetwork(api_key='e62b095dc44b53f63137d90bce84117b',
                                               api_secret="1e3f4f44e4eae94a9cc8280f11b6fc71",
                                               username=username)
                result = network.get_user(username).get_recent_tracks(limit=search_limit)

                recently_played_names = {item['track']['name'].lower() for item in results['items'] if
                                         item['track']['uri'] not in history_tracks_uris}

                # достаём данные из lastfm
                data_with_duplicates = [
                    {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
                    for song in result
                ]

                # создаём оптимизированный список без дубликатов и без треков, которые уже, вероятно, есть в истории
                last_fm_data = []
                for song in data_with_duplicates:
                    if song not in last_fm_data and song['name'].lower() not in recently_played_names and song[
                        'name'].lower() not in history_tracks_names:
                        last_fm_data.append(song)

                # переводим эти данные в uri спотифай (SPOTIFY API SEARCH)
                last_fm_data_to_uri = []
                for q in last_fm_data:
                    try:
                        lang = detect_language(q['artist'])
                        if lang != 'ru':
                            track = \
                                spotify.search(f"\"{q['name']}\" artist:{q['artist']} album:\"{q['album']}\"", limit=1,
                                               type="track")['tracks']['items'][0]['uri']
                        else:
                            track = \
                                spotify.search(f"\"{q['name']}\" album:\"{q['album']}\"", limit=1, type="track")[
                                    'tracks'][
                                    'items'][0]['uri']
                        last_fm_data_to_uri.insert(0, {"name": q['name'], 'uri': track})
                    except:
                        continue

                # проверяем все результаты на дубликаты и если всё ок - передаём в плейлист
                for track in last_fm_data_to_uri:
                    if track['uri'] not in recently_played_uris and track['uri'] not in history_tracks_uris:
                        recently_played_uris.insert(0, track['uri'])

            except pylast.WSError:
                pass
                # TODO: добавить полноценное оповещение, но только при ручном автообновлении
                # logging.error('Last.fm. Connection to the API failed with HTTP code 500')

            except Exception as e:
                log_with_traceback(e)

        # если есть новые треки для добавления - они добавляются в History   
        try:
            if recently_played_uris:
                # убираем дубликаты
                recently_played_uris = list(dict.fromkeys(recently_played_uris))

                spotify.playlist_add_items(history_id, recently_played_uris, position=0)
                # если стоит настройка ограничения плейлиста по размеру
                if history_query.fixed_capacity:
                    limit_playlist_size()

                return (gettext('History updated'))
            # иначе пропускаем
            else:
                return (gettext('Nothing to update'))
        except spotipy.SpotifyException:
            return ("Nothing to add for now")
        finally:
            history_query = HistoryPlaylist.query.filter_by(user_id=user_id).first()
            history_query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
            db.session.commit()
            gc.collect()
    except TokenError:
        pass
    except requests.exceptions.ReadTimeout as e:
        if 'Read timed out' in str(e):
            # TODO: выкидывать ошибку в интерфейсе в виде ретёрна как выше
            pass
        else:
            log_with_traceback(e)
    except Exception as e:
        log_with_traceback(e)


def update_favorite_playlist(user_id, UserSettings) -> None:
    """ Создать новый плейлист, содержащий только лайкнутые треки """

    sp = UserSettings.spotify
    favorite_query = UserSettings.favorite_query
    try:
        results = sp.current_user_saved_tracks(limit=20)
        # если плейлист добавлен, то просто обновляем
        if favorite_query.playlist_id and sp.playlist_is_following(favorite_query.playlist_id, [user_id])[0]:
            # получаем актуальный список треков из saved
            new_track_uris = tuple(item['uri'] for item in get_and_convert_every_playlist_tracks(sp, results))

            # получаем список песен из плейлиста favorites
            fav_playlist_results = sp.playlist_tracks(favorite_query.playlist_id)
            fav_playlist_uris = tuple(item['uri'] for item in get_and_convert_every_playlist_tracks(sp, fav_playlist_results))

            # добавляем новые треки
            to_add = [uri for uri in new_track_uris if uri not in fav_playlist_uris]
            if to_add:
                fill_playlist(sp, favorite_query.playlist_id, to_add, from_top=True)

            # удаляем не акутальные
            to_delete = [uri for uri in fav_playlist_uris if uri not in new_track_uris]
            if to_delete:
                sp.playlist_remove_all_occurrences_of_items(favorite_query.playlist_id, to_delete[:99])
                # плейлист не добавлен
        else:
            sp.user_playlist_create(
                user=user_id,
                name='My Favorite Songs',
                description='My public liked tracks. Created by SpotiBoi'
            )

            playlists = sp.current_user_playlists()
            track_uris = tuple(item['uri'] for item in get_and_convert_every_playlist_tracks(sp, results))
            for item in playlists['items']:
                if item['name'] == 'My Favorite Songs':
                    favorite_query.playlist_id = item['id']
                    favorite_query.update = False
                    db.session.commit()
                    fill_playlist(sp, item['id'], track_uris)
                    break
    except Exception as e:
        if 'Couldn\'t refresh token' in str(e):
            pass
        else:
            log_with_traceback(e)
    finally:
        gc.collect()


def update_smart_playlist(user_id, UserSettings):
    sp = UserSettings.spotify
    used_playlists_ids = UsedPlaylist.query.filter_by(user_id=user_id, exclude=False, exclude_artists=False).all()
    excluded_artists_playlists = UsedPlaylist.query.filter_by(user_id=user_id, exclude_artists=True).all()
    smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
    playlist_size = smart_query.max_tracks

    check_by_names = True

    def add_tracks_to_list(excluded_list, key, playlist):
        if playlist:
            new_list = frozenset(item[key] for item in playlist)
            excluded_list.update(new_list)
            return True
        else:
            return False

    def fillup(excluded_list, key):
        if smart_query.exclude_history:
            history_playlist = get_current_history_list(UserSettings)
            smart_query.exclude_history = add_tracks_to_list(excluded_list, key, history_playlist)

        if smart_query.exclude_favorite:
            favorite_playlist = get_and_convert_every_playlist_tracks(sp, sp.current_user_saved_tracks(limit=20))
            smart_query.exclude_favorite = add_tracks_to_list(excluded_list, key, favorite_playlist)

    def appender(results, excluded_list, key):
        ban_list = list(f'spotify:track:{i}' for i in range(1, 445))
        for item in results:
            if not excluded_artists_playlists:
                if item[key] not in excluded_list and item['uri'] not in ban_list:
                    all_uris.append(item['uri'])
            else:
                if item[key] not in excluded_list and item['artist'] not in excluded_artists and item[
                    'uri'] not in ban_list:
                    all_uris.append(item['uri'])

    try:
        # существует ли smart в базе данных
        if smart_query.playlist_id:
            excluded_list = set()
            check_key = 'uri'
            # лист заполняется в зависимости от выбранного типа проверки 
            if check_by_names:
                fillup(excluded_list, 'name')
                check_key = 'name'
            else:
                fillup(excluded_list, 'uri')
                check_key = 'uri'

            if excluded_artists_playlists:
                excluded_artists = set()
                for playlist in excluded_artists_playlists:
                    raw_results = get_playlist_raw_tracks(sp, playlist.playlist_id)
                    results = get_and_convert_every_playlist_tracks(sp, raw_results)
                    output = frozenset(item['artist'] for item in results)
                    excluded_artists.update(output)

            # собираем все треки из приклеплённых плейлистов в used playlists
            all_uris = []
            for playlist in used_playlists_ids:
                raw_results = sp.playlist_tracks(playlist.playlist_id,
                                                 fields="items(track(name, uri, artists, album)), next")
                results = get_and_convert_every_playlist_tracks(sp, raw_results)
                appender(results, excluded_list, check_key)

            # перемешиваем
            random.shuffle(all_uris)

            # обрезка плейлиста, если кол-во песен из all_uris меньше, чем требуемое
            if playlist_size > len(all_uris):
                playlist_size = len(all_uris)

            output_tracks = tuple(all_uris[i] for i in range(playlist_size))
            fill_playlist_with_replace(sp, user_id, smart_query.playlist_id, output_tracks)
            return 'OK!'
        else:
            return 'You unfollowed this playlist. Please, refresh your page'

    except TokenError:
        cancel_job(smart_query, smart_query.job_id, scheduler_s)
    except TypeError as e:
        app.logger.error('Error in update_smart_playlist below:')
        app.logger.error(e)
        app.logger.error(
            f'User:{UserSettings.user_id}, Playlist: https://open.spotify.com/playlist/{UserSettings.smart_query.playlist_id}')
        app.logger.error('And traceback for error above:')
        app.logger.error(traceback.format_exc())
    except Exception as e:
        if 'Couldn\'t refresh token' in str(e):
            pass
        else:
            app.logger.error(e)
            app.logger.error('And traceback for error above:')
            app.logger.error(traceback.format_exc())
    finally:
        smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
        smart_query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
        db.session.commit()
        gc.collect()


def auto_clean(user_id, UserSettings):
    try:
        history_query = UserSettings.new_history_query()
        smart_query = UserSettings.new_smart_query()
        sp = UserSettings.spotify
        if history_query.playlist_id and UserSettings.smart_query.playlist_id:
            history_playlist = get_playlist(sp, history_query.playlist_id)
            smart_raw = get_playlist(sp, smart_query.playlist_id)
            history_tracks_names = get_dict_items_by_key(history_playlist, 'name')
            to_delete = frozenset(item['uri'] for item in smart_raw if item['name'] in history_tracks_names)
            sp.playlist_remove_all_occurrences_of_items(UserSettings.smart_query.playlist_id, to_delete)
            gc.collect()
    except Exception as e:
        if 'Couldn\'t refresh token' in str(e) or 'Task exceeded maximum timeout value' in str(
                e) or 'playlist you don\'t own' in str(e):
            smart_query = UserSettings.new_smart_query()
            if smart_query.ac_job_id in scheduler_a:
                scheduler_a.cancel(smart_query.ac_job_id)
            smart_query.ac_job_id = 0
            db.session.commit()
        else:
            app.logger.error(e)


def auto_clean_checker(UserSettings, scheduler):
    """ Работник с задачей, но только специально для auto cleaner """

    def create_ac_job():
        """ То же самое, что и create_job, только для auto cleaner"""
        job = scheduler.schedule(datetime.utcnow(), auto_clean, args=[UserSettings.user_id, UserSettings],
                                 interval=3600, repeat=None, timeout=500)
        scheduler.enqueue_job(job)
        smart_query.ac_job_id = job.id
        db.session.commit()

    try:
        smart_query = UserSettings.new_smart_query()

        # если настройки включены
        if smart_query.auto_clean and smart_query.playlist_id:
            # .... но работа не создана
            if not smart_query.ac_job_id or smart_query.ac_job_id not in scheduler:
                create_ac_job()

            elif smart_query.ac_job_id in scheduler and UserSettings.user_query.last_uuid != session.get('uuid'):
                scheduler.cancel(smart_query.ac_job_id)
                create_ac_job()
                UserSettings.user_query.last_uuid = session.get('uuid')
                db.session.commit()
        else:
            if smart_query.ac_job_id in scheduler:
                scheduler.cancel(smart_query.ac_job_id)
    except Exception as e:
        app.logger.error(e)
