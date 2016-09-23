import argparse 
from datetime import datetime

def main():
	parser = argparse.ArgumentParser()

	subparser = parser.add_subparsers()
	add_job = subparser.add_parser("add_job")
	add_job.add_argument("-n", "--name", help="Name of the job")
	add_job.add_argument("-z", "--timezone", choices=["US/Eastern", "US/Central", "Europe/London"] help="Timezone of the job")
	add_job.add_argument("-s", "--start_dt", default=datetime.now())
	add_job.add_argument("-e", "--end_dt", default=None)
