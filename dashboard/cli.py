import argparse 
from datetime import datetime, timedelta

from models import RequestHandler, ScheduleManager 


def start_schedule_manager(args):
    sched = ScheduleManager()
    sched.start()

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
    add_job.add_argument("-i", "--run_interval", default=timedelta(days=1))
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
    clear_db.set_defaults(func=RequestHandler.clear_db)

    # job info 
    job_info = subparser.add_parser("info")
    # fill in later

    # start scheduler 
    start_scheduler = subparser.add_parser("start")
    start_scheduler.set_defaults(func=start_schedule_manager)        


    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
