from dotenv import load_dotenv
from musical_genres_rag.Storage import PostgresDatabase
from musical_genres_rag.Storage import Cache
from musical_genres_rag.Repository import GenresRepository
from musical_genres_rag.Index import Index, PostgresSearchEngine
from musical_genres_rag.Rag import GenresRag
import json

load_dotenv()
cache = Cache()
database = PostgresDatabase()
grepo = GenresRepository(database, cache)
table = 'genre_index'
searchEngine = PostgresSearchEngine(database, table)
index = Index(searchEngine, grepo)

def ingest():
    index.index()

def rag():
    query = 'What genres could be good If I like electronic music and a lot of drums?';
    genresRag = GenresRag(grepo, index)
    response = genresRag.query(query)
    print(response.toJson())
