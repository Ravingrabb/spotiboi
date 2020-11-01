import os
import pylast
import spotipy
from dotenv import load_dotenv
from itertools import chain
from transliterate import translit

nibba = [
    {'uri' : 123123, 'name': 'Oleg'},
    {'uri' : 141515, 'name': 'Nikich'},
    {'uri' : 152355, 'name': 'Pukich'},
]

names = {
    'suka', 'Oleg'
}

def get_names(nibba):
    for name in nibba:
        yield name['name']


# --------------------------------
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    
auth_manager = spotipy.oauth2.SpotifyOAuth(scope='playlist-modify-private user-read-recently-played playlist-modify-public',
                                               show_dialog=True)
spotify = spotipy.Spotify(auth_manager=auth_manager)

    
API_KEY = os.environ['LASTFM_API_KEY']
API_SECRET = os.environ['LASTFM_API_SECRET']
username = "Ravingrabb"

network = pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET,
                            username=username)
result = network.get_user(username).get_recent_tracks(limit=20)

# достаём данные из lastfm
last_fm_data = [
    {'name': song[0].title, 'artist': song[0].artist.name, 'album': song.album}
    for song in result
]
# переводим эти данные в uri спотифай
last_fm_data_to_uri = []
test = []
test2 = []
for q in last_fm_data:
    try:
        # 1 попытка: проверка как есть
        track = spotify.search(q['name'] + " artist:" + q['artist'] + " album:" + q['album'], limit=1)['tracks']['items'][0]['uri']
        last_fm_data_to_uri.append(track)    
        test.append(q['name'] + ' ' + q['artist'] + ' --- ' + track)
    except:
        try:
            # 2 попытка: ищем по исполнителям, убирая букву ё

            q['artist'] = q['artist'].replace('ё', 'е')
            tr_artist = translit(q['artist'].lower(), 'ru', reversed=True)
            track = spotify.search(q['name'], limit=20, type='track')['tracks']['items']
            for item in track:
                print(q['artist'].lower())
                print(tr_artist.lower())
                print(item['artists'][0]['name'].lower())
                if q['artist'].lower() == item['artists'][0]['name'].lower() or tr_artist.lower() == item['artists'][0]['name'].lower():
                    last_fm_data_to_uri.append(item['uri'])
                    test.append(q['name'] + ' ' + q['artist'] + ' --- ' + item['uri'])
                    break          
        except:
            continue