from datetime import datetime, timedelta
import logging
import pandas as pd
from time import sleep

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, ForeignKey, PickleType,
    Index, Float)
from sqlalchemy import func, or_, and_
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import reconstructor, relationship, synonym

from celery_worker import execute_command

from dashboard.db import get_redis_conn, get_sql_session, engine
from dashboard.utils import convert_to_utc

Base = declarative_base()
ID_LEN = 250
logger = logging.getLogger(__name__)


############
# db models
############

class TaskInstance(Base):
    __tablename__ = 'task_instance'
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False)
    execution_date = Column(DateTime, nullable=False)
    operator = Column(String(1000))
    command = Column(String(1000), nullable=False)
    state = Column(String(20))
    task_id = Column(String(ID_LEN))

    def __init__(self, job):
        self.job_id = job.id 
        self.execution_date = job.next_run_ts 
        self.operator = job.operator 
        self.command = job.command 
        self.state = 'PENDING'
        self.task_id = None

    def __repr__(self):
        return "<TaskInstance(job_id={}, command={}, exe_ts={}, status={})>".format(
                self.job_id, self.command, self.execute_ts, self.status)


class Job(Base):
    __tablename__ = "job"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100))
    timezone = Column(String(20))
    update_time = Column(DateTime)
    start_dt = Column(DateTime)
    end_dt = Column(DateTime, nullable=True)
    active = Column(Boolean)
    schedule_interval = Column(Integer)
    operator = Column(String) # bash, python, sql, etc
    command = Column(String)
    next_run_ts = Column(DateTime)

    def __init__(self, name, timezone, start_dt=None, end_dt=None, 
                active=True, schedule_interval=60*60*24, 
                operator='bash', command='sleep 10', 
                next_run_ts=None, **kwargs):
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
            self.end_dt = convert_to_utc(end_dt, timezone)

        self.active = active
        self.schedule_interval = int(schedule_interval)
        self.operator = operator
        self.command = command 
        if start_dt is not None:
            self.next_run_ts = self.start_dt
        else:
            self.next_run_ts = next_run_ts or datetime.utcnow()

    def schedule_task(self, session):
        if datetime.utcnow() < self.next_run_ts:
            return None
        task = TaskInstance(job=self)
        logger.info("schedule task for job {} at utc {}".format(self.name, self.next_run_ts))
        celery_task = execute_command.apply_async(args=[task.command])
        task.task_id = celery_task.id 
        session.add(task)

        self.next_run_ts += timedelta(seconds=self.schedule_interval)
        session.commit()
        return celery_task.id

    def __repr__(self):
        return "<Job(name={}, active={}, next_run={})>".format(
            self.name, self.active, self.next_run_ts)

Base.metadata.create_all(engine)


###############
# Scheduler 
###############

class ScheduleManager(object):
    name = "scheduler_manager"
    redis_conn = get_redis_conn()

    @classmethod
    def exists(cls):
        if cls.redis_conn.exists(cls.name):
            logger.warning("""A ScheduleManager instance exists, 
                will not start a new one.""") 
            return True 
        return False

    def __init__(self, session=None):
        if self.exists():
            import sys
            sys.exit()

        self.session = session or get_sql_session()
        self.redis_conn.set(self.name, datetime.now(), ex=20)
        # try to recover active tasks:
        self.active_tasks = self.session.query(
                    TaskInstance.task_id, TaskInstance.state).filter(
                    TaskInstance.state.in_(("PENDING", "PROGRESS"))).all()
        logger.info("Start manager, all active tasks: {}".format(
                self.active_tasks))


    def start(self, poll_interval=30):
        while True:
            logger.info("Scheduler working...")
            self.check_schedule_time()
            self.check_tasks_status()
            self.send_heartbeat()
            logger.info("Waiting for next poll...")
            sleep(poll_interval)

    def send_heartbeat(self):
        # TODO:
        # should design heartbeat functionality 
        # for failure recovery/alert
        self.redis_conn.set(self.name, datetime.now())


    def check_schedule_time(self):
        active_jobs = self.session.query(Job).filter(
            Job.active==True).with_for_update().all()
        logger.info("Find {} active jobs, try to schedule them".format(
                    len(active_jobs)))
        if active_jobs:
            for job in active_jobs:
                task_id = job.schedule_task(self.session)
                if task_id is not None:
                    self.active_tasks.append((task_id, 'PENDING'))

    def check_tasks_status(self):
        active_tasks = []

        for tid, state in self.active_tasks:
            celery_task = execute_command.AsyncResult(tid)
            if celery_task.status != state:
                ti = self.session.query(TaskInstance).filter(
                    TaskInstance.task_id==tid).with_for_update().first()
                if ti:
                    ti.state = celery_task.status 
                else:
                    # should never happen
                    logger.warning("Task {} does not exists in db".format(tid))

            if celery_task.status in ('PENDING', 'PROGRESS'):
                active_tasks.append((tid, celery_task.status))

        self.active_tasks = active_tasks
        self.session.commit()



class RequestHandler:
    """ This is the handlers that takes requests from web/cli """
    @classmethod
    def add_job(cls, args, session=get_sql_session()):
        # create a job instance and add to redis 
        if isinstance(args, dict):
            # ImmutableMultiDict from flask web form 
            # convert to dict
            args_dict = {k.encode('ascii'): v.encode('ascii') for k, v in args.items()}
            # args_dict = {k: v for k, v in args.items()}
            job = Job(**args_dict)
        else:
            job = Job(**vars(args))
        logger.info("Add job {} into db".format(str(job)))
        ex_job = session.query(Job).filter_by(name=job.name).first()
        if ex_job:
            logger.warning("Job with name {} already exist, edit the job".format(
                        job.name))
            for k, v in vars(job).items():
                print(k,v)
                setattr(ex_job, k, v)
        else:
            session.add(job)
        session.commit()

    @classmethod
    def deactivate_job(cls, args, session=get_sql_session()):
        # set the job instance inactive
        # remove from jobs_bag
        job = session.query(Job).filter(
                Job.name==args.name).with_for_update().first()

        if job:
            if job.active:
                logger.debug("deactivate job: {}".format(str(job)))
                job.active = False
                session.commit()
            else:
                logger.debug("Job {} is already inactive".format(args.name))
        else:
            logger.warning("Job with name {} does not exist".format(args.name))

    @classmethod
    def clear_redis(cls):
        redis_conn = get_redis_conn()
        redis_conn.flushdb()

    @classmethod
    def clear_sql_db(cls):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    @classmethod 
    def info_all_jobs(cls, session=get_sql_session()):
        all_jobs = session.query(Job).all()
        job_activity = {"active": [],
            "inactive": []}
        for job in all_jobs:
            if job.active:
                job_activity["active"].append(job)
            else:
                job_activity["inactive"].append(job)
        return job_activity


    @classmethod
    def info_job(cls, job_name):
        redis_conn = get_redis_conn()
        job_info = redis_conn.hgetall(
            Job.create_redis_key(name=job_name))
        return job_info

    @classmethod
    def info_task_by_job(cls, job_name):
        redis_conn = get_redis_conn()
        all_tasks = redis_conn.keys(Task.root + job_name + "*")
        # categorize by status
        task_status = {"pending": [],
                "progress": [],
                "fail": [],
                "success": []}
        for task_key in all_tasks:
            status = redis_conn.hget(task_key, 'status')
            if status == 'PENDING':
                task_status['pending'].append(task_key.strip(Task.root))
            elif status == "PROGRESS":
                task_status['progress'].append(task_key.strip(Task.root))
            elif status == "SUCCESS":
                task_status['success'].append(task_key.strip(Task.root))
            else:
                task_status['fail'].append(task_key.strip(Task.root))
        return task_status

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



# class Monitor(object):
    # this is to check scheduler heartbeat
    # should be able to give alert if scheduler
    # stops sending heartbeat

# class Worker(RedisObject): pass
