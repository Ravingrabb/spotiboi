from datetime import datetime

from modules.app_init import app
from modules.schedulers import *


def debug_page(UserSettings):
    try:
        app.logger.error('test')
        job = scheduler_s.job_class.fetch(UserSettings.smart_query.job_id, connection=Redis())
        print(job.started_at)
        print(datetime.now())
        return UserSettings.user_id
    except:
        app.logger.info('Someone unauthorized tried to visit debug page lol')