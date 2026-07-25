from dotenv import load_dotenv
from musical_genres_rag.Storage import Database
from musical_genres_rag.Storage import Cache
from musical_genres_rag.Repository import GenresRepository
from musical_genres_rag.Index import Index

def ingest():
    load_dotenv()
    cache = Cache()
    database = Database()
    grepo = GenresRepository(database, cache)
    table = 'genre_index'
    index = Index(database, table, grepo)
    index.index()
