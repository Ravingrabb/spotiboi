from datetime import datetime
from flask import session
import spotipy
from app import db, User
from pprint import pprint


def update_history(user_id, history_id, spotify):
    query = User.query.filter_by(spotify_id=user_id).first()
    results_tracks_number = 30
    # получаем историю прослушиваний (учитывая настройки )
    history_playlist = get_current_history_list(history_id, spotify, query)
    # вытаскиваются последние прослушанные песни и сравниваются с текущей историей
    results = spotify.current_user_recently_played(limit=results_tracks_number)
    recently_played_uris = []
    try:
        for idx, item in enumerate(results['items']):
            track = item['track']
            if track['uri'] not in history_playlist:
                recently_played_uris.append(track['uri'])
        # если есть новые треки для добавления - они добавляются в History
        if recently_played_uris:
            recently_played_uris = list(dict.fromkeys(recently_played_uris))
            spotify.playlist_add_items(history_id, recently_played_uris, position=0)
            # если стоит настройка ограничения плейлиста по размеру
            if query.fixed_capacity:
                playlist_size = spotify.playlist_tracks(history_id, fields='total')
                if playlist_size['total'] >= query.fixed_capacity:
                    result = spotify.playlist_tracks(history_id, fields="items(track(uri,name))", limit=results_tracks_number, offset=query.fixed_capacity)
                    tracks_to_delete = []
                    for item in result['items']:
                        tracks_to_delete.append(item['track']['uri'])
                    spotify.playlist_remove_all_occurrences_of_items(history_id, tracks_to_delete)
            print(spotify.current_user()['id'] + ": History updated in " + datetime.strftime(datetime.now(), "%H:%M:%S"))
            return ("History updated in " + datetime.strftime(datetime.now(), "%H:%M:%S"))
        # иначе пропускаем
        else:
            print(spotify.current_user()['id'] + ": List is empty. Nothing to update.")
            return ("List is empty. Nothing to update.")
    except spotipy.SpotifyException:
        print("Nothing to add for now")
        return ("Nothing to add for now")
    finally:
        query = User.query.filter_by(spotify_id=user_id).first()
        query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
        db.session.commit()


def get_current_history_list(playlist_id, sp, query):
    #если включена настройка ограничения дубликатора
    if query.fixed_dedup:
        if query.fixed_dedup > 100:
            limit = query.fixed_dedup
            results = sp.playlist_tracks(playlist_id, fields="items(track(uri)), next")
            tracks = results['items']
            while results['next'] and check_len(tracks, limit):
                results = sp.next(results)
                tracks.extend(results['items'])
                isEnough = check_len(tracks, limit)
            if not check_len(tracks, limit):
                diff = len(tracks) - limit
                tracks = tracks[:len(tracks)-diff]

        if query.fixed_dedup <= 100:
            results = sp.playlist_tracks(playlist_id, fields="items(track(uri))", limit=query.fixed_dedup)
            tracks = results['items']
    #если ВЫКЛ
    else:
        results = sp.playlist_tracks(playlist_id, fields="items(track(uri)), next")
        tracks = results['items']
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])

    currentPlaylist = set()
    for item in tracks:
        currentPlaylist.add(item['track']['uri'])
    return currentPlaylist

def check_len(ar, limit):
    if len(ar) >= limit:
        return False
    else:
        return True
