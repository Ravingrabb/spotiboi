from datetime import datetime
import logging
from flask import session
from flask.globals import request
import spotipy
from sqlalchemy.orm import query
from start_settings import db, User, HistoryPlaylist, FavoritePlaylist, SmartPlaylist, UsedPlaylist
from flask_babel import gettext
import gc
import random
from sys import exc_info
from traceback import extract_tb
from start_settings import app
#for last
import pylast
from transliterate import detect_language



class UserSettings():
    
    def __init__(self, auth_manager) -> None:
        # авторизация и получаем id
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        self.user_id = self.spotify.current_user()['id']
        
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
                    # TODO: сделать в будущем защиту, чтобы все абсолютно отмены работы были функцией, как ниже
                    if query.job_id in scheduler:
                        scheduler.cancel(query.job_id)         
            except Exception as e:
                app.logger.error(e)
                app.logger.error(query)
                app.logger.error(type(query))
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


def time_converter(query):
    minutes = time_worker2(query)
    if minutes:
        if minutes >= 60:
            hours = minutes / 60
            if hours >= 24:
                days = hours / 24
                return str(round(days)) + ' дн.'
            else:
                return str(round(hours)) + ' ч.'
        else:
            return str(round(minutes)) + ' мин.'
    else:
        return None
      
                           
def decode_to_bool(text):
    words = {'on', 'true'}
    if text.lower() in words:
        return True
    else:
        return False
        
def days_to_minutes(number_string):
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


def restart_job_with_new_settings(query, scheduler, UserSettings):
    if query.job_id in scheduler:
        scheduler.cancel(query.job_id)
        create_job(UserSettings, query, update_history, scheduler)


def check_worker_status(UserSettings, playlist_query, func, scheduler) -> str:
    """ Функция для проверки и перезапуска менеджера расписаний и статуса авто-обновления """
    user_query = UserSettings.user_query
    # если autoupdate = ON

    if playlist_query.update == True and playlist_query.playlist_id and UserSettings.spotify.playlist_is_following(playlist_query.playlist_id, [UserSettings.user_id])[0]:
        # если работа не задана или она не в расписании
        if not playlist_query.job_id or playlist_query.job_id not in scheduler:
            try:
                create_job(UserSettings, playlist_query, func, scheduler)
            except Exception as e:
                app.logger.error(e)
        # если работа работается, но uuid не совпадает
        if playlist_query.job_id in scheduler and user_query.last_uuid != session.get('uuid'):
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
    
    # получаем историю прослушиваний (учитывая настройки )
    history_playlist = get_current_history_list(UserSettings, history_query.fixed_dedup)
    
    # если вернутся None из-за ошибки, то выдаём ошибку
    if history_playlist == None:
        return (gettext('Can\'t connect to Spotify server'))
    
    # вытаскиваются последние прослушанные песни
    results = spotify.current_user_recently_played(limit=search_limit)
    
    #песни из recently сравниваются с историей
    recently_played_uris = [item['track']['uri'] 
                            for item in results['items'] 
                            if item['track']['uri'] not in get_items_by_key(history_playlist, 'uri') 
                            and item['track']['name'].lower() not in get_items_by_key(history_playlist, 'name') ]

    # если в настройках указан логин lasfm, то вытаскиваются данные с него
    if user_query.lastfm_username:
        try:
            username = user_query.lastfm_username
            network = pylast.LastFMNetwork(api_key='e62b095dc44b53f63137d90bce84117b', api_secret="1e3f4f44e4eae94a9cc8280f11b6fc71",
                                        username=username)
            result = network.get_user(username).get_recent_tracks(limit=search_limit)
            
            recently_played_names = { item['track']['name'].lower() for item in results['items'] if item['track']['uri'] not in get_items_by_key(history_playlist, 'uri') }
                
            # достаём данные из lastfm
            data_with_duplicates = [
                {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
                for song in result
            ]
            
            # создаём оптимизированный список без дубликатов и без треков, которые уже, вероятно, есть в истории
            last_fm_data = []
            for song in data_with_duplicates:
                if song not in last_fm_data and song['name'].lower() not in recently_played_names and song['name'].lower() not in get_items_by_key(history_playlist, 'name'):
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
                if track['uri'] not in recently_played_uris and track['uri'] not in get_items_by_key(history_playlist, 'uri'):
                    recently_played_uris.insert(0, track['uri'])
                    
        except pylast.WSError:
            logging.error('Last.fm. Connection to the API failed with HTTP code 500') 
                     
        except Exception as e:
            logging.error(e)
            
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


def get_playlist_raw_tracks(sp, playlist_id):
    return sp.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")
    

def convert_playlist(playlist_array) -> list:
    """ Перевод сырого JSON в формат, более удобный для программы """
    output = [
        {'name': item['track']['name'].lower(),
        'uri': item['track']['uri'],
        'artist': item['track']['artists'][0]['name'].lower(),
        'album': item['track']['album']['name'].lower()}
        for item in playlist_array['items']
        if item['track']
        ]
    return output


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
    
    except:
        print("Нет подключения к серверам Spotify. Переподключение через 5 минут")
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
        
        
def update_smart_playlist(user_id, UserSettings):
    sp = UserSettings.spotify
    used_playlists_ids = UsedPlaylist.query.filter_by(user_id=user_id, exclude = False, exclude_artists = False).all()
    excluded_artists_playlists = UsedPlaylist.query.filter_by(user_id=user_id, exclude_artists = True).all()
    smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
    playlist_size = smart_query.max_tracks
    
    check_by_names = True
    
    def fillup(excluded_list, key):  
        if smart_query.exclude_history:
            history_playlist = get_current_history_list(UserSettings)
            hp = frozenset(item[key] for item in history_playlist)
            excluded_list.update(hp)
            
        if smart_query.exclude_favorite:
            favorite_playlist = get_every_playlist_track(sp, sp.current_user_saved_tracks(limit=20))
            fp = frozenset(item[key] for item in favorite_playlist)
            excluded_list.update(fp)
            
    def appender(results, excluded_list, key):
        for item in results:
            if not excluded_artists_playlists:
                if item[key] not in excluded_list:
                    all_uris.append(item['uri'])
            else:
                if item[key] not in excluded_list and item['artist'] not in excluded_artists:
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
    except Exception as e:
        app.logger.error(e)
    finally:
        smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
        smart_query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
        db.session.commit()
        gc.collect()
        
 
def auto_clean(user_id, UserSettings):
    history_query = UserSettings.new_history_query()
    sp = UserSettings.spotify
    if history_query.playlist_id and UserSettings.smart_query.playlist_id:
        listened_raw = get_playlist_raw_tracks(sp, history_query.playlist_id)
        listened = get_items_by_key(convert_playlist(listened_raw), 'uri')
        sp.playlist_remove_all_occurrences_of_items(UserSettings.smart_query.playlist_id, listened)

    
def auto_clean_checker(UserSettings, scheduler):
    """ Работник с задачей, но только специально для auto cleaner """
    def create_ac_job():
        ''' То же самое, что и create_job, только для auto cleaner'''
        job = scheduler.schedule(datetime.utcnow(), auto_clean, args=[UserSettings.user_id, UserSettings], interval=3600, repeat=None)
        scheduler.enqueue_job(job)
        smart_query.ac_job_id = job.id
        db.session.commit()
        
    try:
        smart_query = UserSettings.new_smart_query()
        if smart_query.auto_clean and smart_query.playlist_id:
            if not smart_query.ac_job_id or smart_query.ac_job_id not in scheduler:
                create_ac_job()
            if smart_query.ac_job_id in scheduler and UserSettings.user_query.last_uuid != session.get('uuid'):
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


        
        