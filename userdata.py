import traceback
from datetime import datetime

import requests
import spotipy

from modules import User, db, HistoryPlaylist, FavoritePlaylist, SmartPlaylist, app


class UserSettings:
    __slots__ = ('spotify', 'user_id', 'user_query', 'history_query', 'favorite_query', 'smart_query', 'settings',
                 'playlist_data', 'playlists', 'current_playlist')

    def __init__(self, auth_manager):
        # авторизация и получаем id
        try:
            self.spotify = spotipy.Spotify(auth_manager=auth_manager)
            self.user_id = self.spotify.current_user()['id']

            # если юзера не сущестует в БД, то создаётся запись. Тут же создаётся запись для плейлиста
            if not User.query.filter_by(spotify_id=self.user_id).first():
                db.session.add(User(spotify_id=self.user_id))
                db.session.add(HistoryPlaylist(user_id=self.user_id))
                db.session.add(FavoritePlaylist(user_id=self.user_id))
                db.session.add(SmartPlaylist(user_id=self.user_id, max_tracks=100))
                db.session.commit()

            self.user_query = User.query.filter_by(spotify_id=self.user_id).first()
            self.history_query = HistoryPlaylist.query.filter_by(user_id=self.user_id).first()
            self.favorite_query = FavoritePlaylist.query.filter_by(user_id=self.user_id).first()
            self.smart_query = SmartPlaylist.query.filter_by(user_id=self.user_id).first()

            self.settings = None
        except spotipy.exceptions.SpotifyException as e:
            app.logger.error(e)

    def get_playlists_settings(self) -> dict:
        """ Get History, Smart and Favorite playlists settings to display them on HTML pages """

        # init empty dict
        self.settings = {
            # history playlist
            'dedup_status': None,
            'dedup_value': 0,
            'fixed_status': None,
            'fixed_value': 0,
            'update_time': self.history_query.update_time,
            'lastfm_status': 0,
            'lastfm_value': self.user_query.lastfm_username,
            # fav playlist
            'fav_playlist': False,
            # smart playlist
            'max_tracks': self.smart_query.max_tracks,
            'exclude_history': self.smart_query.exclude_history,
            'exclude_favorite': self.smart_query.exclude_favorite,
            'smart_update_time': round(self.smart_query.update_time / 1440)
        }

        # fill settings with data based on database data
        if self.history_query.fixed_dedup and self.history_query.fixed_dedup > 0:
            self.settings['dedup_status'] = 'checked'
            self.settings['dedup_value'] = self.history_query.fixed_dedup

        if self.history_query.fixed_capacity and self.history_query.fixed_capacity > 0:
            self.settings['fixed_status'] = 'checked'
            self.settings['fixed_value'] = self.history_query.fixed_capacity

        if self.user_query.lastfm_username:
            self.settings['lastfm_status'] = 'checked'

        if self.favorite_query.playlist_id:
            if self.spotify.playlist_is_following(self.favorite_query.playlist_id, [self.user_query.spotify_id])[0]:
                self.settings['fav_playlist'] = True

        if self.settings['exclude_history']:
            self.settings['exclude_history'] = 'checked'

        if self.settings['exclude_favorite']:
            self.settings['exclude_favorite'] = 'checked'

        return self.settings

    def new_user_query(self) -> User:
        """ Create new User query"""
        return User.query.filter_by(spotify_id=self.user_id).first()

    def new_history_query(self) -> HistoryPlaylist:
        """ Create new HistoryPlaylist query"""
        return HistoryPlaylist.query.filter_by(user_id=self.user_id).first()

    def new_smart_query(self) -> SmartPlaylist:
        """ Create new SmartPlaylist query"""
        return SmartPlaylist.query.filter_by(user_id=self.user_id).first()
