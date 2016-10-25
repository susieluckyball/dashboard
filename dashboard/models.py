from collections import defaultdict
from datetime import datetime, timedelta, time
import functools
import logging
import pandas as pd 
from time import sleep

from sqlalchemy import (
        Column, Integer, String, DateTime, Text, Boolean, Float)
from sqlalchemy import func, or_, and_
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import reconstructor, relationship, synonym

from werkzeug.security import generate_password_hash, check_password_hash

from dashboard.celery_worker import execute_command, execute_sql
from dashboard.utils.date import (convert_to_utc, 
        get_cron_schedule_interval, get_next_run_ts)
from dashboard.utils.db import (engine, get_redis_conn, 
        provide_session, get_sql_session)
from dashboard.utils.emails import send_email, valid_email


Base = declarative_base()
ID_LEN = 250
logger = logging.getLogger(__name__)


############
# db models
############

@functools.total_ordering
class TaskInstance(Base):
    __tablename__ = 'task_instances'
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False)
    job_name = Column(String(100), nullable=False)
    execution_date = Column(DateTime, nullable=False)
    operator = Column(String(1000))
    command = Column(String(1000), nullable=False)
    state = Column(String(20))
    task_id = Column(String(ID_LEN))
    result = Column(String(1000))

    def __init__(self, job, execution_date=None):
        self.job_id = job.id 
        self.job_name = job.name
        self.execution_date = execution_date or job.next_run_local_ts 
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
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), index=True)
    # owner = Column(String(50), nullable=True)    # this is only a placeholder for now
    timezone = Column(String(20))
    update_time = Column(DateTime)
    start_dt = Column(DateTime)   # local dt
    end_dt = Column(DateTime, nullable=True)   # local dt
    active = Column(Boolean)
    block_till = Column(DateTime, nullable=True)
    block_by = Column(String(50), nullable=True)
    block_msg = Column(String(200), nullable=True)
    schedule_interval = Column(String(20))
    reset_status_at = Column(DateTime)

    operator = Column(String(10)) # bash, python, sql, etc
    database = Column(String(20), nullable=True)
    command = Column(String)
    next_run_local_ts = Column(DateTime)    # local dt
    last_execution_ts = Column(DateTime, nullable=True)
    last_task_result = Column(String(1000))
    status = Column(Integer)

    status_enum = {'fail': 0,
                'success': 1,
                'unknown': 2}
    status_map = {0: 'fail',
                1: 'success',
                2: 'unknown'}

    def __init__(self, name, timezone, 
                start_dt, end_dt, 
                schedule_interval,
                weekday_to_run,
                schedule_interval_crontab, 
                reset_status_at,
                operator, database,
                command, active=True,
                block_till=None, block_by=None, **kwargs):
        self.name = name
        self.timezone = timezone
        self.update_time = datetime.utcnow()

        if start_dt is None or start_dt == '':
            self.start_dt = pd.to_datetime(datetime.utcnow()
                ).tz_localize('UTC').astimezone(timezone
                ).replace(tzinfo=None)
        else:
            self.start_dt = pd.to_datetime(start_dt)

        if end_dt is None or end_dt == '':
            self.end_dt = None 
        else:
            self.end_dt = pd.to_datetime(self.end_dt)

        self.active = active
        self.block_till = block_till
        self.block_by = block_by

        # figure out the schedule interval crontab...
        if len(schedule_interval_crontab):
            self.schedule_interval = schedule_interval_crontab
        else:
            self.schedule_interval = get_cron_schedule_interval(
                    schedule_interval, self.start_dt, weekday_to_run)

        self.reset_status_at = pd.to_datetime(reset_status_at)
        self.operator = operator
        self.database = database
        self.command = command

        self.next_run_local_ts = self.start_dt
        self.status = self.status_enum['unknown']

    def set_status(self, session, status='unknown'):
        self.status = self.status_enum.get(status, 
                        self.status_enum['unknown'])
        session.commit()

    def schedule_task(self, session, force_run=False):
        if force_run:
            # orig_next_run = self.next_run_local_ts
            utcnow = datetime.utcnow()
            current_run = pd.to_datetime(utcnow
                ).tz_localize('UTC').astimezone(self.timezone
                ).replace(tzinfo=None)
            task = TaskInstance(job=self, execution_date=current_run)
            logger.info("schedule task for job {} at utc {}".format(
                        self.name, utcnow))

        else:
            if datetime.utcnow() < convert_to_utc(
                    self.next_run_local_ts, self.timezone):
                return None
            task = TaskInstance(job=self)
        if task.operator == 'bash':
            celery_task = execute_command.apply_async(args=[task.command])
        elif task.operator == 'sql':
            # add sql query
            celery_task = execute_sql.apply_async(args=[task.command, self.database])
        task.task_id = celery_task.id 
        session.add(task)
        if not force_run:
            logger.info("schedule task for job {} at {} {}".format(
                        self.name, self.next_run_local_ts, self.timezone))
            self.next_run_local_ts = get_next_run_ts(self.schedule_interval, self.next_run_local_ts)

        session.commit()
        return celery_task.id

    def initialize_shortcommand(self, max_size=30):
        if len(self.command) > max_size:
            self.short_command = self.command[:max_size] + "..."
        else:
            self.short_command = self.command

    def initialize_short_result(self, max_size=30):
        self.short_result = self.last_task_result
        if self.last_task_result is not None:
            if len(self.last_task_result) > max_size:
                self.short_result = self.last_task_result[:max_size] + "..."

    def __eq__(self, other):
        return self.name == other.name 

    def __lt__(self, other):
        return self.name < other.name

    def __repr__(self):
        return "<Job(name={}, active={}, next_run={})>".format(
            self.name, self.active, self.next_run_local_ts)


@functools.total_ordering
class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100), index=True)
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


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer , primary_key=True, autoincrement=True)
    email = Column(String(50), unique=True, index=True)
    password_hash = Column(String(128))
    
    @property
    def password(self):
        raise AttributeError('password is not readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True 

    def is_anonymous(self):
        return False 

    def get_id(self):
        return unicode(self.id)

    @provide_session
    def is_subscribed_to(self, name, job=True, session=None):
        if job:
            res = session.query(JobAlert).filter(and_(
                JobAlert.job_name==name, 
                JobAlert.email==self.email)).first()
        else:
            res = session.query(TagAlert).filter(and_(
                TagAlert.tag_name==name, 
                TagAlert.email==self.email)).first()
        if res:
            return True
        return False        

    def __repr__(self):
        return "<User {}>".format(self.email)

# TODO: ordering...
class JobAlert(Base):
    __tablename__ = "job_alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(100))
    email = Column(String(50))
    # TODO
    # add alert level
    # default is alert when failure


class TagAlert(Base):
    __tablename__ = 'tag_alerts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_name = Column(String(100))
    email = Column(String(50))


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

    def __init__(self):
        if self.exists():
            import sys
            sys.exit()
        self.redis_conn.set(self.name, datetime.now(), ex=20)
        logger.info("Start manager")


    def start(self, poll_interval=20):
        while True:
            logger.info("Scheduler working...")
            start = datetime.now()
            with get_sql_session() as session:
                # schedule tasks
                self.schedule_and_update_jobs(session)
                # update running/pending tasks state
                self.check_tasks_state(session)
                # check 
            self.send_heartbeat()
            logger.info("Waiting for next poll...")
            sleep_for = max(poll_interval - 
                    (datetime.now() - start).total_seconds(),
                    0)
            sleep(sleep_for)

    def send_heartbeat(self):
        # TODO:
        # should design heartbeat functionality 
        # for failure recovery/alert
        self.redis_conn.set(self.name, datetime.now())


    @provide_session
    def schedule_and_update_jobs(self, session=None):
        """ check all active jobs and schedule tasks when it's time """
        now = datetime.now()
        blocked_jobs = session.query(Job).filter(
                        Job.active==False).filter(
                        Job.block_till != None).with_for_update().all()
        if blocked_jobs:
            for job in blocked_jobs:
                if now > job.block_till:
                    job.activate = True 
                    logger.info("Job {} is unblocked".format(job.name))

        active_jobs = session.query(Job).filter(
            Job.active==True).with_for_update().all()  
        logger.info("Find {} active jobs, try to schedule them".format(
                    len(active_jobs)))      
        if active_jobs:
            for job in active_jobs:
                # check if the job should be deactivate 
                if job.end_dt and now > job.end_dt:
                    job.active = False
                    continue
                reset_time = datetime.combine(datetime.today(),
                        job.reset_status_at.time())
                # check if the job state should be reset
                if (now >= reset_time and job.last_task_result and 
                        job.last_execution_ts < reset_time):
                    job.set_status(session, 'unknown')

                # schedule tasks for each active job
                task_id = job.schedule_task(session)
                if task_id is not None:
                    logger.info("schedule task {} for job {}".format(task_id, job.name))
        session.commit()

    @provide_session
    def check_tasks_state(self, session=None):
        """ check celery jobs and change task status """
        # try to recover active tasks
        active_tasks = session.query(TaskInstance).filter(
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
                self._update_job_last_state(task, session)

        session.commit()

    def _update_job_last_state(self, task, session):
        job = session.query(Job).filter(
                        Job.name==task.job_name
                        ).with_for_update().first()
        if not job:
            logger.error("Cannot find job name {}".format(task.job_name))
            return 
        # CAVEAT
        # This is only for dashboard
        # if sysout starts with 1, data check passed
        job.last_execution_ts = task.execution_date
        job.last_task_result = task.result
        if (not isinstance(job.last_task_result, str) or 
                not job.last_task_result.startswith("1")):
            self._send_alert(job, session)
            job.set_status(session, 'failure')
        else:
            job.set_status(session, 'success')
        session.commit()

    def _send_alert(self, job, session):
        job_followers = [f[0] for f in session.query(JobAlert.email).filter(
                JobAlert.job_name==job.name).all()]
        t = session.query(Tag.name.label("tag_name")).filter(
                Tag.job_name==job.name)

        tag_followers = [f[0] for f in session.query(TagAlert.email).filter(
                TagAlert.tag_name.in_(t)).all()]
        recipients = list(set(job_followers).union(set(tag_followers)))
        if len(recipients):
            subject = "Dashboard - Job Failure Alert"
            body = "Job {} (command {}) status: \nfailed with sysout {}".format(
                    job.name, job.command, job.last_task_result)
            send_email(subject=subject, to_=recipients, body=body)


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
    @provide_session
    def get_tags(cls, session=None):
        """get all distinct tags"""
        return session.query(Tag.name).distinct().order_by(Tag.name).all()

    @classmethod
    @provide_session    
    def get_user(cls, email, session=None):
        return session.query(User).filter(User.email==email).first()

    @classmethod
    @provide_session    
    def get_user_by_id(cls, id, session=None):
        return session.query(User).filter(User.id==id).first()

    @classmethod
    @provide_session
    def register(cls, email, password, session=None):
        user = User(email=email, password=password)
        session.add(user)
        session.commit()
        return 

    @classmethod
    @provide_session
    def get_jobs(cls, only_active=False, session=None):
        """get ALL jobs, can filter for only active jobs"""
        q = session.query(Job)
        if only_active:
            q = q.filter(Job.active==True)
        return q.all()

    @classmethod
    @provide_session
    def info_job(cls, job_name, max_task_num=20, session=None):
        """ given a job_name, get all tags and its tasks """
        job = session.query(Job).filter(Job.name==job_name).first()
        if job:
            tags = session.query(Tag.name).filter(
                    Tag.job_name==job_name).all()
            tags = [t[0] for t in tags]
            tasks = session.query(TaskInstance).filter(
                    TaskInstance.job_id==job.id).order_by(
                    TaskInstance.execution_date.desc()).limit(
                    max_task_num).all()
            tasks = sorted(tasks)
            alerts = session.query(JobAlert.email).filter(
                    JobAlert.job_name==job_name).order_by(
                    JobAlert.email).all()
            alerts = [a[0] for a in alerts]
            return job, tags, tasks, alerts
        return None, None, None

    @classmethod
    @provide_session
    def get_jobs_by_tag(cls, only_active=False, tag_name=None, session=None):
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
    @provide_session
    def info_tasks(cls, only_running=False, job_name=None, session=None):
        """ get all running tasks """
        q = session.query(TaskInstance)
        if only_running:
            q = q.filter(TaskInstance.state.in_(('STARTED', 'PENDING')))
        if job_name is not None:
            q = q.filter(TaskInstance.job_name==job_name)
        tasks = sorted(q.all())
        return tasks

    @classmethod
    @provide_session    
    def clear_tasks_history(cls, job_name, session=None):
        tasks = session.query(TaskInstance).filter(
                TaskInstance.job_name==job_name).with_for_update(
                ).all()
        for t in tasks:
            session.delete(t)
        session.commit()
        return


    @classmethod
    @provide_session
    def add_job(cls, job_args, tags, subscribers, session=None):
        """ add a new job """
        # check existing
        ex_job = session.query(Job).filter(
                Job.name==job_args['name']).first()
        if ex_job:
            return False

        # create a job instance
        job = Job(**job_args)
        session.add(job)
        # add tag
        tag_instances = [Tag(t, job_args["name"]) for t in tags]
        # add alerts 
        # TODO:
        # we did not check whether the email is a valid user here!!
        job_alerts = [JobAlert(job_name=job_args["name"], email=s) for s in subscribers]
        for ti in tag_instances:
            session.add(ti)
        for ja in job_alerts:
            session.add(ja)
        session.commit()
        return True


    @classmethod
    @provide_session
    def edit_job(cls, job_args, tags, subscribers, session=None):
        """ Change the existing job, remove outdated tags
        and add newly added tags to db.
        """
        job = session.query(Job).filter(
                Job.name==job_args['name']).with_for_update().first() 
        ex_tags = session.query(Tag).filter(
                Tag.job_name==job_args['name']).with_for_update().all()
        ex_subs = session.query(JobAlert).filter(
                JobAlert.job_name==job_args['name']).with_for_update().all()
        #
        # This (I think) is poorly designed...
        # 
        job_args['active'] = job.active
        job_args['block_till'] = job.block_till
        job_args['block_by'] = job.block_by
        tmp = Job(**job_args)
        # update jobs attributes
        for k, v in vars(tmp).items():
            if k.startswith("_"):
                continue 
            setattr(job, k, v)
        del tmp

        # remove the deleted tags from db, 
        # add newly added tags to db
        all_tags = set(tags)    # updated tags
        for t in ex_tags:
            if t.name in all_tags:
                # if an existing tag is still in updated tags,
                # remove from all tags which will be the set
                # for newly added tags after the loop is finished
                all_tags.remove(t.name)   
            else:
                # if an existing tag is deleted by user
                # remove from db
                session.delete(t)
                logger.debug("delete tag {} for job {}".format(t.name, job_args['name']))
        # create all non-existing tags
        for name in all_tags:
            session.add(Tag(name, job_args['name']))
            logger.debug("add tag {} for job {}".format(name, job_args['name']))

        all_subs = set(subscribers)    # updated subscribers
        for s in ex_subs:
            if s.email in all_subs:
                all_subs.remove(s.email)
            else:
                session.delete(s)
        for email in all_subs:
            session.add(JobAlert(job_name=job.name, email=email))

        session.commit()

    @classmethod
    @provide_session
    def block_job_till(cls, job_name, block_till, 
                    block_msg, email, errors, session=None):
        job = session.query(Job).filter(
                Job.name==job_name).with_for_update().first()
        if not job:
            errors.append("no job with name {}".format(job_name))
            return False 
        try:
            job.block_till = pd.to_datetime(block_till)
        except Exception as e:
            errors.append(str(e))
            return False
        if not valid_email(email):
            error.append("email {} is not valid".format(email))
            return False 
        job.active = False 
        job.block_msg = block_msg 
        job.block_by = email
        session.commit()        
        return True


    @classmethod
    @provide_session
    def change_job_status(cls, job_name, session=None, deactivate=True):
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
            logger.warning(msg)
        return msg

    @classmethod
    @provide_session
    def check_task_stdout(cls, task_id, session=None):
        # read-only
        task = session.query(TaskInstance).filter(TaskInstance.id==task_id).first()
        return task


    @classmethod
    @provide_session
    def remove_job(cls, job_name, session=None):
        """ remove from job table """
        job = session.query(Job).filter(Job.name==job_name
                    ).with_for_update().first()
        tags = session.query(Tag).filter(Tag.job_name==job_name
                    ).with_for_update().all()
        tasks = session.query(TaskInstance).filter(TaskInstance.job_name
                    ==job_name).with_for_update().all()
        job_alerts = session.query(JobAlert).filter(JobAlert.job_name
                    ==job_name).with_for_update().all()
        # NOTE:
        # not exactly clear whether to delete all tag related alerts
        session.delete(job)
        for t in tags:
            session.delete(t)
        for t in tasks:
            session.delete(t)
        for j in job_alerts:
            session.delete(j)
        session.commit()

    @classmethod
    @provide_session
    def force_schedule_for_job(cls, job_name, session=None):
        job = session.query(Job).filter(Job.name==job_name
                ).with_for_update().first()
        if job:
            task_id = job.schedule_task(session, force_run=True)
            return task_id 
        return None

    @classmethod
    @provide_session
    def subscribe(cls, inst_type, name, email, session=None):
        if inst_type == 'job':
            alert = JobAlert(job_name=name, email=email)
        elif inst_type == 'tag':
            alert = TagAlert(tag_name=name, email=email)

        session.add(alert)
        session.commit()

    @classmethod
    @provide_session
    def unsubscribe(cls, inst_type, name, email, session=None):
        if inst_type == 'job':
            sub = session.query(JobAlert).filter(and_(
                    JobAlert.job_name==name, JobAlert.email==email)
                    ).with_for_update().all()
        elif inst_type == 'tag':
            sub = session.query(TagAlert).filter(and_(
                    TagAlert.tag_name==name, TagAlert.email==email)
                    ).with_for_update().all()
        for s in sub:
            session.delete(s)
        session.commit()

    @classmethod
    @provide_session
    def get_subscribed(cls, inst_type, name, session=None):
        if inst_type == 'job':
            subs = session.query(JobAlert.email).filter(
                JobAlert.job_name==name).all()
        elif inst_type == 'tag':
            subs = session.query(TagAlert.email).filter(
                TagAlert.tag_name==name).all()
        return sorted([s[0] for s in subs])


# class Monitor(object):
    # this is to check scheduler heartbeat
    # should be able to give alert if scheduler
    # stops sending heartbeat

# class Worker(RedisObject): pass
