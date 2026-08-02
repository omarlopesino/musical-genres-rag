from musical_genres_rag.Config import Config
from musical_genres_rag.Demo import DemoExport, DemoLoad
from musical_genres_rag.Evaluation import GenreQuestionsGroundTruth, GenresRagEvaluationRunner, GenresRetrievalEvaluationRunner, GroundTruthAnswers
from musical_genres_rag.Feedback import FeedbackRelevanceJudge
from musical_genres_rag.Index import Index, PostgresSearchEngine
from musical_genres_rag.Rag import GenresRag
from musical_genres_rag.Repository import AttachmentsRepository, ConversationsRepository, EvaluationRunsRepository, FeedbackRepository, GenresRepository, JudgeBatchRepository
from musical_genres_rag.Vectorizer import VectorizerDownload

GENRE_INDEX_TABLE = 'genre_index'

"""Every engine a run can be scored against, keyed by the name it is stored under.

The key must be what the engine's own getName() returns, since that is what lands in
EvaluationRun.retriever and Attachment.engine, and what any comparison groups by.

Adding a way of searching means adding a builder here: the command line, the API and the dags all
offer whatever this lists, and an evaluation groups by it.
"""
ENGINES = {
    'postgres_text': lambda: PostgresSearchEngine(GENRE_INDEX_TABLE, 'text'),
    'postgres_embed': lambda: PostgresSearchEngine(GENRE_INDEX_TABLE, 'embed'),
    'postgres_hybrid': lambda: PostgresSearchEngine(GENRE_INDEX_TABLE, 'hybrid'),
}

"""The one everything runs through when a run does not name another.

Configured rather than chosen here, since which way of searching this application is being run with
is a decision about a deployment and not about the code. "--engine" on a command and "engine" in an
API request still say otherwise for a single run.
"""
INDEX_ENGINE = Config.getShared().getIndexEngine()

"""Builds the object graph on demand.

Built lazily rather than at import time, so a manage.py subcommand that never
touches genres does not open a database connection or an OpenAI client.
"""

def buildGenresRepository():
    return GenresRepository()

def buildAttachmentsRepository():
    return AttachmentsRepository()

def buildGenresIndex(engine = INDEX_ENGINE, repository = None):
    repository = repository if repository is not None else buildGenresRepository()
    return Index(ENGINES[engine](), repository)

def buildGenresRag(engine = INDEX_ENGINE):
    repository = buildGenresRepository()
    return GenresRag(repository, buildGenresIndex(engine, repository))

def buildGenresGroundTruth():
    return GenreQuestionsGroundTruth(buildGenresRepository(), buildAttachmentsRepository())

def buildEvaluationRunsRepository():
    return EvaluationRunsRepository()

def buildConversationsRepository():
    return ConversationsRepository()

def buildFeedbackRepository():
    return FeedbackRepository()

def buildJudgeBatchRepository():
    return JudgeBatchRepository()

def buildFeedbackRelevanceJudge():
    return FeedbackRelevanceJudge(buildFeedbackRepository(), buildJudgeBatchRepository())

def buildGenresRagEvaluationRunner(engine = INDEX_ENGINE):
    return GenresRagEvaluationRunner(
        buildGenresIndex(engine),
        buildAttachmentsRepository(),
        buildEvaluationRunsRepository(),
    )

def buildGenresRetrievalEvaluationRunner(engine = INDEX_ENGINE):
    return GenresRetrievalEvaluationRunner(
        buildGenresIndex(engine),
        buildAttachmentsRepository(),
        buildEvaluationRunsRepository(),
    )

def buildGroundTruthAnswers(engine = INDEX_ENGINE):
    return GroundTruthAnswers(buildGenresRag(engine), buildAttachmentsRepository())

def buildDemoExport():
    return DemoExport(buildEvaluationRunsRepository(), buildAttachmentsRepository())

def buildDemoLoad():
    return DemoLoad(buildEvaluationRunsRepository(), buildAttachmentsRepository())

def buildVectorizerDownload():
    return VectorizerDownload()
