import croniter
from datetime import datetime
import pandas as pd 
import re

# probably should use datetime and dateutils
# but pandas makes it so simple...
def convert_to_utc(timestamp_str, timezone):
    return pd.to_datetime(timestamp_str).\
                tz_localize(timezone).astimezone('UTC').\
                replace(tzinfo=None)

def convert_to_local(timestamp, timezone):
	return pd.to_datetime(timestamp).\
				tz_localize('UTC').astimezone(timezone).\
				replace(tzinfo=None)



cron_presets = {
    '@hourly': '{m} * * * *',
    '@daily': '{m} {h} * * *',
    '@weekly': '{m} {h} * * {weekday}',
    '@weekdaydaily': '{m} {h} * * 1-5'
    # '@monthly': '0 0 1 * *',
    # '@yearly': '0 0 1 1 *',
}

validate_crontab_time_format_regex = re.compile(\
        "{0}\s+{1}\s+{2}\s+{3}\s+{4}".format(\
            "(?P<minute>\*|[0-5]?\d)",\
            "(?P<hour>\*|[01]?\d|2[0-3])",\
            "(?P<day>\*|0?[1-9]|[12]\d|3[01])",\
            "(?P<month>\*|0?[1-9]|1[012])",\
            "(?P<day_of_week>\*|[0-6](\-[0-6])?)"\
        ) # end of str.format()
    ) # end of re.compile()

def get_cron_schedule_interval(schedule_interval, start_dt, weekday_to_run=None):
    if schedule_interval in cron_presets:
        return cron_presets[schedule_interval].format(m=start_dt.minute,
        		h=start_dt.hour, weekday=start_dt.weekday()+1)
    
    interval_hr = int(schedule_interval)
    assert interval_hr < 24 and interval_hr > 0
    assert isinstance(weekday_to_run, list)
    assert all([isinstance(i, str) for i in weekday_to_run])
    cron_str = '* */{hr} * * {weekday}'.format(
    		hr=interval_hr,weekday=",".join(weekday_to_run))
    return cron_str

def get_next_run_ts(crontab):
	cron = croniter.croniter(crontab)
	return cron.get_next(datetime)



