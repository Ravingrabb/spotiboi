#!flask/bin/python
from app import app, logging, gunicorn_logger

if __name__ == "__main__":
    gunicorn_logger.info('sosi pizdu')
    logging.info('sosi pizdu')
    app.run()