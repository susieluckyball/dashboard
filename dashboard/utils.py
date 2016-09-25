import pandas as pd 

def convert_to_utc(timestamp_str, timezone):
    return pd.to_datetime(timestamp_str).\
                tz_localize(timezone).astimezone('UTC').\
                replace(tzinfo=None)

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

