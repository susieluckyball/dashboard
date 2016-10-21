from contextlib import contextmanager
from functools import wraps
import logging
import pyodbc
import re
from redis import StrictRedis
from sqlalchemy import create_engine 
from sqlalchemy.orm import scoped_session, sessionmaker

from dashboard.configuration import conf
from dashboard.utils.miscellaneous import Singleton

logger = logging.getLogger(__name__)

# convert from bytes to string...
class RedisConn(StrictRedis):
    __metaclass__ = Singleton

    def hgetall(self, name):
        d = StrictRedis.hgetall(self, name)
        decoded_d = {}
        for k, v in d.items():
            k = k.decode() if isinstance(k, bytes) else k 
            v = v.decode() if isinstance(v, bytes) else v 
            decoded_d[k] = v 
        return decoded_d

    def hget(self, name, key):
        v = StrictRedis.hget(self, name, key)
        v = v.decode() if isinstance(v, bytes) else v
        return v

_redis_conn = None 
engine = None 
session_factory = None

def configure_databases():
    # config manager heart beat 
    manager_heart_beat = conf.get('manager', 'send_heart_beat')
    global _redis_conn
    if manager_heart_beat.startswith('redis'):
        m = re.compile('redis://(?P<host>\w+):(?P<port>\d+)/(?P<db>\d+)')
        redis_cfg = m.match(manager_heart_beat).groupdict()
        try:
            _redis_conn = RedisConn(host=redis_cfg['host'],
                    port=int(redis_cfg['port']),
                    db=int(redis_cfg['db']))
        except RuntimeError:    # should have 
            logger.exception('Cannot config redis with {}'.format(
                        manager_heart_beat))

    # config webserver db 
    global engine
    global session_factory    
    engine_args = {}
    web_db = conf.get('webserver', 'database')
    if 'sqlite' not in web_db:
        # Engine args not supported by sqlite
        engine_args['pool_size'] = conf.getint('core', 'sqlalchemy_pool_size')
        engine_args['pool_recycle'] = conf.getint('core',
                                                  'sqlalchemy_pool_recycle')

    engine = create_engine(web_db, **engine_args)
    session_factory = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine))

configure_databases()


#####################
# Interfaces 
#####################

def get_redis_conn():
    return _redis_conn

@contextmanager
def get_sql_session():
    """ This webserver db connect session """
    session = session_factory()
    session._model_changes = {}
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise 
    finally:
        session.close()


@contextmanager
def open_sql_server_session(db, commit=False):
    """ This is data sql server session """
    driver = conf.get('database', 'DRIVER')
    server = conf.get('database', db)
    conn_str = "Driver={{driver}};Server={server};Database={db};Trusted_Connection=Yes;".format(
                driver=driver, server=server, db=db)
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    try:
        yield cursor
    except pyodbc.DatabaseError as e:
        error, = e.args
        cursor.execute("ROLLBACK")
        raise e 
    else:
        if commit:
            cursor.execute("COMMIT")
        else:
            cursor.execute("ROLLBACK")
    finally:
        conn.close()


def provide_session(func):
    """
    Function decorator that provides a session if it isn't provided.
    If you want to reuse a session or run the function as part of a
    database transaction, you pass it to the function, if not this wrapper
    will create one and close it for you.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        needs_session = False
        arg_session = 'session'
        func_params = func.__code__.co_varnames
        session_in_args = arg_session in func_params and \
            func_params.index(arg_session) < len(args)
        if not (arg_session in kwargs or session_in_args):
            needs_session = True
            session = session_factory()
            session._model_changes = {}
            kwargs[arg_session] = session
        result = func(*args, **kwargs)
        if needs_session:
            session.expunge_all()
            session.commit()
            session.close()
        return result
    return wrapper


# def sql_server_session(func, db_name):
#     @wraps(func)
#     def wrapper(*args, **kwargs):
#         conn = pyodbc.connect(config['default']['db'][db_name])
#         cursor = conn.cursor()
#         kwargs["cursor"] = cursor
#         result = func(*args, **kwargs)
#         cursor

# def run_query_on_sql_server(db_name, query, config=config['default']['db']):
#     with pyodbc.connect(config[db_name]):
#         cursor = conn.cursor()
#         res = cursor.execute(query)
#     return cursor




