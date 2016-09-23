from redis import StrictRedis

_redis_conn = StrictRedis(host='localhost', port=6379, db=0)

jobs_group = "/jobs"
tasks_group = "/tasks"


def get_redis_conn():
	return _redis_conn

