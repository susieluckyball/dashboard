import argparse 
from datetime import datetime, timedelta
import logging
import sys

from dashboard.db import get_redis_conn
from dashboard.manager import manager
from dashboard.models import RequestHandler, ScheduleManager 

logger = logging.getLogger('dashboard')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)



def start_schedule_manager(args):
    logger.info("start scheduler")
    sched = ScheduleManager()
    # should have a graceful interrupt handler
    # to catch sigint...
    try:
        sched.start()
    except:
        conn = get_redis_conn()
        conn.delete(ScheduleManager.name)
        raise

# # will have to add command...
def start_web_server(args):
    # manager.run() 
    pass


def info_jobs(args):
    res = None
    if args.all:
        res = RequestHandler.info_all_jobs()
    elif args.name:
        if not args.tasks:
            res = RequestHandler.info_job(args.name)
        else: 
            res = RequestHandler.info_task_by_job(args.name)
    logger.info(res)

def clear_db_func(args):
    if args.redis:
        confirm = raw_input("Flush db will clear all existing data in redis (celery related) [Y/N]: ")
        if confirm.upper().startswith('Y'):
            RequestHandler.clear_redis()
        else:
            logger.info("Clear db aborted.")
    elif args.sql:
        confirm = raw_input("Flush db will clear all existing data in sql server (jobs and tasks info) [Y/N]: ")
        if confirm.upper().startswith('Y'):
            RequestHandler.clear_sql_db()
        else:
            logger.info("Clear db aborted.")

def main():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers()

    # add job
    add_job = subparser.add_parser("add")
    add_job.add_argument("-n", "--name", help="Name of the job")
    add_job.add_argument("-z", "--timezone", choices=["US/Eastern", "US/Central", "Europe/London"],
                         help="Timezone of the job")
    add_job.add_argument("-s", "--start_dt")
    add_job.add_argument("-e", "--end_dt", default=None)
    add_job.add_argument("-i", "--schedule_interval", default=60*60*24)
    add_job.add_argument("-o", "--operator", default="bash")
    add_job.add_argument("-c", "--command", default="sleep 10")
    add_job.add_argument("-t", "--tags", default=None)
    add_job.set_defaults(func=RequestHandler.add_job)

    # deactivate job
    deactivate_job = subparser.add_parser("deactivate")
    deactivate_job.add_argument("-n", "--name", help='Name of the job to be deactivated')
    deactivate_job.set_defaults(func=RequestHandler.deactivate_job)

    # clear db 
    clear_db = subparser.add_parser("clear_db")
    clear_db.add_argument("-r", "--redis", help="clear redis db", action='store_true')
    clear_db.add_argument("-s", "--sql", help="clear sql db", action='store_true')
    clear_db.set_defaults(func=clear_db_func)

    # job info 
    job_info = subparser.add_parser("info")
    job_info.add_argument("-a", "--all", help="get all job names", 
                            action='store_true')
    job_info.add_argument("-n", "--name", help="input job name for info")
    job_info.add_argument("-t", "--tasks", help="get all task status for job", 
                            action='store_true')
    job_info.set_defaults(func=info_jobs)
    # fill in later

    # start scheduler 
    start_scheduler = subparser.add_parser("start")
    start_scheduler.set_defaults(func=start_schedule_manager)        

    # start web server 
    start_web = subparser.add_parser("webserver")
    start_web.set_defaults(func=start_web_server)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':


    main()
