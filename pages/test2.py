from flask import render_template


def test_mood_page(UserSettings):
    sp = UserSettings.spotify
    data = sp.audio_features(['spotify:artist:0LsTFjEB1IIrh7IlTxs1GY',
                              'spotify:album:2edH6FFfrv00LqR3fuQpWr',
                              'spotify:track:2ynCjjrmED5CfiVn2ZLkUk',
                              'spotify:track:1zj2hXKBgOma076z0Ya96I',
                              'spotify:track:1ZsVFKysSROWBWZX3ZG1Gu',
                              'spotify:track:70ObidosunvN8jTLZuZQWO',
                              'spotify:track:4yaoVEBN4EDtFSkmXoQBd1',
                              'spotify:track:4IlVAZQ9gDZGQ0CILBRLVB',
                              'spotify:track:17vC29osvs1ArI3GDgZWzm',
                              'spotify:track:3ScyefUwfkGi0g6CaCemRc',
                              'spotify:track:68pRDxzsRVXjVojzrU5NNm',
                              'spotify:track:329yUC0343IqdAHu2dLVkJ',
                              'spotify:track:4W9n2JpWokIEZdBA3Kq1Ep',
                              'spotify:track:36reJeV8JjPXgHYfxz72X3',
                              'spotify:track:3s2MZsEfiMe7ZjiRtun6wv'])

    def mean(numbers):
        return float(sum(numbers)) / max(len(numbers), 1)

    danceability = []
    energy = []
    valence = []
    tempo = []
    for track in data:
        if track:
            danceability.append(track['danceability'])
            energy.append(track['energy'])
            valence.append(track['valence'])
            tempo.append(track['tempo'])
    data.append('danceability - ' + str(mean(danceability)))
    data.append('energy - ' + str(mean(energy)))
    data.append('valence - ' + str(mean(valence)))
    data.append('tempo - ' + str(mean(tempo)))

    results = sp.playlist_tracks('spotify:playlist:2v8wK2uDTq7Rog1T8hPJRN', fields="items(track(uri)), next")

    track_moods = sp.audio_features([item['track']['uri'] for item in results['items']])
    tracks_to_delete = [song['uri'] for song in track_moods if song['danceability'] > 0.53 or song['energy'] > 0.5]
    sp.playlist_remove_all_occurrences_of_items('spotify:playlist:2v8wK2uDTq7Rog1T8hPJRN', tracks_to_delete)
    return render_template('test.html', queries=track_moods)