import time
from rq import Queue
from redis import Redis
from tasks import test_shit

# задаём соединение с Redis по умолчанию
queue = Queue(connection=Redis())

# кладём выполнение нашей задачи в очередь
job = queue.enqueue(test_shit)
print(job.result)   # функция возвратит None, так как задача скорее всего не будет выполнена к этому момент
# подождём 4 секунды
time.sleep(4)
print(job.result)   # => результат выполнения функции (кол-во слов)