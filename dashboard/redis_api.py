from redis import StrictRedis

from utils import Singleton



def get_redis_conn():
	return _redis_conn

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
