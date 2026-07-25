from musical_genres_rag.Storage import Database
from musical_genres_rag.Storage import Cache
from musical_genres_rag.Repository import GenresRepository
from musical_genres_rag.Model import Genre
from dotenv import load_dotenv
import json

load_dotenv()

def debug():
    database = Database()
    cache = Cache()
    grepo = GenresRepository(database, cache)
    genres = grepo.loadMultiple()
    for genre in genres:
        print(genre)
        print(genre.name)
        print(genre.instruments)

def debugCacheAndQueries():
    cache = Cache()
    cacheValue = cache.getValue('test_rows')
    if (not cacheValue is None):
        rows = json.loads(cacheValue)
    else:
        database = Database()
        with database.query('SELECT name FROM genre') as result:
            rows = result.fetchall()
            cache.setValue('test_rows', json.dumps(rows))

    for row in rows:
        [name] = row
        print('Name=' + name)
