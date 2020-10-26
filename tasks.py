from datetime import datetime
import logging
from logging import log
from flask import session
import spotipy
from sqlalchemy.orm import query
from start_settings import db, User, scheduler
from flask_babel import gettext
import pylast


class UserSettings():
    
    def __init__(self, auth_manager) -> None:
        
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        self.user_id = self.spotify.current_user()['id']
        
        if not User.query.filter_by(spotify_id=self.user_id).first():
            db.session.add(User(spotify_id=self.user_id, update=False))
            db.session.commit()
            self.query = User.query.filter_by(spotify_id=self.user_id).first()
        else:
            self.query = User.query.filter_by(spotify_id=self.user_id).first()
            
        self.settings = {
            'dedup_status': None,
            'dedup_value': 0,
            'fixed_status': None,
            'fixed_value': 0,
            'update_time': self.query.update_time,
            'lastfm_status': 0,
            'lastfm_value': self.query.lastfm_username
        }
     
        
    def new_query(self):
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
            
            
    def check_worker_status(self):
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
        

    def settings_worker(self) -> None:
        if self.query.fixed_dedup and self.query.fixed_dedup > 0:
            self.settings['dedup_status'] = 'checked'
            self.settings['dedup_value'] = self.query.fixed_dedup
        if self.query.fixed_capacity and self.query.fixed_capacity > 0:
            self.settings['fixed_status'] = 'checked'
            self.settings['fixed_value'] = self.query.fixed_capacity
        if self.query.lastfm_username:
            self.settings['lastfm_status'] = 'checked'
    

    def attach_playlist(self):
        """ Функция, необходимая только дял отображение плейлиста юзера, данные
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
            result = spotify.playlist_tracks(history_id, fields="items(track(uri,name))", limit=results_tracks_number, offset=query.fixed_capacity)
            tracks_to_delete = []
            for item in result['items']:
                tracks_to_delete.append(item['track']['uri'])
            spotify.playlist_remove_all_occurrences_of_items(history_id, tracks_to_delete)
    
    def eliminate_duplicates(history_playlist, results, dedup_by_name) -> list:
        ''' Функция проверки дубликатов с историей прослушиваний по двум признакам -
        только по URI или только по названиям и артистам
        TODO: добавить в history_playlist поле name, artist '''
        if not dedup_by_name:
            def get_uris(history_playlist):
                for name in history_playlist:
                    yield name['uri']
                    
            recently_played_uris = [
                item['track']['uri'] 
                for idx, item in enumerate(results['items']) 
                if item['track']['uri'] not in history_playlist]
        else:
            def get_names(history_playlist):
                for name in history_playlist:
                    yield name['name']
                    
            recently_played_uris = [
                item['track']['uri'] 
                for idx, item in enumerate(results['items']) 
                if item['track']['name'] not in history_playlist]
        
        return recently_played_uris
            
       
    
    # --------- CODE STARTS HERE ----------

    query = User.query.filter_by(spotify_id=user_id).first()
    results_tracks_number = 30
    
    # получаем историю прослушиваний (учитывая настройки )
    history_playlist = get_current_history_list(history_id, spotify, query)
    # вытаскиваются последние прослушанные песни
    results = spotify.current_user_recently_played(limit=results_tracks_number)
    
    #песни сравниваются с историей
    recently_played_uris = [
        item['track']['uri'] 
        for item in results['items'] 
        if item['track']['uri'] not in history_playlist]
 
    # если в настройках указан логин lasfm, то вытаскиваются данные с него
    print ('pre-last')
    if query.lastfm_username:
        try:
            username = query.lastfm_username
            network = pylast.LastFMNetwork(api_key='b6d8eb5b11e5ea1e81a3f116cfa6169f', api_secret="7108511ff8fee65ba231fba99902a1d5",
                                        username=username)
            result = network.get_user(username).get_recent_tracks(limit=30)
                
            # достаём данные из lastfm
            last_fm_data = [
                {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
                for song in result
            ]
            
            # переводим эти данные в uri спотифай
            last_fm_data_to_uri = []
            for q in last_fm_data:
                try:
                    track = spotify.search(q['name'] + " artist:" + q['artist'] + " album:" + q['album'], limit=1)['tracks']['items'][0]['uri']
                    last_fm_data_to_uri.append(track)
                except:
                    continue
            print (last_fm_data_to_uri)
            last_fm_data_to_uri.reverse()      
                             
            # проверяем все результаты на дубликаты и если всё ок - передаём в плейлист
            for track in last_fm_data_to_uri:
                if track not in recently_played_uris and track not in history_playlist:
                    recently_played_uris.insert(0, track)

        except pylast.WSError:
            logging.error('Last.fm. Connection to the API failed with HTTP code 500')          
        except Exception as e:
            logging.error(e)
            
    try:  
        # если есть новые треки для добавления - они добавляются в History
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
        print("Nothing to add for now")
        return ("Nothing to add for now")
    
    finally:
        query = User.query.filter_by(spotify_id=user_id).first()
        query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
        try:
            db.session.commit()
        except Exception as e:
            print(e)
            
        

def get_current_history_list(playlist_id: "str", sp, query) -> set:
    """ Функция получения истории прослушиваний """
    
    def check_len(ar, limit) -> bool:
        if len(ar) >= limit:
            return False
        else:
            return True
        
    
    # если  FIXED DEDUP ON
    if query.fixed_dedup:
        if query.fixed_dedup > 100:
            limit = query.fixed_dedup
            results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri)), next")
            tracks = results['items']
            while results['next'] and check_len(tracks, limit):
                results = sp.next(results)
                tracks.extend(results['items'])
            if not check_len(tracks, limit):
                diff = len(tracks) - limit
                tracks = tracks[:len(tracks)-diff]
        if query.fixed_dedup <= 100:
            results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri))", limit=query.fixed_dedup)
            tracks = results['items']
    # если FIXED DEDUP OFF, добавляются все треки
    else:
        results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri)), next")
        tracks = results['items']
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])
            
    currentPlaylist = {
        item['track']['uri']
        for item in tracks
    }  
    
    return currentPlaylist

