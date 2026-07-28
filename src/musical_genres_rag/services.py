from musical_genres_rag.Evaluation import GenreQuestionsGroundTruth, GenresRagEvaluationRunner, GenresRetrievalEvaluationRunner, GroundTruthAnswers
from musical_genres_rag.Index import Index, PostgresSearchEngine
from musical_genres_rag.Rag import GenresRag
from musical_genres_rag.Repository import AttachmentsRepository, EvaluationRunsRepository, GenresRepository

GENRE_INDEX_TABLE = 'genre_index'

"""Every engine a run can be scored against, keyed by the name it is stored under.

The key must be what the engine's own getName() returns, since that is what lands in
EvaluationRun.retriever and Attachment.engine, and what any comparison groups by.

One entry so far. Adding vector or hybrid search means adding a builder here.
"""
ENGINES = {
    'postgres_text': lambda: PostgresSearchEngine(GENRE_INDEX_TABLE, 'text'),
}

DEFAULT_ENGINE = 'postgres_text'

"""Builds the object graph on demand.

Built lazily rather than at import time, so a manage.py subcommand that never
touches genres does not open a database connection or an OpenAI client.
"""

def buildGenresRepository():
    return GenresRepository()

def buildAttachmentsRepository():
    return AttachmentsRepository()

def buildGenresIndex(engine = DEFAULT_ENGINE, repository = None):
    repository = repository if repository is not None else buildGenresRepository()
    return Index(ENGINES[engine](), repository)

def buildGenresRag(engine = DEFAULT_ENGINE):
    repository = buildGenresRepository()
    return GenresRag(repository, buildGenresIndex(engine, repository))

def buildGenresGroundTruth():
    return GenreQuestionsGroundTruth(buildGenresRepository(), buildAttachmentsRepository())

def buildEvaluationRunsRepository():
    return EvaluationRunsRepository()

def buildGenresRagEvaluationRunner(engine = DEFAULT_ENGINE):
    return GenresRagEvaluationRunner(
        buildGenresIndex(engine),
        buildAttachmentsRepository(),
        buildEvaluationRunsRepository(),
    )

def buildGenresRetrievalEvaluationRunner(engine = DEFAULT_ENGINE):
    return GenresRetrievalEvaluationRunner(
        buildGenresIndex(engine),
        buildAttachmentsRepository(),
        buildEvaluationRunsRepository(),
    )

def buildGroundTruthAnswers(engine = DEFAULT_ENGINE):
    return GroundTruthAnswers(buildGenresRag(engine), buildAttachmentsRepository())
