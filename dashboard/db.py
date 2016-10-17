from contextlib import contextmanager
from functools import wraps
import pyodbc
from redis import StrictRedis
from sqlalchemy import create_engine 
from sqlalchemy.orm import scoped_session, sessionmaker

from dashboard.config import config
from dashboard.utils import Singleton

#
# kk, I know how messy this looks...
#


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

_redis_conn = RedisConn(host='localhost', port=6379, db=0)



# This is for dev
SQL_ALCHEMY_CONN = config['default'].SQLALCHEMY_DATABASE_URI

engine = None
session_factory = None


# enterprise = None

# def configure_sql_server():

def configure_orm():
    global engine
    global session_factory
    engine_args = {}
    if 'sqlite' not in SQL_ALCHEMY_CONN:
        # Engine args not supported by sqlite
        engine_args['pool_size'] = conf.getint('core', 'SQL_ALCHEMY_POOL_SIZE')
        engine_args['pool_recycle'] = conf.getint('core',
                                                  'SQL_ALCHEMY_POOL_RECYCLE')

    engine = create_engine(SQL_ALCHEMY_CONN, **engine_args)
    session_factory = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine))

configure_orm()

def get_redis_conn():
    return _redis_conn

@contextmanager
def get_sql_session():
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


# @contextmanager
# def open_sql_server_session(config, db, commit=False):
#     # This is for dev
#     conn = pyodbc.connect(config['default'])
#     cursor = conn.cursor()
#     try:
#         yield cursor
#     except pyodbc.DatabaseError as e:
#         error, = e.args
#         cursor.execute("ROLLBACK")
#         raise e 
#     else:
#         if commit:
#             cursor.execute("COMMIT")
#         else:
#             cursor.execute("ROLLBACK")
#     finally:
#         connection.close()


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
