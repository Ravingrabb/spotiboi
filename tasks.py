from datetime import datetime
import spotipy

def test_task():
    print('test work')

def update_history(db, User, app, user, spotify):
     #создаётся плейлист из го
    history_playlist = get_current_history_list(user.history_id, spotify)
    #вытаскиваются последние прослушанные песни и сравниваются с текущей историей
    results = spotify.current_user_recently_played(limit=30)
    recently_played_uris = []
    try:
        for idx, item in enumerate(results['items']):
            track = item['track']
            if track['uri'] not in history_playlist:
                recently_played_uris.append(track['uri'])
        #если есть новые треки для добавления - они добавляются
        if recently_played_uris:
            recently_played_uris = list(dict.fromkeys(recently_played_uris))
            spotify.playlist_add_items(user.history_id, recently_played_uris)
            app.logger.info(user.spotify_id + ": History updated in " + datetime.strftime(datetime.now(), "%H:%M:%S"))
        #иначе пропускаем
        else:
            app.logger.info(user.spotify_id + ": List is empty. Nothing to update.")
    except spotipy.SpotifyException:
        print("Nothing to add for now")
    finally:
        with db.app.app_context():
            query = User.query.filter_by(spotify_id=spotify.current_user()['id']).first()
            query.last_update = datetime.strftime(datetime.now(), "%H:%M:%S")
            db.session.commit()

def get_current_history_list(playlist_id, sp):
    results = sp.playlist_tracks(playlist_id, fields="items(track(name, uri)), next")
    tracks = results['items']
    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])

    currentPlaylist = []
    for item in enumerate(tracks):
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