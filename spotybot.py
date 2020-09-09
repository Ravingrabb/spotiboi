import spotipy  
import time
import schedule
import requests
import dotenv
import os

#из функции get_playlist генерируется список uri со всеми трекми из трелиста history
def create_current_history_list(playlist_id, sp):
    playlistResult = get_playlist_tracks(playlist_id, sp)
    currentPlaylist = []
    for item in enumerate(playlistResult):
        track = item[1]['track']
        currentPlaylist.append(track['uri'])
    return currentPlaylist

def get_playlist_tracks(playlist_id, sp):
    results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri)), next")
    tracks = results['items']
    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])
    return tracks

#функция добавления прослушанного в историю
def recent_to_history():

    currentPlaylist = create_recent_list()

    #вытаскиваются последние прослушанные песни и сравниваются с текущей историей
    results = sp.current_user_recently_played(limit=30)
    recently_played_uris = []
    try:
        for idx, item in enumerate(results['items']):
            track = item['track']
            if track['uri'] not in currentPlaylist:
                recently_played_uris.append(track['uri'])

        #если есть новые треки для добавления - они добавляются
        if recently_played_uris:
            sp.playlist_add_items(HISTORY_PLAYLIST,recently_played_uris)
            print("History updated at " + time.asctime())
        #иначе пропускаем
        else:
            print("List is empty")
    except spotipy.SpotifyException:
        print("Nothing to add for now")


#расписание
recent_to_history()
schedule.every().hour.do(recent_to_history)

#скрипт для постоянной работы крона
while 1:
    schedule.run_pending()
    time.sleep(1)