import argparse 
from datetime import datetime, timedelta

from models import RequestHandler, ScheduleManager 
from manager import manager

def start_schedule_manager(args):
    sched = ScheduleManager()
    sched.start()

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
    print(res)

def clear_db(args):
    confirm = raw_input("Flush db will clear all existing data [Y/N]: ")
    if confirm.upper().startswith('Y'):
        RequestHandler.clear_db()
    else:
        print("Aborted")

def main():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers()

    # add job
    add_job = subparser.add_parser("add")
    add_job.add_argument("-n", "--name", help="Name of the job")
    add_job.add_argument("-z", "--timezone", choices=["US/Eastern", "US/Central", "Europe/London"],
                         help="Timezone of the job")
    add_job.add_argument("-s", "--start_dt", default=datetime.now())
    add_job.add_argument("-e", "--end_dt", default=None)
    add_job.add_argument("-i", "--schedule_interval", default=timedelta(days=1))
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
    clear_db.set_defaults(func=clear_db)

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
