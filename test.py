import os
import base64
import bisect
import time
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

os.environ['SPOTIPY_CLIENT_ID'] = str('8fdd684a5a7941458aad7b61463dae30')
os.environ['SPOTIPY_CLIENT_SECRET'] = str('e7457645935340288614702a8cbea531')

birdy_uri = 'spotify:artist:2WX2uTcsvV5OnS0inACecP'
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())

#start_time = time.time()
#main()
#print("--- %s seconds ---" % (time.time() - start_time))

def get_items_by_key(array, search_key: str) -> str:
    ''' Возможность вытащить из dict элементы по определённому ключу, только для итераций'''
    for item in array:
        for key, value in item.items():
            if key == search_key:
                
                yield value

def convert_playlist(playlist_array) -> list:
    """ Перевод сырого dict плейлиста в формат, более удобный для программы """
    output = [
        {'name': item['track']['name'].lower(),
        'uri': item['track']['uri'].replace('spotify:track:', ''),
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
    return list(tracks)

nib = [
    {'name': 'Clockwork', 'uri': 'spotify:track:2Irvz2THf0VVadfakxnGr2', 'artist': 'Palaye Royale', 'album': 'Boom Boom Room (Side A)'},
    {'name': 'Gently', 'uri': 'spotify:track:1meOrd8kJCIyypiQB6W0OI', 'artist': 'New Year Memorial', 'album': "I'll See You Tonight Wherever You Are"},
    {'name': 'Больной и злой', 'uri': 'spotify:track:3xOnnfdlNEBUYCdGLeHwVH', 'artist': 'Nike Borzov', 'album': 'Больной и злой'},
    {'name': 'Слов нет', 'uri': 'spotify:track:0VuGpDm9NeSc2zrA5q3bap', 'artist': 'Sakura', 'album': 'Greatest Hits Lo-Fi and D.I.Y.'},
    {'name': 'Доспехи бога', 'uri': 'spotify:track:1FRdU7LKrKRgEeRPpQEaf4', 'artist': 'Sakura', 'album': 'Настоящий волшебный'},
    {'name': 'На сиреневой луне', 'uri': 'spotify:track:5jews8c25ClbASJSn5inJN', 'artist': 'Leonid Agutin', 'album': 'Леонид Агутин'},
    {'name': 'Lightning', 'uri': 'spotify:track:6EslZUShkvYA9AHAYLzfcW', 'artist': 'State Champs', 'album': 'Living Proof'},
    {'name': 'Злой', 'uri': 'spotify:track:5gIvd4PaPBdvjTqrIHGrXb', 'artist': 'Samoe Bolshoe Prostoe Chislo', 'album': 'Наверное, точно'},
    {'name': 'One Of Us - Short Version', 'uri': 'spotify:track:39aRmixB9qNtCU2t8BmsC1', 'artist': 'Joan Osborne', 'album': 'The Best Of Joan Osborne 20th Century Masters The Millennium Collection'},
    {'name': 'Мачты', 'uri': 'spotify:track:36reJeV8JjPXgHYfxz72X3', 'artist': 'Zveri', 'album': 'Рома Зверь. Колыбельные'},
    {'name': 'The Red Door', 'uri': 'spotify:track:0478L3lxFG5iQfAp0EiyRI', 'artist': 'Restorations', 'album': 'LP5000'},
    {'name': 'Dancin Closer to the Edge', 'uri': 'spotify:track:4SYjDNRcH29PX1XYrotAqI', 'artist': 'Johnny Goth', 'album': 'Dancin Closer to the Edge'},
    {'name': 'Дверь', 'uri': 'spotify:track:1agw9B990wPvsFZbugvwMe', 'artist': 'Dolphin', 'album': 'Глубина резкости'},
    {'name': 'The Valley', 'uri': 'spotify:track:7tn9xt1KSqifpc9FhpnBnW', 'artist': 'Emma Ruth Rundle', 'album': 'The Valley'},
    {'name': 'Никогда-нибудь', 'uri': 'spotify:track:3AgNVBcigR8tb76iVQk4RT', 'artist': 'Husky', 'album': 'Хошхоног'},
    {'name': 'Still Blue', 'uri': 'spotify:track:7LBufCjG8Vrdnhi8bpMtGn', 'artist': 'Seaway', 'album': 'Still Blue'},
    {'name': 'Rube', 'uri': 'spotify:track:5ecwfnhiqUf971BXZHAOBG', 'artist': 'The Kickback', 'album': 'Weddings & Funerals'},
    {'name': 'Комета', 'uri': 'spotify:track:1N9FJnv60n3o8aZJPxPfYS', 'artist': 'Зарница', 'album': 'На самый главный вопрос ответ'},
    {'name': 'Hotblack', 'uri': 'spotify:track:2O874sb2cjteqljE3QAPQC', 'artist': 'Oceanship', 'album': 'Oceanship'},
    {'name': 'Ночная смена', 'uri': 'spotify:track:3MT2Z3r4KbhjXX8dCbZ5wD', 'artist': 'Pasosh', 'album': 'Снова возвращаюсь домой'},
]

#result = spotify.playlist_tracks('1rDg3P6YFx3lrfiTotG77f', fields="items(track(uri,name))", offset=1000)
recently_result = spotify.playlist_tracks('2v8wK2uDTq7Rog1T8hPJRN', fields="items(track(uri,name))", limit=100)
history_result = spotify.playlist_tracks('1rDg3P6YFx3lrfiTotG77f', fields="items(track(name, uri, artists, album)), next")

print('Get history')
start_time = time.time()
history_tracks = [item for item in get_every_playlist_track(spotify, history_result)]
print("--- %s seconds ---" % (time.time() - start_time))


print('find recently')
start_time = time.time()
sorted_history = sorted(list(get_items_by_key(history_tracks, 'uri')))
recently_played_uris = [item['track']['uri'].replace('spotify:track:', '') for item in recently_result['items'] 
                                if item['track']['uri'].replace('spotify:track:', '') not in sorted_history]
print("--- %s seconds ---" % (time.time() - start_time))

print('find recently - not sorted')
start_time = time.time()
sorted_history = list(get_items_by_key(history_tracks, 'uri'))
recently_played_uris = [item['track']['uri'].replace('spotify:track:', '') for item in recently_result['items'] 
                                if item['track']['uri'].replace('spotify:track:', '') not in sorted_history]
print("--- %s seconds ---" % (time.time() - start_time))

print('find recently binary')
start_time = time.time()
sorted_history = sorted(list(get_items_by_key(history_tracks, 'uri')))
recently_played_uris = [item['track']['uri'].replace('spotify:track:', '') for item in recently_result['items'] 
                                if bisect.bisect_left(sorted_history, item['track']['uri'].replace('spotify:track:', ''))]
print("--- %s seconds ---" % (time.time() - start_time))




# print('find recently old')
# start_time = time.time()
# sorted_history = sorted(list(get_items_by_key(history_tracks, 'uri')))
# recently_played_uris = [item['track']['uri'].replace('spotify:track:', '') for item in recently_result['items'] 
#                                 if item['track']['uri'].replace('spotify:track:', '') not in get_items_by_key(history_tracks, 'uri')]
# print("--- %s seconds ---" % (time.time() - start_time))
