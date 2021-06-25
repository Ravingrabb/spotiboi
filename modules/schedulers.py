from redis import Redis
from rq_scheduler import Scheduler

scheduler_h = Scheduler(connection=Redis(), queue_name="history_update")
scheduler_f = Scheduler(connection=Redis(), queue_name="favorite_update")
scheduler_s = Scheduler(connection=Redis(), queue_name="smart_update")
scheduler_a = Scheduler(connection=Redis(), queue_name="auto_clean")
