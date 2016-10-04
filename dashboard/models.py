from collections import defaultdict
from datetime import datetime, timedelta
import functools
import logging
import pandas as pd
from time import sleep

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, ForeignKey, PickleType,
    Index, Float)
from sqlalchemy import func, or_, and_
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import reconstructor, relationship, synonym

from dashboard.celery_worker import execute_command

from dashboard.db import get_redis_conn, get_sql_session, engine
from dashboard.utils import convert_to_utc

Base = declarative_base()
ID_LEN = 250
logger = logging.getLogger(__name__)


############
# db models
############

@functools.total_ordering
class TaskInstance(Base):
    __tablename__ = 'task_instance'
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False)
    job_name = Column(String(100), nullable=False)
    execution_date = Column(DateTime, nullable=False)
    operator = Column(String(1000))
    command = Column(String(1000), nullable=False)
    state = Column(String(20))
    task_id = Column(String(ID_LEN))
    result = Column(String(1000))

    def __init__(self, job):
        self.job_id = job.id 
        self.job_name = job.name
        self.execution_date = job.next_run_ts 
        self.operator = job.operator 
        self.command = job.command 
        self.state = 'PENDING'
        self.task_id = None
        self.result = None

    def __eq__(self, other):
        return ((self.job_name, self.execution_date) == 
                (other.job_name, other.execution_date))

    def __lt__(self, other):
        if self.job_name < other.job_name:
            return True 
        if self.job_name > other.job_name:
            return False
        return self.execution_date > other.execution_date

    def __repr__(self):
        return "<TaskInstance(job_id={}, command={}, exe_ts={}, status={})>".format(
                self.job_id, self.command, self.execute_ts, self.status)

@functools.total_ordering
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
                active=True, schedule_interval=None, 
                operator='bash', command='sleep 10', 
                next_run_ts=None, **kwargs):
        self.name = name
        self.timezone = timezone
        self.update_time = datetime.utcnow() 

        if start_dt is None or start_dt == '':
            self.start_dt = datetime.utcnow()
        else:
            self.start_dt = convert_to_utc(start_dt, timezone)

        if end_dt is None or end_dt == '':
            self.end_dt = None 
        else:
            self.end_dt = convert_to_utc(end_dt, timezone)

        self.active = active
        if schedule_interval is None or schedule_interval == "":
            self.schedule_interval = 60 * 60 * 24 # default daily job
        else:
            self.schedule_interval = int(schedule_interval)
        self.operator = operator
        self.command = command
        if start_dt is not None:
            self.next_run_ts = self.start_dt
        else:
            self.next_run_ts = next_run_ts or datetime.utcnow()

    def schedule_task(self, session, force_run=False):
        if force_run:
            orig_next_run = self.next_run_ts
            self.next_run_ts = datetime.utcnow()
        if datetime.utcnow() < self.next_run_ts:
            return None
        task = TaskInstance(job=self)
        print("=========")
        print(task.command)
        import shlex
        print(shlex.split(task.command, posix=False))
        celery_task = execute_command.apply_async(args=[task.command])
        task.task_id = celery_task.id 
        session.add(task)
        if not force_run:
            logger.info("schedule task for job {} at utc {}".format(self.name, self.next_run_ts))
            self.next_run_ts += timedelta(seconds=self.schedule_interval)
        else:
            logger.info("schedule task for job {} at utc {}".format(self.name, datetime.utcnow()))
            self.next_run_ts = orig_next_run
        session.commit()
        return celery_task.id

    def initialize_shortcommand(self):
        max_size = 57
        if len(self.command) > max_size:
            self.short_command = self.command[:max_size] + "..."
        else:
            self.short_command = self.command

    def __eq__(self, other):
        return self.name == other.name 

    def __lt__(self, other):
        return self.name < other.name

    def __repr__(self):
        return "<Job(name={}, active={}, next_run={})>".format(
            self.name, self.active, self.next_run_ts)


@functools.total_ordering
class Tag(Base):
    __tablename__ = "tag"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100))
    name = Column(String(100))

    def __init__(self, tag_name, job_name):
        self.name = tag_name
        self.job_name = job_name

    def __eq__(self, other):
        return ((self.name, self.job_name) == 
            (other.name, self.job_name))

    def __lt__(self, other):
        return ((self.name, self.job_name) < 
                (self.name, self.job_name))

    def __repr__(self):
        return "<Tag(job={}, tag={})>".format(self.job_name, self.name)



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
        logger.info("Start manager")


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
                    logger.info("schedule task {} for job {}".format(task_id, job.name))

    def check_tasks_status(self):
        # try to recover active tasks:
        active_tasks = self.session.query(TaskInstance).filter(
                    TaskInstance.state.in_(("PENDING", "STARTED"))
                    ).with_for_update().all()
        if len(active_tasks) == 0:
            logger.info("No active tasks, return")
            return 

        for task in active_tasks:
            celery_task = execute_command.AsyncResult(task.task_id)
            if celery_task.status == task.state:
                continue 
            task.state = celery_task.status
            logger.info("Job {} exec time {} task changes to state {}".format(
                    task.job_name, task.execution_date, task.state))
            if celery_task.ready():
                if isinstance(celery_task.result, Exception):
                    task.result = str(celery_task.result)
                else:
                    task.result = celery_task.result
        self.session.commit()



class RequestHandler:
    """ This is the handlers that takes requests from web/cli """

    @classmethod
    def clear_redis(cls):
        """clear celery info"""
        redis_conn = get_redis_conn()
        redis_conn.flushdb()

    @classmethod
    def clear_sql_db(cls):
        """clear all jobs/tasks/tags"""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    @classmethod
    def get_tags(cls, session=get_sql_session()):
        """get all distinct tags"""
        return session.query(Tag.name).distinct().order_by(Tag.name).all()

    @classmethod
    def get_jobs(cls, session=get_sql_session(), only_active=False):
        """get ALL jobs, can filter for only active jobs"""
        q = session.query(Job)
        if only_active:
            q = q.filter(Job.active==True)
        return q.all()

    @classmethod
    def info_job(cls, job_name, session=get_sql_session()):
        """ given a job_name, get all tags and its tasks """
        job = session.query(Job).filter(Job.name==job_name).first()
        if job:
            tags = session.query(Tag.name).filter(
                    Tag.job_name==job_name).all()
            tags = [t[0] for t in tags]
            tasks = session.query(TaskInstance).filter(
                    TaskInstance.job_id==job.id).all()
            tasks = sorted(tasks)
            return job, tags, tasks
        return None, None, None

    @classmethod
    def get_jobs_by_tag(cls, session=get_sql_session(), only_active=False, tag_name=None):
        """if given tag_name, will get all jobs that have this tag,
        else return dictionary of tags and their list of jobs"""
        tj = session.query(Tag, Job).filter(Job.name==Tag.job_name)
        if only_active:
            tj = tj.filter(Job.active==True)
        if tag_name is not None:
            tj = tj.filter(Tag.name==tag_name).all()
            # return a list of all jobs that has the tag 
            # of the input tag_name
            return [item[1] for item in tj]

        tj = tj.all()
        # return a dictionary
        # tag -> [jobs]
        tags_dict = defaultdict(list)
        for tag, job in tj:
            tags_dict[tag.name].append(job)
        return tags_dict

    @classmethod
    def info_tasks(cls, session=get_sql_session(), 
                    only_running=False, job_name=None):
        """ get all running tasks """
        q = session.query(TaskInstance)
        if only_running:
            q = q.filter(TaskInstance.state.in_(('STARTED', 'PENDING')))
        if job_name is not None:
            q = q.filter(TaskInstance.job_name==job_name)
        tasks = sorted(q.all())
        return tasks

    @classmethod
    def add_job(cls, job_args, tags, session=get_sql_session()):
        """ add a new job """
        # check existing
        ex_job = session.query(Job).filter(
                Job.name==job_args['name']).first()
        if ex_job:
            return False

        # create a job instance
        job = Job(**job_args)
        session.add(job)
        tag_instances = [Tag(t, job_args["name"]) for t in tags]
        for ti in tag_instances:
            session.add(ti)
        session.commit()
        return True


    @classmethod
    def edit_job(cls, job_args, tags, session=get_sql_session()):
        """ Change the existing job, remove outdated tags
        and add newly added tags to db.
        """
        job = session.query(Job).filter(
                Job.name==job_args['name']).with_for_update().first() 
        ex_tags = session.query(Tag).filter(
                Tag.job_name==job_args['name']).with_for_update().all()
    
        tmp = Job(**job_args)
        for k, v in vars(tmp).items():
            if k.startswith("_"):
                continue 
            setattr(job, k, v)
        del tmp

        all_tags = set(tags)
        for t in ex_tags:
            if t.name in all_tags:
                all_tags.remove(t.name)
            else:
                session.delete(t)
                logger.debug("delete tag {} for job {}".format(t.name, job_args['name']))
        for name in all_tags:
            session.add(Tag(name, job_args['name']))
            logger.debug("add tag {} for job {}".format(name, job_args['name']))

        session.commit()

    @classmethod
    def change_job_status(cls, job_name, session=get_sql_session(), deactivate=True):
        """ set the job instance inactive """
        job = session.query(Job).filter(
                Job.name==job_name).with_for_update().first()

        if job:
            if deactivate:
                if job.active:
                    logger.debug("deactivate job: {}".format(str(job)))
                    job.active = False
                    session.commit()
                    return True
                else:
                    msg = "Job {} is already inactive".format(job_name)
                    logger.debug(msg)
            else:
                if not job.active:
                    logger.debug("activate job: {}".format(str(job)))
                    job.active = True
                    session.commit()
                    return True 
                else:
                    msg = "Job {} is already active".format(job_name)
                    logger.debug(msg)
        else:
            msg = "Job with name {} does not exist".format(job_name)
            logger.warning()
        return msg

    @classmethod
    def check_task_stdout(cls, task_id, session=get_sql_session()):
        # read-only
        task = session.query(TaskInstance).filter(TaskInstance.id==task_id).first()
        return task


    @classmethod
    def remove_job(cls, job_name, session=get_sql_session()):
        """ remove from job table """
        job = session.query(Job).filter(Job.name==job_name
                    ).with_for_update().first()
        session.delete(job)
        session.commit()

    @classmethod
    def force_schedule_for_job(cls, job_name, session=get_sql_session()):
        job = session.query(Job).filter(Job.name==job_name
                ).with_for_update().first()
        if job:
            task_id = job.schedule_task(session, force_run=True)
            return task_id 
        return None

    @classmethod
    def get_task_status(cls):
        raise NotImplementedError





# class Monitor(object):
    # this is to check scheduler heartbeat
    # should be able to give alert if scheduler
    # stops sending heartbeat

# class Worker(RedisObject): pass
