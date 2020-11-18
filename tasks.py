from datetime import datetime, timedelta
import logging
from logging import log
from flask import session
from flask.globals import request
import json
import spotipy
from sqlalchemy.orm import query
from start_settings import db, User, scheduler
from flask_babel import gettext
#for last
import pylast
from itertools import chain
from transliterate import detect_language


class UserSettings():
    
    def __init__(self, auth_manager) -> None:
        # авторизация и получаем id
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        self.user_id = self.spotify.current_user()['id']
        
        # если юзера не сущестует в БД, то создаётся запись
        if not User.query.filter_by(spotify_id=self.user_id).first():
            db.session.add(User(spotify_id=self.user_id, update=False))
            db.session.commit()
            self.query = User.query.filter_by(spotify_id=self.user_id).first()
        else:
            self.query = User.query.filter_by(spotify_id=self.user_id).first()
            
        # Used only for HTML page. Template for settings, that will be changed in future. 
        self.settings = {
            'dedup_status': None,
            'dedup_value': 0,
            'fixed_status': None,
            'fixed_value': 0,
            'update_time': self.query.update_time,
            'lastfm_status': 0,
            'lastfm_value': self.query.lastfm_username,
            'fav_playlist': False
        }
     
    def settings_worker(self) -> None:
        if self.query.fixed_dedup and self.query.fixed_dedup > 0:
            self.settings['dedup_status'] = 'checked'
            self.settings['dedup_value'] = self.query.fixed_dedup
            
        if self.query.fixed_capacity and self.query.fixed_capacity > 0:
            self.settings['fixed_status'] = 'checked'
            self.settings['fixed_value'] = self.query.fixed_capacity
            
        if self.query.lastfm_username:
            self.settings['lastfm_status'] = 'checked'
            
        if self.query.favorite_playlist:
            self.fav_id = json.loads(self.query.favorite_playlist)['id']
            if self.spotify.playlist_is_following(self.fav_id, [self.query.spotify_id])[0]:
                self.settings['fav_playlist'] = True
            
            
    def new_query(self):
        ''' Function to create and return clear and new database query'''
        return User.query.filter_by(spotify_id=self.user_id).first()


    def create_job(self, job_time=30) -> None:
        if self.query.update_time:
            job_time = int(self.query.update_time)
        self.job_time = job_time * 60
        try:
            self.job = scheduler.schedule(datetime.utcnow(), update_history, args=[
                                    self.query.spotify_id, self.query.history_id, self.spotify], interval=self.job_time, repeat=None)
            scheduler.enqueue_job(self.job)
            self.query.job_id = self.job.id
            db.session.commit()
        except Exception as e:
            print(e)
            
            
    def check_worker_status(self) -> str:
        """ Функция для проверки работы менеджера расписаний и статуса авто-обновления """
        self.query = User.query.filter_by(spotify_id=self.user_id).first()
        
        # если autoupdate = ON
        if self.query.update == True and self.query.history_id:
            # если работа не задана или она не в расписании
            if not self.query.job_id or self.query.job_id not in scheduler:
                try:
                    self.create_job()
                except Exception as e:
                    print (e)
            # если работа работается, но uuid не совпадает
            if self.query.job_id in scheduler and self.query.last_uuid != session.get('uuid'):
                try:
                    scheduler.cancel(self.query.job_id)
                    self.create_job()
                    self.query.last_uuid = session.get('uuid')
                    db.session.commit()
                except Exception as e:
                    print (e)
            return "checked"
        # если autoupdate = OFF
        else:
            try:
                if self.query.job_id in scheduler:
                    scheduler.cancel(self.query.job_id)
            except Exception as e:
                print(e)
            return None
        
        
    def check_worker_status2(self, update: bool, playlist_id: str, job_id: str) -> str:
        """ Функция для проверки работы менеджера расписаний и статуса авто-обновления """
        # если autoupdate = ON
        if update == True and playlist_id:
            # если работа не задана или она не в расписании
            if not job_id or job_id not in scheduler:
                try:
                    self.create_job()
                except Exception as e:
                    print (e)
            # если работа работается, но uuid не совпадает
            if job_id in scheduler and self.query.last_uuid != session.get('uuid'):
                try:
                    scheduler.cancel(job_id)
                    self.create_job()
                    self.query.last_uuid = session.get('uuid')
                    db.session.commit()
                except Exception as e:
                    print (e)
            return "checked"
        # если autoupdate = OFF
        else:
            try:
                if job_id in scheduler:
                    scheduler.cancel(job_id)
            except Exception as e:
                print(e)
            return None


    def time_worker(self) -> int:
        self.query = self.new_query()
        if self.query.last_update:
            self.time_past = self.query.last_update
            self.time_now = datetime.now()
            self.FMT = '%H:%M:%S'
            self.duration = self.time_now - datetime.strptime(self.time_past, self.FMT)
            self.time_difference = self.duration.seconds // 60
            return self.time_difference
        else:
            return None


    def attach_playlist(self):
        """ Функция, необходимая только для отображения плейлиста юзера, данные
        которого находятся в базе данных """
        
        # создаётся заготовок пустого плейлиста
        self.history_playlist_data = {
            'name': None,
            'id': None,
            'images': None
        }
        
        # посмотреть все плейлисты юзера
        try:
            # сморим все плейлисты
            self.playlists = self.spotify.current_user_playlists()
            # если привязан ID плейлиста и юзер подписан на него, то выводим инфу
            if self.query.history_id and self.spotify.playlist_is_following(self.query.history_id, [self.query.spotify_id])[0]:
                self.current_playlist = self.spotify.playlist(
                    self.query.history_id, fields="name, id, images")
                self.history_playlist_data['name'] = self.current_playlist['name']
                self.history_playlist_data['id'] = self.current_playlist['id']
                self.history_playlist_data['images'] = self.current_playlist['images'][0]['url']
            # если ID плейлиста привязан, но юзер не подписан на плейлист
            elif self.query.history_id and not self.spotify.playlist_is_following(self.query.history_id, [self.query.spotify_id])[0]:
                self.query.history_id = None
                db.session.commit()
            # если ID плейлиста не привязан, например если только что создали плейлист History через спотибой
            elif not self.query.history_id:
                for idx, item in enumerate(self.playlists['items']):
                    if item['name'] == "History (fresh!)":
                        self.history_playlist_data['name'] = "History"
                        self.history_playlist_data['id'] = item['id']
                        self.image_item = item['images']
                    if self.image_item:
                        self.history_playlist_data['images'] = self.image_item[0]['url']
                self.query.history_id = self.history_playlist_data['id']
                db.session.commit()
                self.spotify.playlist_change_details(
                    self.history_playlist_data['id'], name="History")
        except:
            print(self.query.spotify_id +
                            ': Плейлист не прикреплён, нечего показывать')
        finally:
            return self.history_playlist_data
        
    
def update_history(user_id, history_id, spotify) -> str:
    """ Функция обновления истории """
               
    def limit_playlist_size():
        """ Обрезка плейлиста, если стоит настройка фиксированного плейлиста """
        playlist_size = spotify.playlist_tracks(history_id, fields='total')
        if playlist_size['total'] >= query.fixed_capacity:
            result = spotify.playlist_tracks(history_id, fields="items(track(uri,name))", limit=search_limit, offset=query.fixed_capacity)
            tracks_to_delete = []
            for item in result['items']:
                tracks_to_delete.append(item['track']['uri'])
            spotify.playlist_remove_all_occurrences_of_items(history_id, tracks_to_delete)   
                     
                        
    def get_items(array, search_key: str) -> str:
        for item in array:
            for key, value in item.items():
                if key == search_key:
                    yield value
        
        
    # --------- CODE STARTS HERE ----------

    query = User.query.filter_by(spotify_id=user_id).first()
    search_limit = 45
    
    # получаем историю прослушиваний (учитывая настройки )
    history_playlist = get_current_history_list(history_id, spotify, query)
    
    # вытаскиваются последние прослушанные песни
    results = spotify.current_user_recently_played(limit=search_limit)
    
    #песни из recently сравниваются с историей
    recently_played_uris = [item['track']['uri'] 
                            for item in results['items'] 
                            if item['track']['uri'] not in get_items(history_playlist, 'uri') 
                            and item['track']['name'].lower() not in get_items(history_playlist, 'name') ]

 
    # если в настройках указан логин lasfm, то вытаскиваются данные с него
    if query.lastfm_username:
        try:
            username = query.lastfm_username
            network = pylast.LastFMNetwork(api_key='e62b095dc44b53f63137d90bce84117b', api_secret="1e3f4f44e4eae94a9cc8280f11b6fc71",
                                        username=username)
            result = network.get_user(username).get_recent_tracks(limit=search_limit)
            
            recently_played_names = { item['track']['name'].lower() for item in results['items'] if item['track']['uri'] not in get_items(history_playlist, 'uri') }
                
            # достаём данные из lastfm
            data_with_duplicates = [
                {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
                for song in result
            ]
            
            # создаём оптимизированный список без дубликатов и без треков, которые уже, вероятно, есть в истории
            last_fm_data = []
            for song in data_with_duplicates:
                if song not in last_fm_data and song['name'].lower() not in recently_played_names and song['name'].lower() not in get_items(history_playlist, 'name'):
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
                if track['uri'] not in recently_played_uris and track['uri'] not in get_items(history_playlist, 'uri'):
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
            if query.fixed_capacity:
                limit_playlist_size()
            
            print(spotify.current_user()['id'] + ": History updated in " + datetime.strftime(datetime.now(), "%H:%M:%S"))
            return (gettext('History updated'))
        # иначе пропускаем
        else:
            print(spotify.current_user()['id'] + ": List is empty. Nothing to update.")
            return (gettext('Nothing to update'))          
    except spotipy.SpotifyException:
        return ("Nothing to add for now")
    finally:
        query = User.query.filter_by(spotify_id=user_id).first()
        query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
        db.session.commit()
            
 
def convert_playlist(playlist_array) -> list:
    """ Перевод сырого JSON в формат, более удобный для программы """
    
    output = [
        {'name': item['track']['name'].lower(),
        'uri': item['track']['uri'],
        'artist': item['track']['artists'][0]['name'].lower(),
        'album': item['track']['album']['name'].lower()} 
        for item in playlist_array['items']]
    return output


def get_every_playlist_track(spotify, raw_results: list) -> list:
    """ Достать абсолютно все треки из плейлиста в обход limit """
    
    tracks = convert_playlist(raw_results)
    while raw_results['next']:
        raw_results = spotify.next(raw_results)
        tracks.extend(convert_playlist(raw_results))
    return tracks


def get_limited_playlist_track(spotify, raw_results, limit) -> list:
    
    def is_reached_limit(array, limit) -> bool:
            if len(array) >= limit:
                return True
            else:
                return False
            
    tracks = convert_playlist(raw_results)
    
    while raw_results['next'] and not is_reached_limit(tracks, limit):
        raw_results = spotify.next(raw_results)
        tracks.extend(convert_playlist(raw_results))  
        
    if is_reached_limit(tracks, limit):
        tracks = tracks[:limit] 
        
    return tracks
 
        
def get_current_history_list(playlist_id: str, sp, query) -> tuple:
    """ Функция получения истории прослушиваний """
        
    def get_tracks():
        limit = query.fixed_dedup
        try:
            results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")
                    
            if limit:
                return get_limited_playlist_track(sp, results, limit)
            else:
                return get_every_playlist_track(sp, results)
        except sp.requests.exceptions.ReadTimeout:
            print("Нет подключения к серверам Spotify. Переподключение через 5 минут")
            time = datetime.now() + timedelta(minutes=5)
            query.last_update = datetime.strftime(time, "%H:%M:%S")
            db.session.commit()
    
    tracks = get_tracks()
    
    return tuple(item for item in tracks)



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



def create_liked_playlist(UserSettings) -> None:
    """ Создать новый плейлист, содержащий только лайкнутые треки """
    sp = UserSettings.spotify
    user_id = UserSettings.user_id
    query = UserSettings.new_query()
    results = sp.current_user_saved_tracks(limit=20)
    
    if query.favorite_playlist:
        fav_id = json.loads(query.favorite_playlist)['id']
        if sp.playlist_is_following(fav_id, [user_id])[0]:
            # получаем актуальный список треков из saved
            new_track_uris = tuple( item['uri'] for item in get_every_playlist_track(sp, results) )
            
            # получаем список песен из плейлиста favorites
            fav_playlist_results = sp.playlist_tracks(fav_id)
            fav_playlist_uris = tuple( item['uri'] for item in get_every_playlist_track(sp, fav_playlist_results) )
            
            #добавляем новые треки
            to_add = [ uri for uri in new_track_uris if uri not in fav_playlist_uris]
            if to_add: 
                fill_playlist(sp, fav_id, to_add, from_top=True)
            
            #удаляем не акутальные
            to_delete = [ uri for uri in fav_playlist_uris if uri not in new_track_uris]
            if to_delete:
                sp.playlist_remove_all_occurrences_of_items(fav_id, to_delete)
        
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
                data = {"id" : item['id'], "update": False}
                query.favorite_playlist = json.dumps(data)
                db.session.commit()
                fill_playlist(sp, item['id'], track_uris)
                break
