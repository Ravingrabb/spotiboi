from datetime import datetime, timedelta
import logging
from flask import session
from flask.globals import request
import spotipy
from sqlalchemy.orm import query
from start_settings import HistoryPlaylist, db, User, HistoryPlaylist, FavoritePlaylist
from flask_babel import gettext
import gc
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
            db.session.commit()

        self.user_query = User.query.filter_by(spotify_id=self.user_id).first()
        self.history_query = HistoryPlaylist.query.filter_by(user_id=self.user_id).first()
        self.favorite_query = FavoritePlaylist.query.filter_by(user_id=self.user_id).first()
            
        # Used only for HTML page. Template for settings, that will be changed in future. 
        self.settings = {
            'dedup_status': None,
            'dedup_value': 0,
            'fixed_status': None,
            'fixed_value': 0,
            'update_time': self.history_query.update_time,
            'lastfm_status': 0,
            'lastfm_value': self.user_query.lastfm_username,
            'fav_playlist': False
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
            if self.history_query.playlist_id and self.spotify.playlist_is_following(self.history_query.playlist_id, [self.user_query.spotify_id])[0]:
                self.current_playlist = self.spotify.playlist(
                    self.history_query.playlist_id, fields="name, id, images")
                self.history_playlist_data['name'] = self.current_playlist['name']
                self.history_playlist_data['id'] = self.current_playlist['id']
                self.history_playlist_data['images'] = self.current_playlist['images'][0]['url']
            # если ID плейлиста привязан, но юзер не подписан на плейлист
            elif self.history_query.playlist_id and not self.spotify.playlist_is_following(self.history_query.playlist_id, [self.user_query.spotify_id])[0]:
                self.history_query.playlist_id = None
                db.session.commit()
            # если ID плейлиста не привязан, например если только что создали плейлист History через спотибой
            elif not self.history_query.playlist_id:
                for idx, item in enumerate(self.playlists['items']):
                    if item['name'] == "History (fresh!)":
                        self.history_playlist_data['name'] = "History"
                        self.history_playlist_data['id'] = item['id']
                        self.image_item = item['images']
                    if self.image_item:
                        self.history_playlist_data['images'] = self.image_item[0]['url']
                self.history_query.playlist_id = self.history_playlist_data['id']
                db.session.commit()
                self.spotify.playlist_change_details(
                    self.history_playlist_data['id'], name="History")
        except Exception as e:
            print(e)
        finally:
            return self.history_playlist_data
        
        
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
        print(e)
            

def check_worker_status(UserSettings, playlist_query, func, scheduler) -> str:
    """ Функция для проверки работы менеджера расписаний и статуса авто-обновления """
    user_query = UserSettings.user_query
    # если autoupdate = ON
    if playlist_query.update == True and playlist_query.playlist_id and UserSettings.spotify.playlist_is_following(playlist_query.playlist_id, [UserSettings.user_id])[0]:
        # если работа не задана или она не в расписании
        if not playlist_query.job_id or playlist_query.job_id not in scheduler:
            try:
                create_job(UserSettings, playlist_query, func, scheduler)
            except Exception as e:
                print (e)
        # если работа работается, но uuid не совпадает
        if playlist_query.job_id in scheduler and user_query.last_uuid != session.get('uuid'):
            try:
                scheduler.cancel(playlist_query.job_id)
                create_job(UserSettings, playlist_query, func, scheduler)
                user_query.last_uuid = session.get('uuid')
                db.session.commit()
            except Exception as e:
                print (e)
        return "checked"
    # если autoupdate = OFF
    else:
        try:
            if playlist_query.job_id in scheduler:
                scheduler.cancel(playlist_query.job_id)
        except Exception as e:
            print(e)
        return None
        
    
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
                     
                        
    def get_items(array, search_key: str) -> str:
        for item in array:
            for key, value in item.items():
                if key == search_key:
                    yield value
        
        
    spotify = UserSettings.spotify
    history_query = UserSettings.history_query
    history_id = history_query.playlist_id
    user_query = UserSettings.new_user_query()

    search_limit = 45
    
    # получаем историю прослушиваний (учитывая настройки )
    history_playlist = get_current_history_list(UserSettings)
    
    # если вернутся None из-за ошибки, то выдаём ошибку
    if not history_playlist:
        return (gettext('Can\'t connect to Spotify server'))
    
    # вытаскиваются последние прослушанные песни
    results = spotify.current_user_recently_played(limit=search_limit)
    
    #песни из recently сравниваются с историей
    recently_played_uris = [item['track']['uri'] 
                            for item in results['items'] 
                            if item['track']['uri'] not in get_items(history_playlist, 'uri') 
                            and item['track']['name'].lower() not in get_items(history_playlist, 'name') ]

 
    # если в настройках указан логин lasfm, то вытаскиваются данные с него
    if user_query.lastfm_username:
        try:
            username = user_query.lastfm_username
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
            if history_query.fixed_capacity:
                limit_playlist_size()
            
            # print(spotify.current_user()['id'] + ": History updated in " + datetime.strftime(datetime.now(), "%H:%M:%S"))
            return (gettext('History updated'))
        # иначе пропускаем
        else:
            # print(spotify.current_user()['id'] + ": List is empty. Nothing to update.")
            return (gettext('Nothing to update'))          
    except spotipy.SpotifyException:
        return ("Nothing to add for now")
    finally:
        history_query = HistoryPlaylist.query.filter_by(user_id=user_id).first()
        history_query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
        db.session.commit()
        gc.collect()


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
 
        
def get_current_history_list(UserSettings) -> tuple:
    """ Функция получения истории прослушиваний """
        
    history_query = UserSettings.history_query
    sp = UserSettings.spotify
    playlist_id = history_query.playlist_id
    
    limit = history_query.fixed_dedup
    try:
        results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")
                
        if limit:
            tracks = get_limited_playlist_track(sp, results, limit)
        else:
            tracks = get_every_playlist_track(sp, results)
        return tuple(item for item in tracks)
    
    except:
        print("Нет подключения к серверам Spotify. Переподключение через 5 минут")
        time = datetime.now() + timedelta(minutes=5)
        history_query.last_update = datetime.strftime(time, "%H:%M:%S")
        db.session.commit()
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
        