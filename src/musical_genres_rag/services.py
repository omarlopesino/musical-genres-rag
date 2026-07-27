from musical_genres_rag.Evaluation import GenreQuestionsGroundTruth, EvaluationRunner, GroundTruthAnswers
from musical_genres_rag.Index import Index, PostgresSearchEngine
from musical_genres_rag.Rag import GenresRag
from musical_genres_rag.Repository import GenresRepository

GENRE_INDEX_TABLE = 'genre_index'

"""Builds the object graph on demand.

Built lazily rather than at import time, so a manage.py subcommand that never
touches genres does not open a database connection or an OpenAI client.
"""

def buildGenresRepository():
    return GenresRepository()

def buildGenresIndex(repository = None):
    repository = repository if repository is not None else buildGenresRepository()
    return Index(PostgresSearchEngine(GENRE_INDEX_TABLE), repository)

def buildGenresRag():
    repository = buildGenresRepository()
    return GenresRag(repository, buildGenresIndex(repository))

def buildGenresGroundTruth():
    return GenreQuestionsGroundTruth(buildGenresRepository())

def buildEvaluationRunner():
    return EvaluationRunner(buildGenresIndex())

def buildGroundTruthAnswers():
    return GroundTruthAnswers(buildGenresRag())
