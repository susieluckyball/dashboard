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
Session = None

def configure_orm():
    global engine
    global Session
    engine_args = {}
    if 'sqlite' not in SQL_ALCHEMY_CONN:
        # Engine args not supported by sqlite
        engine_args['pool_size'] = conf.getint('core', 'SQL_ALCHEMY_POOL_SIZE')
        engine_args['pool_recycle'] = conf.getint('core',
                                                  'SQL_ALCHEMY_POOL_RECYCLE')

    engine = create_engine(SQL_ALCHEMY_CONN, **engine_args)
    Session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine))

configure_orm()

def get_redis_conn():
    return _redis_conn

def get_sql_session():
    session = Session()
    session._model_changes = {}
    return session

