import traceback
import logging.handlers
from .database import app

# TODO изменить путь логов
logging.basicConfig(filename='logs.log', level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
handler = logging.handlers.RotatingFileHandler(
    'logs.log',
    maxBytes=1024 * 1024)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('werkzeug').addHandler(handler)
logging.getLogger('rq.worker').setLevel(logging.ERROR)
logging.getLogger('rq.worker').addHandler(handler)

app.logger.setLevel(logging.ERROR)
#app.logger.addHandler(handler)

def log_with_traceback(message):
    app.logger.error(message)
    app.logger.error(traceback.format_exc())
