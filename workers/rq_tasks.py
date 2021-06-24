from .tasks import update_history, update_favorite_playlist, update_smart_playlist


def update_history_task(user_id, UserSettings):
    update_history(user_id, UserSettings)


def update_favorite_playlist_task(user_id, UserSettings):
    update_favorite_playlist(user_id, UserSettings)


def update_smart_playlist_task(user_id, UserSettings):
    update_smart_playlist(user_id, UserSettings)