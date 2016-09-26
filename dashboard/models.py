from datetime import datetime, timedelta
import pandas as pd
from time import sleep

from celery_hook import execute_command
from redis_api import get_redis_conn
from utils import convert_to_utc

class RedisObject:
    root = ""

    @property
    def redis_key(self):
        return self._redis_key

    @redis_key.getter
    def redis_key(self):
        return self._redis_key

    @classmethod
    def create_redis_key(cls, **kwargs):
        return cls.root.format(**kwargs)

    def serialize(self, redis_conn):
        print("serialize {} for {}".format(self.__class__.__name__, self.redis_key))
        if redis_conn.exists(self.redis_key):
            print("Warning: {} with redis key {} already exists".format(
                    self.__class__.__name__, self._redis_key))
        tx = redis_conn.pipeline()
        for k, v in vars(self).items():
            tx.hset(self._redis_key, k, v)  
        tx.execute()

    @classmethod
    def deserialize(cls, redis_conn, **kwargs):
        key = cls.create_redis_key(**kwargs)
        print("deserialize {} for {}".format(cls.__name__, key))
        obj_info = redis_conn.hgetall(key)
        return cls(**decoded_obj_info)

    def __repr__(self):
        return "{}<{}>".format(self.__class__.__name__,
                    self.redis_key)


class Task(RedisObject):
    root = "/tasks/{job}/{ts}"

    def __init__(self, job_name, timestamp, command):
        self.job = job_name
        self.timestamp = timestamp
        self._redis_key = self.root.format(job=job_name, ts=timestamp.isoformat())
        self.command = command

        self.status = None
        self.task_id = None



class Job(RedisObject):
    root = "/jobs/{name}"
    def __init__(self, name, timezone, start_dt=None, end_dt=None,
                active=True, schedule_interval=timedelta(days=1),
                operator="bash", command="", tags=None, **kwargs):
        self.name = name 
        self.timezone = timezone 
        self.update_time = datetime.utcnow()
        if start_dt is None:
            self.start_dt = datetime.utcnow()
        else:
            self.start_dt = convert_to_utc(start_dt, timezone)
        if end_dt is None:
            self.end_dt = None 
        else:
            self.end_dt = convert_to_utc(start_dt, timezone)
        if isinstance(active, str):
            self.active = True if active == 'True' else False 
        else:
            self.active = active
        if isinstance(schedule_interval, timedelta):
            self.schedule_interval = schedule_interval
        else:
            self.schedule_interval = timedelta(seconds=int(schedule_interval))
        self.operator = operator 
        self.command = command
        self.tags = tags
        self._redis_key = self.create_redis_key(name=name)

    def serialize(self, redis_conn):
        super().serialize(redis_conn)
        # convert scheduled interval
        redis_conn.hset(self.redis_key, 'schedule_interval', 
                    int(self.schedule_interval.total_seconds()))

    def is_active(self):
        return self.active 



class RequestHandler:
    """ This is the handlers that takes requests from web/cli """
    @classmethod
    def add_job(cls, args):
        # create a job instance and add to redis 
        
        job = Job(**vars(args))
        redis_conn = get_redis_conn()
        job.serialize(redis_conn)

        # update jobs_bag
        redis_conn.hset(ScheduleManager.next_run_key, job.name, job.start_dt)

    @classmethod
    def deactivate_job(cls, args):
        # set the job instance inactive
        # remove from jobs_bag
        redis_conn = get_redis_conn()
        job = Job.deserialize(redis_conn, name=args.name)
        print(job)
        for k in vars(job):
            if not k.startswith("__"):
                print(k, getattr(job, k), type(getattr(job, k)))
        if job.active:
            job.active = False 
        redis_conn.hset(job.redis_key, 'active', False)
        redis_conn.hdel(JobsBag.next_run_key, job.name)

    @classmethod
    def clear_db(cls, args):
        redis_conn = get_redis_conn()
        confirm = input("Flush db will clear all existing data [Y/N]: ")
        if confirm.upper().startswith('Y'):
            redis_conn.flushdb()

    @classmethod
    def add_tag_to_job(cls, args):
        raise NotImplementedError

    @classmethod
    def remove_job(cls, args):
        # remove from jobs 
        # potentially remove from jobs_bag
        raise NotImplementedError

    @classmethod
    def force_schedule_for_job(cls):
        # update jobs_bag for the job
        raise NotImplementedError

    @classmethod
    def get_task_status(cls):
        raise NotImplementedError

    @classmethod
    def show_job_info(cls):
        raise NotImplementedError

    # def get_task_log(self):
    #     raise NotImplementedError


class ScheduleManager(object):
    name = "scheduler_manager"
    next_run_key = "/jobs_bag/next_run_ts"
    active_tasks_key = "/tasks_bag/active"
    redis_conn = get_redis_conn()

    @classmethod
    def exists(cls):
        if cls.redis_conn.exists(cls.name):
            print("""A ScheduleManager instance exists, 
                will not start a new one.""") 
            return True 
        return False


    def __init__(self):
        if not self.exists():
            self.redis_conn.set(self.name, datetime.now(), ex=20)

    def start(self, poll_interval=30):
        while True:
            print("Scheduler working...")
            self.check_schedule_time()
            self.check_tasks_status()
            self.send_heartbeat()
            print("Waiting for next poll...")
            sleep(poll_interval)

    def send_heartbeat(self):
        self.redis_conn.set(self.name, datetime.now())


    def check_schedule_time(self):
        active_jobs = self.redis_conn.hgetall(self.next_run_key)
        print("jobs: ",active_jobs)
        tx = self.redis_conn.pipeline()
        for job_name, next_run in active_jobs.items():
            next_run_ts = pd.to_datetime(next_run)
            if datetime.utcnow() >= pd.to_datetime(next_run_ts):
                new_next_run_ts = self.schedule_task(job_name, next_run_ts)
                tx.hset(self.next_run_key, job_name, new_next_run_ts)
        tx.execute()

    def check_tasks_status(self):
        active_task_names = self.redis_conn.lrange(self.active_tasks_key, 0, -1)
        print("tasks: ", active_task_names)
        finished_tasks = []
        for name in active_task_names:
            task_id = self.redis_conn.hget(name, 'task_id')
            celery_task = execute_command.AsyncResult(task_id)
            self.redis_conn.hset(name, 'status', celery_task.status)
            if celery_task.status not in ("PENDING", "PROGRESS"):
                finished_tasks.append(name)
        if len(finished_tasks):
            tx = self.redis_conn.pipeline()
            for item in finished_tasks:
                tx.lrem(name=self.active_tasks_key, value=item, count=1)
            tx.execute()

    def schedule_task(self, job_name, timestamp):
        job_key = Job.create_redis_key(name=job_name)
        schedule_interval = self.redis_conn.hget(job_key,
                 "schedule_interval")
     
        command = self.redis_conn.hget(job_key, 'command')
        task = Task(job_name, timestamp, command)
        
        # put celery queue
        print("schedule task for job {}".format(job_name))
        celery_task = execute_command.apply_async(args=[task.command])
        task.status = 'PENDING'
        task.task_id = celery_task.id

        # write a record to redis
        task.serialize(self.redis_conn)  
        self.redis_conn.rpush(self.active_tasks_key, task.redis_key)      

        # return next scheduled time
        return timestamp + timedelta(seconds=int(schedule_interval))


# class Worker(RedisObject): pass
