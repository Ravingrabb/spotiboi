import os
import pylast
import spotipy
from dotenv import load_dotenv
from itertools import chain
from transliterate import translit

nibba = [
    {'uri' : 123123, 'name': 'Rube'},
    {'uri' : 141515, 'name': 'Nikich'},
    {'uri' : 152355, 'name': 'Pukich'},
]

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

def get_key_values(dictionary: dict, key: str):
    for item in dictionary:
        yield item[key]
kek = [item['uri'] 
       for item in nibba
       if item['name'] not in get_key_values(nib, 'name')]
print(nibba[0:100])