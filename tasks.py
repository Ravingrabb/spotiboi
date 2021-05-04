from datetime import datetime
import requests
from flask import session
from flask.globals import request
import spotipy
from sqlalchemy.orm import query
from start_settings import db, User, HistoryPlaylist, FavoritePlaylist, SmartPlaylist, UsedPlaylist, scheduler_h, scheduler_f, scheduler_s, scheduler_a
from flask_babel import gettext
import gc
import random
from sys import exc_info
import traceback
from start_settings import app
#for last
import pylast
from transliterate import detect_language



class UserSettings():
    
    def __init__(self, auth_manager) -> None:
        # авторизация и получаем id
        try:
            self.spotify = spotipy.Spotify(auth_manager=auth_manager)
            self.user_id = self.spotify.current_user()['id']
        except spotipy.requests.exceptions.ReadTimeout:
            app.logger.error('Spotify HTTP read timed out. (read timeout=5)')
        except spotipy.exceptions.SpotifyException as e:
            app.logger.error(e)
            
        
        # если юзера не сущестует в БД, то создаётся запись. Тут же создаётся запись дял плейлиста
        if not User.query.filter_by(spotify_id=self.user_id).first():
            db.session.add(User(spotify_id=self.user_id))
            db.session.add(HistoryPlaylist(user_id=self.user_id))
            db.session.add(FavoritePlaylist(user_id=self.user_id))
            db.session.add(SmartPlaylist(user_id=self.user_id, max_tracks = 100))
            db.session.commit()

        self.user_query = User.query.filter_by(spotify_id=self.user_id).first()
        self.history_query = HistoryPlaylist.query.filter_by(user_id=self.user_id).first()
        self.favorite_query = FavoritePlaylist.query.filter_by(user_id=self.user_id).first()
        self.smart_query = SmartPlaylist.query.filter_by(user_id=self.user_id).first()
            
        # Used only for HTML page. Template for settings, that will be changed in future. 
        self.settings = {
            # history playlist
            'dedup_status': None,
            'dedup_value': 0,
            'fixed_status': None,
            'fixed_value': 0,
            'update_time': self.history_query.update_time,
            'lastfm_status': 0,
            'lastfm_value': self.user_query.lastfm_username,
            # fav playlist
            'fav_playlist': False,
            # smart playlist
            'max_tracks': self.smart_query.max_tracks,
            'exclude_history': self.smart_query.exclude_history,
            'exclude_favorite': self.smart_query.exclude_favorite,
            'smart_update_time' : round(self.smart_query.update_time / 1440)
        }
     
    def settings_worker(self) -> None:
        if self.history_query.fixed_dedup and self.history_query.fixed_dedup > 0:
            self.settings['dedup_status'] = 'checked'
            self.settings['dedup_value'] = self.history_query.fixed_dedup
            
        if self.history_query.fixed_capacity and self.history_query.fixed_capacity > 0:
            self.settings['fixed_status'] = 'checked'
            self.settings['fixed_value'] = self.history_query.fixed_capacity
            
        if self.user_query.lastfm_username:
            self.settings['lastfm_status'] = 'checked'
            
        if self.favorite_query.playlist_id:
            if self.spotify.playlist_is_following(self.favorite_query.playlist_id, [self.user_query.spotify_id])[0]:
                self.settings['fav_playlist'] = True
        
        if self.settings['exclude_history']:
            self.settings['exclude_history'] = 'checked'
            
        if self.settings['exclude_favorite']:
            self.settings['exclude_favorite'] = 'checked'


    def time_worker(self) -> int:
        if self.history_query.last_update:
            self.time_past = self.history_query.last_update
            self.time_now = datetime.now()
            self.FMT = '%H:%M:%S'
            self.duration = self.time_now - datetime.strptime(self.time_past, self.FMT)
            self.time_difference = self.duration.seconds // 60
            return self.time_difference
        else:
            return None

    def new_user_query(self):
        return User.query.filter_by(spotify_id=self.user_id).first()
    
    
    def new_history_query(self):
        return HistoryPlaylist.query.filter_by(user_id=self.user_id).first()
    
    
    def new_smart_query(self):
        return SmartPlaylist.query.filter_by(user_id=self.user_id).first()
    
    
    def get_several_playlists_data(self, playlist_ids: list):
        ''' Возвращает сырые данные плейлиста '''
        output = tuple(self.spotify.playlist(playlist.playlist_id, fields="name, images, external_urls, id") for playlist in playlist_ids)
        return output
    
    
    def get_user_playlists(self):
        
            playlists = self.spotify.current_user_playlists()
            
            def get_image(image):
                if image:
                    return image[0]['url']
                else:
                    return None
                
            playlists_to_dict = [
                {
                'name': playlist['name'],
                'id': playlist['id'],
                'images': get_image(playlist['images']),
                'url' : playlist['external_urls']['spotify'],
                'owner' : playlist['owner']['display_name']
                }
                for playlist in playlists['items']]
            
            return playlists_to_dict

        
    def attach_playlist(self, query, scheduler):
            """ Функция, необходимая только для отображения плейлиста юзера, данные
            которого находятся в базе данных """
            # создаётся заготовок пустого плейлиста
            self.playlist_data = {
                'name': None,
                'id': None,
                'images': None
            }
            
            # посмотреть все плейлисты юзера
            try:
                # сморим все плейлисты
                self.playlists = self.spotify.current_user_playlists()
                # если привязан ID плейлиста и юзер подписан на него, то выводим инфу
                if query.playlist_id and self.spotify.playlist_is_following(query.playlist_id, [self.user_query.spotify_id])[0]:
                    self.current_playlist = self.spotify.playlist(
                        query.playlist_id, fields="name, id, images")
                    self.playlist_data['name'] = self.current_playlist['name']
                    self.playlist_data['id'] = self.current_playlist['id']
                    try:
                        if not self.current_playlist['images']:
                            self.playlist_data['images'] = None
                        else:
                            self.playlist_data['images'] = self.current_playlist['images'][0]['url']
                    except Exception as e:
                        app.logger.error(e)
                # если ID плейлиста привязан, но юзер не подписан на плейлист
                elif query.playlist_id and not self.spotify.playlist_is_following(query.playlist_id, [self.user_query.spotify_id])[0]:
                    query.playlist_id = None
                    db.session.commit()
                    if query.job_id in scheduler:
                        scheduler.cancel(query.job_id)    
                        app.logger.error(f'Traceback: отключено автообновление у клиента, так как нет подписки на плейлист. {query.playlist_id}. Юзер {self.user_query.spotify_id}')
            except spotipy.exceptions.SpotifyException as e:
                app.logger.error('Tasks -> Attach_playlist -> spotipy.exceptions.SpotifyException. Неправильно указан Playlist ID. Если ошибка будет поймана вновь - выводить её юзеру, а не в консоль')
            except requests.exceptions.ReadTimeout:
                app.logger.error('Tasks -> Attach_playlist -> requests.exceptions.ReadTimeout. Read Timeout.')
            except Exception as e:
                app.logger.error(e)
                app.logger.error(traceback.format_exc())
            finally:
                return self.playlist_data    
            
            
def time_worker2(query) -> int:
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


def time_converter(minutes):
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
      
                           
def decode_to_bool(text: str) -> bool:
    ''' Переводит текстовые значения on или true в bool'''
    words = {'on', 'true'}
    if text.lower() in words:
        return True
    else:
        return False
        
def days_to_minutes(number_string: str) -> int:
    ''' Переводит число в дней в минуты для RQ'''
    return int(number_string) * 1440

            
def create_job(UserSettings, playlist_query, func, scheduler, job_time=30) -> None:
    if playlist_query.update_time:
        job_time = int(playlist_query.update_time)
    job_time = job_time * 60
    try:
        job = scheduler.schedule(datetime.utcnow(), func, args=[UserSettings.user_id, UserSettings], interval=job_time, repeat=None)
        scheduler.enqueue_job(job)
        playlist_query.job_id = job.id
        db.session.commit()
    except Exception as e:
        app.logger.error(e)

def cancel_job(new_query, job_id, scheduler):
    '''Отмена задачи. Требуется создания нового запроса, чтобы выполнялось без ошибок'''
    query = new_query
    if job_id in scheduler:
        scheduler.cancel(job_id)
    job_id = 0
    db.session.commit()

# TODO: объединить обе функции
def restart_job_with_new_settings(query, scheduler, UserSettings):
    if query.job_id in scheduler:
        scheduler.cancel(query.job_id)
        create_job(UserSettings, query, update_history, scheduler)

def restart_smart_with_new_settings(query, scheduler, UserSettings):
    if query.job_id in scheduler:
        scheduler.cancel(query.job_id)
        create_job(UserSettings, query, update_smart_playlist, scheduler)


def check_worker_status(UserSettings, playlist_query, func, scheduler) -> str:
    """ Функция для проверки и перезапуска менеджера расписаний и статуса авто-обновления """
    user_query = UserSettings.user_query
    # если autoupdate = ON

    if playlist_query.update == True and playlist_query.playlist_id and UserSettings.spotify.playlist_is_following(playlist_query.playlist_id, [UserSettings.user_id])[0]:
        if UserSettings.user_id != UserSettings.spotify.playlist(playlist_query.playlist_id, fields='owner')['owner']['id']:
            if playlist_query.job_id in scheduler: 
                scheduler.cancel(playlist_query.job_id)
            playlist_query.update = False
            playlist_query.job_id = 0
            db.session.commit()
            return None
        # если работа не задана или она не в расписании
        elif not playlist_query.job_id or playlist_query.job_id not in scheduler:
            try:
                create_job(UserSettings, playlist_query, func, scheduler)
            except Exception as e:
                app.logger.error(e)
        # если работа работается, но uuid не совпадает
        elif playlist_query.job_id in scheduler and user_query.last_uuid != session.get('uuid'):
            try:
                scheduler.cancel(playlist_query.job_id)
                create_job(UserSettings, playlist_query, func, scheduler)
                user_query.last_uuid = session.get('uuid')
                db.session.commit()
            except Exception as e:
                app.logger.error(e)
        
        
        return "checked"
    # если autoupdate = OFF
    else:
        try:
            if playlist_query.job_id in scheduler:
                scheduler.cancel(playlist_query.job_id)
        except Exception as e:
            app.logger.error(e)
        return None
    
    
def get_items_by_key(array, search_key: str) -> str:
    ''' Возможность вытащить из dict элементы по определённому ключу, только для итераций'''
    for item in array:
        for key, value in item.items():
            if key == search_key:
                yield value
    
    
def update_history(user_id, UserSettings) -> str:
    """ Функция обновления истории """

    def limit_playlist_size():
        """ Обрезка плейлиста, если стоит настройка фиксированного плейлиста """
        # поулчаем кол-во треков
        playlist_size = spotify.playlist_tracks(history_id, fields='total')
        
        if playlist_size['total'] >= history_query.fixed_capacity:
            result = spotify.playlist_tracks(history_id, fields="items(track(uri,name))", limit=len(recently_played_uris), offset=history_query.fixed_capacity)
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
        if history_playlist == None:
            return (gettext('Can\'t connect to Spotify server'))
        
        # вытаскиваются последние прослушанные песни
        results = spotify.current_user_recently_played(limit=search_limit)
        
        #песни из recently сравниваются с историей
        history_tracks_uris = list(get_items_by_key(history_playlist, 'uri'))
        history_tracks_names = list(get_items_by_key(history_playlist, 'name'))
        recently_played_uris = [item['track']['uri'] 
                                for item in results['items'] 
                                if item['track']['uri'] not in history_tracks_uris 
                                and item['track']['name'].lower() not in history_tracks_names]

        # если в настройках указан логин lasfm, то вытаскиваются данные с него
        if user_query.lastfm_username:
            try:
                username = user_query.lastfm_username
                network = pylast.LastFMNetwork(api_key='e62b095dc44b53f63137d90bce84117b', api_secret="1e3f4f44e4eae94a9cc8280f11b6fc71",
                                            username=username)
                result = network.get_user(username).get_recent_tracks(limit=search_limit)
                
                recently_played_names = {item['track']['name'].lower() for item in results['items'] if item['track']['uri'] not in history_tracks_uris }
                    
                # достаём данные из lastfm
                data_with_duplicates = [
                    {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
                    for song in result
                ]
                
                # создаём оптимизированный список без дубликатов и без треков, которые уже, вероятно, есть в истории
                last_fm_data = []
                for song in data_with_duplicates:
                    if song not in last_fm_data and song['name'].lower() not in recently_played_names and song['name'].lower() not in history_tracks_names:
                        last_fm_data.append(song)

                # переводим эти данные в uri спотифай (SPOTIFY API SEARCH)
                last_fm_data_to_uri = [] 
                for q in last_fm_data:
                    try:
                        lang = detect_language(q['artist'])
                        if lang != 'ru':
                            track = spotify.search(f"\"{q['name']}\" artist:{q['artist']} album:\"{q['album']}\"", limit=1, type="track")['tracks']['items'][0]['uri']
                        else:
                            track = spotify.search(f"\"{q['name']}\" album:\"{q['album']}\"", limit=1, type="track")['tracks']['items'][0]['uri']
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
                #logging.error('Last.fm. Connection to the API failed with HTTP code 500') 
                        
            except Exception as e:
                app.logger.error(e)
                app.logger.error('And trackeback for error above:')
                app.logger.error(traceback.format_exc())
                
                
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
    except requests.exceptions.ReadTimeout as e:
        if 'Read timed out' in str(e):
            # TODO: выкидывать ошибку в интерфейсе в виде ретёрна как выше
            pass
        else:
            app.logger.error(e)
    except Exception as e:
        app.logger.error(e)

def get_playlist_raw_tracks(sp, playlist_id):
    ''' Шаблонное получение плейлиста по ID. Содержит лишние поля items, track, поэтому для работы из лучше убрать с помощью convert_playlist '''
    return sp.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")


def convert_playlist(playlist_array) -> list:
    """ Перевод сырого dict плейлиста в формат, более удобный для программы """
    output = [
        {'name': item['track']['name'].lower(),
        'uri': item['track']['uri'],
        'artist': item['track']['artists'][0]['name'].lower(),
        'album': item['track']['album']['name'].lower()}
        for item in playlist_array['items']
        if item['track']
        ]
    return output


def get_playlist(sp, playlist_id, limit=100):
    ''' Возвращает хорший и уже конвертнутый плейлист'''
    result = get_playlist_raw_tracks(sp, playlist_id)
    return convert_playlist(result) if limit else get_every_playlist_track(sp, result)


def get_every_playlist_track(spotify, raw_results: list) -> list:
    """ Достать абсолютно все треки из плейлиста в обход limit c конвертацией в удобную форму для доступа.
    Лимит есть абсолютно у всех плейлистов """
    tracks = convert_playlist(raw_results)
    while raw_results['next']:
        raw_results = spotify.next(raw_results)
        tracks.extend(convert_playlist(raw_results))
    return tracks


def get_limited_playlist_track(spotify, raw_results, limit) -> list:
    def is_reached_limit(array, limit) -> bool:
            return True if len(array) >= limit else False
        
    tracks = convert_playlist(raw_results)
    
    while raw_results['next'] and not is_reached_limit(tracks, limit):
        raw_results = spotify.next(raw_results)
        tracks.extend(convert_playlist(raw_results))  
        
    if is_reached_limit(tracks, limit):
        tracks = tracks[:limit] 
        
    return tracks
 
        
def get_current_history_list(UserSettings, limit = None) -> tuple:
    """ Функция получения истории прослушиваний """
        
    history_query = UserSettings.new_history_query()
    sp = UserSettings.spotify
    playlist_id = history_query.playlist_id
    
    try:
        results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")
                
        if limit:
            tracks = get_limited_playlist_track(sp, results, limit)
        else:
            tracks = get_every_playlist_track(sp, results)
        return tuple(item for item in tracks)
    except AttributeError as e:
        if 'NoneType' in str(e):
            app.logger.error(f'get_current_history_list, проверь плейлист {playlist_id} на ошибки NoneType')
    except Exception as e:
        if 'Couldn\'t refresh token' in str(e):
            #app.logger.error('Couldn\'t refresh token')
            cancel_job(history_query, history_query.job_id, scheduler_h)
        else:
            app.logger.error(e)
            app.logger.error('And trackeback for error above:')
            app.logger.error(traceback.format_exc())
        return None
    
    

def fill_playlist(sp, playlist_id : str, uris_list : list, from_top = False) -> None:
    """ Заполнение плейлиста песнями из массива. Так как ограничение
    на одну итерацию добавления - 100 треков, приходится делать это в несколько
    итераций """
    
    offset = 0
    
    while offset < len(uris_list):
        if not from_top:
            sp.playlist_add_items(playlist_id, uris_list[offset:offset+100])
        else:
            sp.playlist_add_items(playlist_id, uris_list[offset:offset+100], position=0)
        offset += 100
        
        
def fill_playlist_with_replace(sp, user_id: str, playlist_id : str, uris_list : list) -> None:
    """ Почти то же самое, что и fill playlist, только он заменяет песни, а не добавляет. Нужно для smart плейлиста""" 
    offset = 0
    once = True
    while offset < len(uris_list):
        # TODO: очищать плейлист и добавлять новые песни
        if once:
            sp.user_playlist_replace_tracks(user_id, playlist_id, uris_list[offset:offset+100])
            once = False
        else:
            sp.playlist_add_items(playlist_id, uris_list[offset:offset+100])
        offset += 100


def update_favorite_playlist(user_id, UserSettings) -> None:
    """ Создать новый плейлист, содержащий только лайкнутые треки """
    
    sp = UserSettings.spotify
    favorite_query = UserSettings.favorite_query
    try:
        results = sp.current_user_saved_tracks(limit=20)
        # если плейлист добавлен, то просто обновляем
        if favorite_query.playlist_id and sp.playlist_is_following(favorite_query.playlist_id, [user_id])[0]:
            # получаем актуальный список треков из saved
            new_track_uris = tuple( item['uri'] for item in get_every_playlist_track(sp, results) )
            
            # получаем список песен из плейлиста favorites
            fav_playlist_results = sp.playlist_tracks(favorite_query.playlist_id)
            fav_playlist_uris = tuple( item['uri'] for item in get_every_playlist_track(sp, fav_playlist_results) )
            
            #добавляем новые треки
            to_add = [uri for uri in new_track_uris if uri not in fav_playlist_uris]
            if to_add: 
                fill_playlist(sp, favorite_query.playlist_id, to_add, from_top=True)
            
            #удаляем не акутальные
            to_delete = [ uri for uri in fav_playlist_uris if uri not in new_track_uris]
            if to_delete:
                sp.playlist_remove_all_occurrences_of_items(favorite_query.playlist_id, to_delete)   
        # плейлист не добавлен
        else:
            sp.user_playlist_create(
                    user=user_id, 
                    name='My Favorite Songs', 
                    description='My public liked tracks. Created by SpotiBoi'
                    )
            
            playlists = sp.current_user_playlists()
            track_uris = tuple( item['uri'] for item in get_every_playlist_track(sp, results) )
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
            app.logger.error(e)
    finally:
        gc.collect()
        
        
def update_smart_playlist(user_id, UserSettings):
    sp = UserSettings.spotify
    used_playlists_ids = UsedPlaylist.query.filter_by(user_id=user_id, exclude = False, exclude_artists = False).all()
    excluded_artists_playlists = UsedPlaylist.query.filter_by(user_id=user_id, exclude_artists = True).all()
    smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
    playlist_size = smart_query.max_tracks
    
    check_by_names = True
    

    def add_tracks_to_list(excluded_list, key, playlist):
        if playlist:
            new_list = frozenset(item[key] for item in playlist)
            excluded_list.update(new_list)


    def fillup(excluded_list, key):  
        if smart_query.exclude_history:
            history_playlist = get_current_history_list(UserSettings)
            add_tracks_to_list(excluded_list, key, history_playlist)
            
        if smart_query.exclude_favorite:
            favorite_playlist = get_every_playlist_track(sp, sp.current_user_saved_tracks(limit=20))
            add_tracks_to_list(excluded_list, key, favorite_playlist)
            
    def appender(results, excluded_list, key):
        ban_list = list(range(1, 445))
        for item in results:
            if not excluded_artists_playlists:
                if item[key] not in excluded_list:
                    all_uris.append(item['uri'])
            else:
                if item[key] not in excluded_list and item['artist'] not in excluded_artists and item['uri'].replace('spotify:track:', '') not in ban_list:
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
                    results = get_every_playlist_track(sp, raw_results)
                    output = frozenset(item['artist'] for item in results)
                    excluded_artists.update(output)
            
            # собираем все треки из приклеплённых плейлистов в used playlists
            all_uris = []
            for playlist in used_playlists_ids:
                raw_results = sp.playlist_tracks(playlist.playlist_id, fields="items(track(name, uri, artists, album)), next")
                results = get_every_playlist_track(sp, raw_results)
                appender(results, excluded_list, check_key)

            # перемешиваем
            random.shuffle(all_uris)
            
            #обрезка плейлиста, если кол-во песен из all_uris меньше, чем требуемое
            if playlist_size > len(all_uris):
                playlist_size = len(all_uris)
            
            output_tracks = tuple(all_uris[i] for i in range(playlist_size))
            fill_playlist_with_replace(sp, user_id, smart_query.playlist_id, output_tracks)
            return 'OK!'
        else:
            return 'You unfollowed this playlist. Please, refresh your page'

    
    except TypeError as e:
        app.logger.error('Error in update_smart_playlist below:')
        app.logger.error(e)
        app.logger.error(f'User:{UserSettings.user_id}, Playlist: https://open.spotify.com/playlist/{UserSettings.smart_query.playlist_id}')
        app.logger.error('And trackeback for error above:')
        app.logger.error(traceback.format_exc())
    except Exception as e:
        if 'Couldn\'t refresh token' in str(e):
            pass
        elif 'Task exceeded maximum timeout value' in str(e):
            pass
        else:
            app.logger.error(e)
            app.logger.error('And trackeback for error above:')
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
            history_tracks_names = get_items_by_key(history_playlist, 'name')
            to_delete = frozenset(item['uri'] for item in smart_raw if item['name'] in history_tracks_names)
            sp.playlist_remove_all_occurrences_of_items(UserSettings.smart_query.playlist_id, to_delete)
            gc.collect()
    except Exception as e:
        if 'Couldn\'t refresh token' in str(e) or 'Task exceeded maximum timeout value' in str(e) or 'playlist you don\'t own' in str(e):
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
        ''' То же самое, что и create_job, только для auto cleaner'''
        job = scheduler.schedule(datetime.utcnow(), auto_clean, args=[UserSettings.user_id, UserSettings], interval=3600, repeat=None, timeout=500)
        scheduler.enqueue_job(job)
        smart_query.ac_job_id = job.id
        db.session.commit()
        
    try:
        smart_query = UserSettings.new_smart_query()
        
        # если настройки включены
        if smart_query.auto_clean and smart_query.playlist_id:
            #.... но работа не создана
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
    
    
def get_updater_status(job_id, scheduler):
    return True if job_id in scheduler else False


        
        