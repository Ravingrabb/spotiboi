def get_dict_items_by_key(array, search_key: str) -> str:
    """ Возможность вытащить из dict элементы по определённому ключу, только для итераций """
    for item in array:
        for key, value in item.items():
            if key == search_key:
                yield value


def get_playlist_raw_tracks(spotify, playlist_id: str):
    """ Шаблонное получение плейлиста по ID. Содержит лишние поля items, track """
    return spotify.playlist_tracks(playlist_id, fields="items(track(name, uri, artists, album)), next")


def get_playlist(spotify, playlist_id: str, limit=100) -> list:
    """ Возвращает хорший и уже конвертнутый для итераций плейлист """
    result = get_playlist_raw_tracks(spotify, playlist_id)
    if limit:
        return convert_playlist_to_list(result)
    else:
        return get_and_convert_every_playlist_tracks(spotify, result)


def convert_playlist_to_list(playlist_array) -> list:
    """ Перевод сырого dict плейлиста в формат, более удобный для программы """
    output = [
        {'name': item['track']['name'].lower(),
         'uri': item['track']['uri'],
         'artist': item['track']['artists'][0]['name'].lower(),
         'album': item['track']['album']['name'].lower()}
        for item in playlist_array['items']
        if item['track']
    ]
    return output


def get_and_convert_every_playlist_tracks(spotify, raw_results) -> list:
    """ Достать абсолютно все треки из плейлиста в обход limit c конвертацией в удобную форму для доступа.
    Лимит есть у всех плейлистов """
    tracks = convert_playlist_to_list(raw_results)
    while raw_results['next']:
        raw_results = spotify.next(raw_results)
        tracks.extend(convert_playlist_to_list(raw_results))
    return tracks


def get_limited_playlist_tracks(spotify, raw_results, tracks_limit) -> list:

    def is_reached_limit(array, limit) -> bool:
        return True if len(array) >= limit else False

    tracks = convert_playlist_to_list(raw_results)

    while raw_results['next'] and not is_reached_limit(tracks, tracks_limit):
        raw_results = spotify.next(raw_results)
        tracks.extend(convert_playlist_to_list(raw_results))

    if is_reached_limit(tracks, tracks_limit):
        tracks = tracks[:tracks_limit]

    return tracks


def fill_playlist(spotify, playlist_id: str, uris_list: list, from_top=False) -> None:
    """ Заполнение плейлиста песнями из массива. Так как ограничение
    на одну итерацию добавления - 100 треков, приходится делать это в несколько
    итераций """

    offset = 0

    while offset < len(uris_list):
        if not from_top:
            spotify.playlist_add_items(playlist_id, uris_list[offset:offset + 100])
        else:
            spotify.playlist_add_items(playlist_id, uris_list[offset:offset + 100], position=0)
        offset += 100


def fill_playlist_with_replace(sp, user_id: str, playlist_id: str, uris_list: list) -> None:
    """ Почти то же самое, что и fill playlist, только он заменяет песни, а не добавляет. Нужно для smart плейлиста"""
    offset = 0
    once = True
    while offset < len(uris_list):
        # TODO: очищать плейлист и добавлять новые песни
        if once:
            sp.user_playlist_replace_tracks(user_id, playlist_id, uris_list[offset:offset + 100])
            once = False
        else:
            sp.playlist_add_items(playlist_id, uris_list[offset:offset + 100])
        offset += 100