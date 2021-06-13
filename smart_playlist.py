import base64
import os
import random

from modules.database import db, HistoryPlaylist, SmartPlaylist, UsedPlaylist


def url_to_plid(url: str) -> str:
    """ Перевод URL в ID"""

    if ' ' in url:
        url = url.replace(' ', '')

    if 'https://open.spotify.com/playlist/' in url:
        t = url.replace('https://open.spotify.com/playlist/', '')
        output = t
        if '?' in t:
            t = t.split('?')
            output = t[0]
        return output

    elif "spotify:playlist:" in url:
        output = url.replace('spotify:playlist:', '')
        return output

    else:
        return None


def is_exist(url: str, UserSettings) -> str:
    """ Проверка, существует ли такой плейлист в пределах спотифай """

    playlist_id = url_to_plid(url)
    try:
        UserSettings.spotify.playlist(playlist_id, fields="id")
        return playlist_id
    except Exception as e:
        print(e)
        return None


def check_and_get_pldata(url: str, UserSettings) -> dict:
    if is_exist(url, UserSettings):
        return UserSettings.spotify.playlist(url_to_plid(url), fields="name, images")


def check_data(data, UserSettings) -> list:
    ''' Проверяет полученные данные из AJAX и возвращает хорошие URL'''
    output = []

    def append_good_playlist(url):
        '''Функция проверят URL на существование. 
        Если такой плейлист существует, то добавляет его ID в общую стопку'''

        good_id = is_exist(url, UserSettings)
        if good_id and good_id not in output:
            output.append(good_id)

    if ';' in data:
        data = data.split(';')
        for url in data:
            append_good_playlist(url)
    else:
        append_good_playlist(data)

    return output


def sort_playlist(playlists: list):
    top = list(p for p in playlists if "Mix" in p['name'])
    high = list(p for p in playlists if "Weekly" in p['name'] or "Radar" in p['name'] and p not in top)
    mid = list(p for p in playlists if p not in top and p not in high and "Spotify" in p['owner'])
    low = list(p for p in playlists if p not in top and p not in mid and p not in high)
    return top + high + mid + low


def create_new_smart_playlist(data, UserSettings):
    '''Проверяются URL и если всё ок - создаётся новый плейлист вместе с этими плейлистами'''

    def clear_db_data(user_id):
        UsedPlaylist.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    user_id = UserSettings.user_id
    output = check_data(data, UserSettings)

    if output:
        # очищаем все данные у определённого id, если в базе есть плейлисты
        if UsedPlaylist.query.filter_by(user_id=user_id):
            clear_db_data(user_id)
        # создаём плейлист
        data = UserSettings.spotify.user_playlist_create(
            user=user_id,
            name='Smart Playlist',
            description='Smart Playlist. Created by SpotiBoi'
        )
        # работа с картинкой
        try:
            cur_path = os.path.dirname(__file__)
            new_path = os.path.relpath('static/img/covers/smart-playlist/', cur_path)
            file = 'static/img/covers/smart-playlist/' + random.choice(os.listdir(new_path))
            with open(file, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read())
            UserSettings.spotify.playlist_upload_cover_image(data['id'], encoded_string.decode('utf-8'))
        except Exception as e:
            print(e)
            print('Cant load image to new playlist. Skipped')

        # добавляем данные в БД
        smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
        smart_query.playlist_id = data['id']

        for id in output:
            db.session.add(UsedPlaylist(playlist_id=id, user_id=user_id, attached_playlist_id=data['id']))
        db.session.commit()


def add_playlists_to_smart(data, UserSettings, exclude_artists=False, exclude_tracks=False):
    user_id = UserSettings.user_id
    output = check_data(data, UserSettings)
    if output:
        smart_query = SmartPlaylist.query.filter_by(user_id=user_id).first()
        for id in output:
            db.session.add(UsedPlaylist(playlist_id=id, user_id=user_id, attached_playlist_id=smart_query.playlist_id,
                                        exclude=exclude_tracks, exclude_artists=exclude_artists))
        db.session.commit()


def get_main_attached_ids(UserSettings):
    smart_query = SmartPlaylist.query.filter_by(user_id=UserSettings.user_id).first()
    history_query = HistoryPlaylist.query.filter_by(user_id=UserSettings.user_id).first()

    output = []
    if smart_query.playlist_id:
        output.append(smart_query.playlist_id)
    if history_query.playlist_id:
        output.append(history_query.playlist_id)

    return output
