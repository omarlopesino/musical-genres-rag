from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction

from musical_genres_rag.models import EvaluationRun
from musical_genres_rag.Progress import NULL_PROGRESS

import gzip
import json
import shutil

"""The evaluations somebody reads this project by without paying for them first.

Every page of the dashboard but this one is filled by work that spends an LLM call per question, so
whoever is only here to look at the evaluations would have to run the whole pipeline to see one. A
run is not needed for that: a report is stored whole, and reading it back searches no index and asks
nothing of anybody.

So the latest run of each kind is exported into the repository and committed, and loading it is a
dag of its own. The export is run by whoever tunes this; the load, by whoever clones it.
"""

# Committed, unlike ./tests, which is where the same files are written when they are earned
DEMO_DIRECTORY = './data/demo'
SNAPSHOT_NAME = 'snapshot.json.gz'

"""How the snapshot is laid out: the files, and the runs that scored them.

Gzipped because a rag report carries every case's prompt and retrieved context, which is megabytes
of it. The files beside it stay as they were written, since that is how they are downloaded back.
"""
ATTACHMENTS_KEY = 'attachments'
RUNS_KEY = 'runs'

# What a run is spending its time on, for whoever is following it
LOADING = 'loading'

MISSING_RUN = 'Nothing has been scored here as a {type} evaluation, so there is nothing to export: a demo already loaded is not one. Run "make evaluate{target}" first.'
MISSING_FILE = 'Attachment {attachment} names {path}, which is not where it was written any more.'
MISSING_SNAPSHOT = 'No demo data is committed at "{path}".'

# Which target writes the run of each kind, for the message above to send whoever has neither
EXPORT_TARGETS = {
    EvaluationRun.Type.RAG: '',
    EvaluationRun.Type.RETRIEVAL: 'Retrieval',
}

"""Writes the committed demo out of the runs this database already holds.

Takes the latest of each kind rather than a named pair: what is worth showing is whatever the
project scores now, and re-running this after a retune is how that stays true.
"""
class DemoExport:

    def __init__(self, evaluationRunsRepository, attachmentsRepository, directory = DEMO_DIRECTORY):
        self.evaluationRunsRepository = evaluationRunsRepository
        self.attachmentsRepository = attachmentsRepository
        self.directory = directory

    """Returns the runs exported and the files that went with them"""
    def export(self):
        runs = [self._requireLatest(type) for type in EXPORT_TARGETS]
        attachments = self._attachmentsOf(runs)

        # Every file is found before the directory is emptied, so a run naming one that is gone
        # leaves the demo as it was rather than wiping it and failing halfway through
        sources = {attachment.getId(): self._require(attachment) for attachment in attachments}

        self._empty()
        paths = {id: self._copy(source) for [id, source] in sources.items()}

        self._write({
            ATTACHMENTS_KEY: [self._attachment(attachment, paths) for attachment in attachments],
            RUNS_KEY: [self._run(run) for run in runs],
        })

        return [runs, attachments]

    """The latest run of a kind that was actually scored here.

    A demo loaded into this database is skipped: it is a copy of a run exported somewhere else, and
    it carries the date of the run it copies, so it ties with the original and could well be read as
    the newest. Exporting one would publish the demo as its own successor and, since its files are
    the ones about to be overwritten, would empty the demo to copy it onto itself.
    """
    def _requireLatest(self, type):
        for run in self.evaluationRunsRepository.findFiltered(types = [type]):
            if not run.ground_truth.getPath().startswith(self.directory):
                return run

        raise RuntimeError(MISSING_RUN.format(type = type, target = EXPORT_TARGETS[type]))

    """Every file the runs name, once each: two runs may well have scored the same ground truth,
    and a retrieval run searched the index live and names no answers at all"""
    def _attachmentsOf(self, runs):
        attachments = {}
        for run in runs:
            for attachment in (run.ground_truth, run.ground_truth_answers):
                if attachment is not None:
                    attachments[attachment.getId()] = attachment

        return list(attachments.values())

    """Clears what a previous export left, so a file no run names any more stops being committed"""
    def _empty(self):
        directory = self._resolve(self.directory)
        directory.mkdir(parents = True, exist_ok = True)

        for path in directory.iterdir():
            if path.is_file():
                path.unlink()

    """Where a registered file really is, refusing one that is no longer there"""
    def _require(self, attachment):
        source = self._resolve(attachment.getPath())
        if not source.is_file():
            raise RuntimeError(MISSING_FILE.format(attachment = attachment.getId(), path = attachment.getPath()))

        return source

    """Copies one file in under the name it was written as, and answers with where it now lives"""
    def _copy(self, source):
        shutil.copyfile(source, self._resolve(self.directory) / source.name)

        return '{directory}/{name}'.format(directory = self.directory, name = source.name)

    def _write(self, snapshot):
        with gzip.open(self._resolve(self.directory) / SNAPSHOT_NAME, 'wt', encoding = 'utf-8') as file:
            json.dump(snapshot, file)

    """The id is the snapshot's own, which the runs below point at and the load remaps: what a row
    was numbered here says nothing about the database it is read into"""
    def _attachment(self, attachment, paths):
        return {
            'id': attachment.getId(),
            'path': paths[attachment.getId()],
            'type': attachment.getType(),
            'engine': attachment.getEngine(),
            'created': attachment.getCreated().isoformat(),
        }

    def _run(self, run):
        return {
            'type': run.getType(),
            'ground_truth': run.ground_truth_id,
            'ground_truth_answers': run.ground_truth_answers_id,
            'retriever': run.retriever,
            'k': run.k,
            'embedding_model': run.embedding_model,
            'hit_rate': run.hit_rate,
            'mrr': run.mrr,
            'report': run.report,
            'averages': run.getAverages(),
            'created_at': run.created_at.isoformat(),
        }

    def _resolve(self, path):
        return Path(settings.BASE_DIR, path)

"""Reads that snapshot back into a database that has none of it.

Touches nothing but the attachments and the runs: a report is scored already, so no genre has to be
stored and no index has to have been built for one to be read.
"""
class DemoLoad:

    def __init__(self, evaluationRunsRepository, attachmentsRepository, directory = DEMO_DIRECTORY):
        self.evaluationRunsRepository = evaluationRunsRepository
        self.attachmentsRepository = attachmentsRepository
        self.directory = directory

    """Returns how many runs were loaded, and whether they were already there.

    A second run loads nothing rather than a second copy of everything, so this is triggered as
    often as anybody likes and the list of evaluations still reads as one demo.
    """
    def load(self, progress = NULL_PROGRESS):
        if self.attachmentsRepository.hasDemo():
            return [0, True]

        snapshot = self._read()
        attachments = snapshot[ATTACHMENTS_KEY]
        runs = snapshot[RUNS_KEY]

        progress.start(LOADING, len(attachments) + len(runs))

        # All of it or none: attachments loaded without the runs that name them would be a demo
        # already there as far as the next run is concerned, and it would never load the rest.
        with transaction.atomic():
            self._loadRuns(runs, self._loadAttachments(attachments, progress), progress)

        return [len(runs), False]

    """Registers each file and answers with what the snapshot numbered it, for the runs to point at"""
    def _loadAttachments(self, attachments, progress):
        registered = {}

        for attachment in attachments:
            registered[attachment['id']] = self.attachmentsRepository.create(
                path = attachment['path'],
                type = attachment['type'],
                engine = attachment['engine'],
                created = self._moment(attachment['created']),
            )
            progress.advance()

        return registered

    def _loadRuns(self, runs, attachments, progress):
        for run in runs:
            self.evaluationRunsRepository.create(
                type = run['type'],
                groundTruth = attachments[run['ground_truth']],
                groundTruthAnswers = attachments.get(run['ground_truth_answers']),
                retriever = run['retriever'],
                k = run['k'],
                embeddingModel = run['embedding_model'],
                hitRate = run['hit_rate'],
                mrr = run['mrr'],
                report = run['report'],
                averages = run['averages'],
                created = self._moment(run['created_at']),
            )
            progress.advance()

    def _read(self):
        path = Path(settings.BASE_DIR, self.directory, SNAPSHOT_NAME)
        if not path.is_file():
            raise RuntimeError(MISSING_SNAPSHOT.format(path = path))

        with gzip.open(path, 'rt', encoding = 'utf-8') as file:
            return json.load(file)

    """The moment a row was really written, kept so the demo reads as the history it was and a
    ground truth generated later still wins as the latest one"""
    def _moment(self, moment):
        return datetime.fromisoformat(moment)
