from celery import Celery
from celery import states as celery_states
import subprocess

from config import Config

class CeleryConfig(object):
    CELERY_ACCEPT_CONTENT = ['json', 'pickle']
    CELERYD_PREFETCH_MULTIPLIER = 1
    CELERY_ACKS_LATE = True

    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

    # CELERY_DEFAULT_QUEUE = DEFAULT_QUEUE
    # CELERY_DEFAULT_EXCHANGE = DEFAULT_QUEUE


worker = Celery('dashboard', broker=CeleryConfig.CELERY_BROKER_URL)
worker.conf.update(CELERY_RESULT_BACKEND='redis')

@worker.task
def execute_command(command):
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError('Celery command failed')
