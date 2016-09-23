from datetime import datetime, timedelta
from time import sleep

class RedisObject:
    root = ""

    @property
    def redis_key(self):
        return self._redis_key

    @redis_key.getter
    def redis_key(self, val):
        return self._redis_key

    @classmethod
    def create_redis_key(cls, **kwargs):
        return cls.root.format(**locals())

    def serialize(self, redis_conn):
        if redis_conn.hexists(self._redis_key):
            print("Warning: {} with redis key {} already exists".format(
                    self.__class__.__name__, self._redis_key))
        tx = redis_conn.pipeline()
        for k, v in vars(self):
            tx.hset(self._redis_key, k, v)  
        tx.execute()

    @classmethod
    def deserialize(cls, kv_pairs):
        return cls.__init__(**kv_pairs)


class Task(RedisObject):
    root = "/tasks/{job}_{ts}"

    def __init__(self, job_name, timestamp):
        self.job = job_name
        self.timestamp = timestamp
        self._redis_key = self.root.format(job=job_name, ts=timestamp)

    def enqueue(self):
        # put to celery queue 
        pass


class Job(RedisObject):
    root = "/jobs/{name}"
    def __init__(self, name, timezone, update_time, 
                start_dt=None, end_dt=None,
                active=True, schedule_interval=timedelta(days=1),
                operator="bash", cmd="", tags=None):
        self.name = name 
        self.timezone = timezone 
        self.update_time = update_time
        # NOTE
        # Should convert start_dt and end_dt to utc
        # using timezone info
        self.start_dt = start_dt or datetime.utcnow()
        self.end_dt = end_dt 
        self.active = active 
        self.schedule_interval = schedule_interval
        self.operator = operator 
        self.cmd = cmd
        self.tags = tags
        self._redis_key = self.create_redis_key()

    def is_active(self):
        return self.active 

    def schedule_task(self, ts):
        task = Task(job_name=self.name, timestamp=ts)


class JobsBag:
    """ JobsBag is a hash, keys are job_name, 
    values are next scheduled time """

    next_run_key = "/jobs_bag/next_run_ts"
    def __init__(self):
        pass

    def check_schedule_time(self, redis_conn, schedule_manager):
        active_jobs = redis_conn.hgetall(self.next_run_key)
        tx = redis_conn.pipeline()
        for job_name, next_run_ts in active_jobs:
            if datetime.now() >= next_run_ts:
                new_next_run_ts = schedule_manager.schedule(job_name, next_run_ts)
                tx.hset(self.next_run_key, job_name, new_next_run_ts)
        tx.execute()


class RequestHandler:
    """ This is the handlers that takes requests from web """
    def add_job(self):
        # create a job instance and add to redis 
        # update jobs_bag
        raise NotImplementedError

    def set_job_inactive(self):
        # set the job instance inactive
        # remove from jobs_bag
        raise NotImplementedError

    def add_tag_to_job(self):
        raise NotImplementedError

    def remove_job(self):
        # remove from jobs 
        # potentially remove from jobs_bag
        raise NotImplementedError

    def force_schedule_for_job(self):
        # update jobs_bag for the job
        raise NotImplementedError

    def get_task_status(self):
        raise NotImplementedError

    def show_job_info(self):
        raise NotImplementedError

    # def get_task_log(self):
    #     raise NotImplementedError


class ScheduleManager:
    def __init__(self, jobs_bag, redis_conn):
        self.jobs_bag = jobs_bag 
        self.redis_conn = redis_conn

    def start(self, poll_interval=30):
        while True:
            self.jobs_bag.check_schedule_time(redis_conn, self)
            sleep(poll_interval)

    def schedule_task(self, job_name, timestamp):
        schedule_interval = self.redis_conn.hget(
                Job.create_redis_key(name=job_name), "schedule_interval")
        task = Task(job_name, timestamp)
        
        # write a record to redis
        task.serialize()        
        # put celery queue
        task.enqueue()
        # return next scheduled time
        return timestamp + timedelta(schedule_interval)
