from dotenv import load_dotenv
from musical_genres_rag.Storage import PostgresDatabase
from musical_genres_rag.Storage import Cache
from musical_genres_rag.Repository import GenresRepository
from musical_genres_rag.Index import Index, PostgresSearchEngine
from musical_genres_rag.Rag import GenresRag
from musical_genres_rag.Evaluation import GenreQuestionsGroundTruth
import json

load_dotenv()
cache = Cache()
database = PostgresDatabase()
genreRepository = GenresRepository(database, cache)
table = 'genre_index'
searchEngine = PostgresSearchEngine(database, table)
index = Index(searchEngine, genreRepository)
genresRag = GenresRag(genreRepository, index)

def ingest():
    index.index()

def rag():
    query = 'Which genre started alongside rock and roll before becoming more commercially oriented?';
    response = genresRag.query(query)
    print(response.toJson())

def groundTruth():
    groundTruthGenerator = GenreQuestionsGroundTruth(genreRepository)
    groundTruthGenerator.generate()
