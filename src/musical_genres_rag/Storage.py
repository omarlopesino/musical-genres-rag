import os
import redis

class Cache():

    def __init__(self):
        self.assertEnvironment()
        self.redis = redis.Redis(host=os.getenv('REDIS_HOST'), port=os.getenv('REDIS_PORT', '6379'), db=os.getenv('REDIS_DATABASE', '0'))

    def assertEnvironment(self):
        for variable in ['REDIS_HOST']:
            if (os.getenv(variable) is None):
                raise Exception('The environment variable "' + variable + '" is required to run Redis.')

    def getValue(self, cid):
        return self.redis.get(cid)

    def setValue(self, cid, value):
        return self.redis.set(cid, value)

import os
import psycopg
from contextlib import contextmanager

"""Provides a database connection"""
class Database():

    @contextmanager
    def transaction(self):
        pass

    """Runs a query, with optional placeholder values as a sequence or a mapping"""
    @contextmanager
    def query(self, query, params = None):
        pass

"""Provides a database connection"""
class PostgresDatabase(Database):

    """ Initializes database """
    def __init__(self):
        self.assertEnvironment()
        self.host = os.getenv('POSTGRES_HOST')
        self.port = os.getenv('POSTGRES_PORT', '5432')
        self.user = os.getenv('POSTGRES_USER')
        self.password = os.getenv('POSTGRES_PASSWORD')
        self.database = os.getenv('POSTGRES_DATABASE')
        self.connection = None

    def assertEnvironment(self):
        for variable in ['POSTGRES_HOST', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DATABASE']:
            if (os.getenv(variable) is None):
                raise Exception('The environment variable "' + variable + '" is required to run the database.')

    """Opens the connection on first use and reuses it afterwards, as connecting costs way more than querying"""
    def getConnection(self):
        if self.connection is None or self.connection.closed:
            self.connection = psycopg.connect(
                host= self.host,
                port= self.port,
                dbname= self.database,
                user= self.user,
                password= self.password,
                autocommit= True,
            )

        return self.connection

    def close(self):
        if self.connection is not None and not self.connection.closed:
            self.connection.close()

        self.connection = None

    @contextmanager
    def transaction(self):
        conn = self.getConnection()
        with conn.transaction():
            with conn.cursor() as cursor:
                yield cursor

    """Runs a query, with optional placeholder values as a sequence or a mapping"""
    @contextmanager
    def query(self, query, params = None):
        with self.getConnection().cursor() as cursor:
            yield self._runQuery(query, cursor, params)

    def _runQuery(self, query, cursor, params = None):
        cursor.execute(query, params)
        return cursor
