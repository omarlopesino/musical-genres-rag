from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from django.conf import settings
from django.http import FileResponse
from ninja import NinjaAPI, Schema
from pydantic import Field

from musical_genres_rag.Feedback import DEFAULT_LIMIT
from musical_genres_rag.Progress import CacheProgress, readProgress
from musical_genres_rag.Report import batchFeedbackUrl, reportUrl
from musical_genres_rag.services import (
    ENGINES,
    INDEX_ENGINE,
    buildAttachmentsRepository,
    buildFeedbackRelevanceJudge,
    buildGenresGroundTruth,
    buildGenresIndex,
    buildGenresRagEvaluationRunner,
    buildGenresRetrievalEvaluationRunner,
    buildGroundTruthAnswers,
)
from musical_genres_rag.Task import BackgroundTasks, OperationLock

"""The JSON API an orchestrator runs this project by.

Building the index, writing the questions to ask it, answering them and scoring those answers: the
four things worth running on a schedule, and every one of them takes minutes and spends paid calls.
So none is answered by holding the connection open until it is over. A POST starts the work and
answers with the task it is followed by, and what the work produced — the counts, whether it went
well, where to read it — is the "result" the progress carries once it is done.

The work itself is the project's own, reached through services.py, so an endpoint and the command
of the same name are one piece of code and not two of them drifting apart.

Wire names are the JSON ones (task_id, ground-truth), which is why they read unlike the rest of
this codebase: they are what the caller writes, not what we call ourselves.
"""

INGEST = 'ingest'
GROUND_TRUTH = 'ground-truth'
CREATE_ANSWERS = 'create-answers'
EVALUATE_RAG = 'evaluate-rag'
EVALUATE_RETRIEVAL = 'evaluate-retrieval'
FEEDBACK_JUDGE = 'feedback-judge'

# Where the files those operations write are downloaded from, one id per registered attachment
ATTACHMENTS_PATH = '/attachments'

RUNNING = 'running'

# What a caller may name its own run: whatever needs no escaping in the URL it is then read at
TASK_ID_PATTERN = r'^[A-Za-z0-9._-]{1,128}$'

"""What each operation says of itself once it is over.

A failure carries the same keys as its success, counting nothing and linking nowhere, so both are
read the same way. The reason it failed is not among them: that is written to the server's log in
full, which is where the line below sends whoever needs it.
"""
INGEST_SUCCESS = 'Data has been ingested sucessfully.'
INGEST_FAILURE = {
    'ingested': 0,
    'success': False,
    'info': 'There was an error ingesting data. Please run make ingest in the server for more details.',
}

GROUND_TRUTH_SUCCESS = 'Ground truth has been generated successfully.'
GROUND_TRUTH_FAILURE = {
    'generated': 0,
    'success': False,
    'info': 'There was an error generating the ground truth. Please run make groundtruth in the server for more details.',
    'link': None,
}

CREATE_ANSWERS_SUCCESS = 'Ground truth answers have been created successfully.'
CREATE_ANSWERS_FAILURE = {
    'answered': 0,
    'success': False,
    'info': 'There was an error creating the ground truth answers. Please run make createAnswers in the server for more details.',
    'link': None,
}

EVALUATE_RAG_SUCCESS = 'The RAG has been evaluated successfully.'
EVALUATE_RAG_FAILURE = {
    'success': False,
    'info': 'There was an error evaluating the RAG. Please run make evaluate in the server for more details.',
    'link': None,
}

EVALUATE_RETRIEVAL_SUCCESS = 'Retrieval has been evaluated successfully.'
EVALUATE_RETRIEVAL_FAILURE = {
    'success': False,
    'info': 'There was an error evaluating retrieval. Please run make evaluateRetrieval in the server for more details.',
    'link': None,
}

"""The only operation with no target of its own to point a failure at: nothing generates the
feedback it reads but the people leaving it, so its reason is only ever in the server's log."""
FEEDBACK_JUDGE_SUCCESS = 'The feedback has been judged successfully.'
FEEDBACK_JUDGE_FAILURE = {
    'total': 0,
    'success': False,
    'info': 'There was an error judging the feedback. Please read the app log in the server for more details.',
    'link': None,
}

BUSY = 'Another {operation} is already running as task "{task}". Wait for it to finish before starting this one.'
UNKNOWN = 'No task "{task}" was ever started here, or it is old enough to have been forgotten.'

# A file registered but no longer on disk reads the same as one that never was: it cannot be served
MISSING = 'No file {id} was ever generated here, or it is no longer where it was written.'

# Named after the engines themselves, so the documentation offers the very list the command line takes
Engine = Enum('Engine', {name: name for name in ENGINES})

api = NinjaAPI(
    title = 'Musical genres RAG',
    version = '1.0.0',
    description = 'Runs the ingest, the ground truth and the evaluations, one task at a time.',
)

tasks = BackgroundTasks()

class TaskRequest(Schema):
    task_id: Optional[str] = Field(default = None, pattern = TASK_ID_PATTERN)

class EngineRequest(TaskRequest):
    engine: Engine = Engine(INDEX_ENGINE)

"""How many answers one run may read. Every one of them is a paid call, so a caller that runs this
on a schedule bounds what a run costs rather than letting it read whatever has piled up."""
class JudgeRequest(TaskRequest):
    limit: int = Field(default = DEFAULT_LIMIT, ge = 1)

class Accepted(Schema):
    task_id: str
    status: str

"""What is answered when the work was not started at all, shaped like an outcome so a caller
reads a refusal the same way it reads a failure"""
class Refused(Schema):
    task_id: Optional[str]
    success: bool
    info: str

class ProgressResponse(Schema):
    task_id: str
    operation: str
    phase: str
    current: int
    total: Optional[int]
    percent: Optional[float]
    started_at: str
    updated_at: str
    done: bool
    success: Optional[bool]
    info: Optional[str]
    result: Optional[Dict[str, Any]]

STARTED = {202: Accepted, 409: Refused}

@api.post('/ingest', response = STARTED, summary = 'Rebuild the index from every stored genre')
def ingest(request, payload: EngineRequest):
    return dispatch(INGEST, payload, ingesting(payload.engine.value), INGEST_FAILURE)

@api.post('/ground-truth', response = STARTED, summary = 'Generate the ground truth question set')
def groundTruth(request, payload: TaskRequest):
    return dispatch(GROUND_TRUTH, payload, generating(), GROUND_TRUTH_FAILURE)

@api.post('/create-answers', response = STARTED, summary = 'Answer the ground truth through the RAG')
def createAnswers(request, payload: EngineRequest):
    return dispatch(CREATE_ANSWERS, payload, answering(payload.engine.value), CREATE_ANSWERS_FAILURE)

@api.post('/evaluate-rag', response = STARTED, summary = 'Score the whole pipeline over recorded answers')
def evaluateRag(request, payload: EngineRequest):
    return dispatch(
        EVALUATE_RAG,
        payload,
        evaluating(buildGenresRagEvaluationRunner, payload.engine.value, EVALUATE_RAG_SUCCESS),
        EVALUATE_RAG_FAILURE,
    )

@api.post('/evaluate-retrieval', response = STARTED, summary = 'Score the index alone, live and free')
def evaluateRetrieval(request, payload: EngineRequest):
    return dispatch(
        EVALUATE_RETRIEVAL,
        payload,
        evaluating(buildGenresRetrievalEvaluationRunner, payload.engine.value, EVALUATE_RETRIEVAL_SUCCESS),
        EVALUATE_RETRIEVAL_FAILURE,
    )

@api.post('/feedback-judge', response = STARTED, summary = 'Score the answers people left feedback on')
def feedbackJudge(request, payload: JudgeRequest):
    return dispatch(FEEDBACK_JUDGE, payload, judging(payload.limit), FEEDBACK_JUDGE_FAILURE)

"""How far a task got, and what it left behind once it is done.

A run that ended badly is answered with a 500 carrying that very document, so a caller that only
watches the status of what it polls still fails on it.
"""
@api.get('/progress/{task_id}', response = {200: ProgressResponse, 404: Refused, 500: ProgressResponse})
def progress(request, task_id: str):
    document = readProgress(task_id)
    if document is None:
        return 404, {'task_id': task_id, 'success': False, 'info': UNKNOWN.format(task = task_id)}

    if document['done'] and not document['success']:
        return 500, document

    return 200, document

"""The file an operation wrote, downloaded by the id its own result linked to.

Registered paths are relative to the repository root, since that is where every process writing one
runs from, and are resolved against it here rather than against wherever this happens to be served.
Nothing outside that root is served whatever a row says, so a path is never a way out of the project.
"""
@api.get(
    ATTACHMENTS_PATH + '/{attachment_id}',
    response = {200: None, 404: Refused},
    summary = 'Download a generated ground truth or answers file',
)
def download(request, attachment_id: int):
    attachment = buildAttachmentsRepository().load(attachment_id)
    if attachment is None:
        return 404, missing(attachment_id)

    path = Path(settings.BASE_DIR, attachment.getPath()).resolve()
    if not path.is_relative_to(settings.BASE_DIR) or not path.is_file():
        return 404, missing(attachment_id)

    return FileResponse(path.open('rb'), as_attachment = True, filename = path.name)

"""Starts an operation and answers with the task it is followed by.

The lock is taken here and let go of by the thread, so an operation nobody may run twice at once
is refused before anything of it has begun.
"""
def dispatch(operation, payload, work, failure):
    task = payload.task_id if payload.task_id is not None else uuid4().hex
    lock = OperationLock(operation)
    if not lock.take(task):
        return 409, {
            'task_id': lock.holder(),
            'success': False,
            'info': BUSY.format(operation = operation, task = lock.holder()),
        }

    # Written before the work is spawned, so a poll arriving right behind this reply finds a task
    tasks.spawn(released(work, lock), CacheProgress(task, operation), failure)

    return 202, {'task_id': task, 'status': RUNNING}

"""The same work, no longer holding the operation once it is over, however it went"""
def released(work, lock):
    def released(progress):
        try:
            return work(progress)
        finally:
            lock.release()

    return released

"""Shaped like the refusal of an operation, since a caller reading one already reads the other"""
def missing(id):
    return {'task_id': None, 'success': False, 'info': MISSING.format(id = id)}

"""Where a generated file is downloaded from.

Absolute for the caller an operation hands it to, which reaches this application from outside rather
than from the address it is served on.
"""
def attachmentUrl(id, baseUrl = ''):
    return '{base}{path}/{id}'.format(base = baseUrl.rstrip('/'), path = ATTACHMENTS_PATH, id = id)

"""Rebuilds the search index from every genre stored, and reports how many that turned out to be.

What the RAG later retrieves from, so nothing else here is worth running until this has.
"""
def ingesting(engine):
    def work(progress):
        return {
            'ingested': buildGenresIndex(engine).index(progress),
            'success': True,
            'info': INGEST_SUCCESS,
        }

    return work

"""Writes the questions every evaluation is scored against, asked of each genre in turn.

Takes no engine: the questions come from the stored genres themselves, with no index searched, so
one set of them is what two engines are compared over.

The link is where the file just written is downloaded from, so a caller reads the questions it paid
for without a shell on the server that holds them.
"""
def generating():
    def work(progress):
        [attachment, questions] = buildGenresGroundTruth().generate(progress = progress)

        return {
            'generated': questions,
            'success': True,
            'info': GROUND_TRUTH_SUCCESS,
            'link': attachmentUrl(attachment.getId(), settings.API_BASE_URL),
        }

    return work

"""Puts every question of the latest ground truth to the RAG and records what came back.

The generation is paid for here, once, so scoring it afterwards costs nothing and scores the same
answers however often it is run.
"""
def answering(engine):
    def work(progress):
        [attachment, answers] = buildGroundTruthAnswers(engine).generate(progress)

        return {
            'answered': answers,
            'success': True,
            'info': CREATE_ANSWERS_SUCCESS,
            'link': attachmentUrl(attachment.getId(), settings.API_BASE_URL),
        }

    return work

"""Scores the latest ground truth and stores what it scored, as far into the pipeline as the runner
given goes: the index alone, or the answers made of what it retrieved.

The link is that stored run's own page on the app serving the reports, which is where a finished
evaluation is read rather than in anything answered here.
"""
def evaluating(runner, engine, info):
    def work(progress):
        run = runner(engine).execute(progress)

        return {'success': True, 'info': info, 'link': reportUrl(run.id, settings.UI_BASE_URL)}

    return work

"""Reads back every answer somebody left feedback on and nobody has judged yet, and writes down what
a judge made of each.

Takes no engine: an answer is judged against the context it was written from, which the feedback row
carries, so nothing is retrieved and no index is searched.

Reads the oldest waiting first, and no more of them than it was asked for, so what one run costs is
bounded however much feedback has piled up since the last.

The link is the batch's own page on the app serving the reports, narrowed to the answers this run
read. A run that found nothing pending opened no batch and links nowhere, exactly as a run that
failed writes none.
"""
def judging(limit):
    def work(progress):
        [batch, total] = buildFeedbackRelevanceJudge().score(progress, limit)

        return {
            'total': total,
            'success': True,
            'info': FEEDBACK_JUDGE_SUCCESS,
            'link': batchFeedbackUrl(batch.getId(), settings.UI_BASE_URL) if batch is not None else None,
        }

    return work
