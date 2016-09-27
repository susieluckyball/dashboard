redis-server # should be able to customize port and db
celery worker -A celery_hook --log-level=debug 

# for debug
# redis-cli 

python cli.py start # start schedule manager
