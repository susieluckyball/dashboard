from configparser import ConfigParser 
import errno
import os
import six

DEV_CONFIG = """ 
[core]
dashboard_home = {DASHBOARD_HOME}
sqlalchemy_pool_size = 16
sqlalchemy_pool_recycle = 4

[celery]
celery_broker_url = redis://localhost:6379/0
celery_result_url = redis://localhost:6379/0

[manager]
logger = None
send_heart_beat = redis://localhost:6379/0

[monitor]
logger = None

[webserver]
database = sqlite:///{DASHBOARD_HOME}/dashboard_web.sqlite
webserver_host = 0.0.0.0
web_server_port = 5000

[database]
# Since all those databases connections are read-only
# I will simply use production db for test
DRIVER = SQL Server Native Client 10.0
# This is for my linux vm config
# driver = ODBC Driver 13 for SQL Server
ENTERPRISE = DALDATA1,1433
REFERENCE = DALDATA5,1633
VENDORREF = DALDATA5,1633
VENDOR = DALDATA1,1433
VENDORQS = DALDATA9,1433
STATARB = DALDATA1,1433
LOANPERFORMANCE = DALSCDATA1
EMBS = DALSCDATA1
EMBSHIST = DALSCDATA1
VENDORSC = DALSCDATA1

[smtp]
mail_server = smtpmail.hbk.com
mail_port = 25
mail_use_tls = True
mail_from = dashboarddev@hbk.com
"""


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
# create 
relative = os.path.join('~', 'sandbox', 'dashboard')
DASHBOARD_HOME =  os.path.expanduser(os.path.expandvars(relative))
mkdir_p(DASHBOARD_HOME)



class DashboardConfigParser(ConfigParser):

    def __init__(self, *args, **kwargs):
        ConfigParser.__init__(self, *args, **kwargs)
        self.read_string(DEV_CONFIG.format(DASHBOARD_HOME=DASHBOARD_HOME))

    def read_string(self, string, source='<string>'):
        """
        Read configuration from a string.

        A backwards-compatible version of the ConfigParser.read_string()
        method that was introduced in Python 3.
        """
        # Python 3 added read_string() method
        if six.PY3:
            ConfigParser.read_string(self, string, source=source)
        # Python 2 requires StringIO buffer
        else:
            import StringIO
            self.readfp(StringIO.StringIO(string))


conf = DashboardConfigParser()