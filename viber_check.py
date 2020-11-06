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
