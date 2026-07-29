from datetime import datetime, timezone

from django.core.cache import cache

import threading

"""Where a long operation is followed from, by whoever is not the one running it.

An operation that takes minutes says nothing until it returns, which is enough for whoever waits in
front of it and nothing an orchestrator can draw a bar from. So every one of them takes a reporter,
and the one they take by default reports nowhere: a run nobody is watching pays nothing for this,
and no class below has to know which kind of run it is in.

What is reported lives in the cache, because the process that reads it is never the one that wrote it.
"""

PROGRESS_KEY = 'progress:{task}'

# Long enough for a finished run to still be read by whatever polls it, short enough that a task id
# nobody asks about again stops taking room
PROGRESS_TTL = 60 * 60

QUEUED = 'queued'

class Progress:

    # What is being followed, for whoever reports it or writes it down
    operation = None

    """What is about to be counted, and how many of it there are"""
    def start(self, phase, total = None):
        pass

    """The same run, now spending its time on something else"""
    def enter(self, phase):
        pass

    """One more of them done. Returns how many that makes"""
    def advance(self, amount = 1):
        return 0

    """The end of it, successful or not: the result carries its own "success" and "info" either way"""
    def finish(self, result):
        pass

# Reports nowhere, and is shared because it holds nothing
NULL_PROGRESS = Progress()

"""Reports into the cache, one document per task, rewritten on every call.

Counted under a lock: an evaluation scores MAX_CONCURRENCY cases at once, so advance() is called
from several threads at a time.
"""
class CacheProgress(Progress):

    def __init__(self, task, operation, store = None):
        self.task = task
        self.operation = operation
        self.store = store if store is not None else cache
        self.lock = threading.Lock()
        self.phase = QUEUED
        self.current = 0
        self.total = None
        self.startedAt = self._now()
        self._write()

    def start(self, phase, total = None):
        with self.lock:
            self.phase = phase
            self.total = total
            self.current = 0
            self._write()

    def enter(self, phase):
        with self.lock:
            self.phase = phase
            self._write()

    def advance(self, amount = 1):
        with self.lock:
            self.current = self.current + amount
            self._write()
            return self.current

    def finish(self, result):
        with self.lock:
            self._write(
                done = True,
                success = result['success'],
                info = result['info'],
                result = result,
            )

    def _write(self, **outcome):
        self.store.set(PROGRESS_KEY.format(task = self.task), self._document(**outcome), PROGRESS_TTL)

    def _document(self, **outcome):
        return {
            'task_id': self.task,
            'operation': self.operation,
            'phase': self.phase,
            'current': self.current,
            'total': self.total,
            'percent': self._percent(),
            'started_at': self.startedAt,
            'updated_at': self._now(),
            'done': False,
            'success': None,
            'info': None,
            'result': None,
            **outcome,
        }

    """Left unanswered while nothing says how much there is to do, rather than answered with a zero
    that reads as no progress at all"""
    def _percent(self):
        if not self.total:
            return None

        return round(self.current * 100 / self.total, 1)

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

"""What was last reported for a task, or nothing at all if no such task was ever started"""
def readProgress(task, store = None):
    store = store if store is not None else cache
    return store.get(PROGRESS_KEY.format(task = task))
