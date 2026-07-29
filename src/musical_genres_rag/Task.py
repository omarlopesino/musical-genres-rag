from django.core.cache import cache
from django.db import connections

import logging
import threading

"""How an operation runs away from whoever asked for it.

Every operation here takes minutes and spends paid calls, so none of them is answered by keeping a
connection open until it is over: the caller is handed the task it is followed by, and reads the
outcome off the progress it reports.

A thread, and not a queue: nothing survives a restart of the process, which is as much as running
the work by hand offers, and a real queue is a dependency this does not need yet.
"""

LOCK_KEY = 'lock:{operation}'

# Only a safety net: the lock is let go of as soon as the work is over, and this is what frees it
# when the process holding it dies instead.
LOCK_TTL = 60 * 60

logger = logging.getLogger(__name__)

class BackgroundTasks:

    """Runs the work in a thread of its own, reporting the outcome either way.

    The failure is a whole payload rather than the exception's own words: what went wrong belongs in
    the server's log, where the "info" it answers with sends the reader.
    """
    def spawn(self, work, progress, failure):
        thread = threading.Thread(
            target = self._run,
            args = (work, progress, failure),
            daemon = True,
        )
        thread.start()

        return thread

    def _run(self, work, progress, failure):
        try:
            progress.finish(work(progress))
        except Exception:
            logger.exception('The %s task failed.', progress.operation)
            progress.finish(failure)
        finally:
            # A thread opens a connection of its own, and is the only one that can close it
            connections.close_all()

"""What keeps one operation from being run twice at once.

Two ingests would truncate the index under each other, and a caller that fires and forgets, or an
orchestrator that retries, makes that easy to do by accident.
"""
class OperationLock:

    def __init__(self, operation, store = None):
        self.operation = operation
        self.store = store if store is not None else cache

    """True when it was free and is now ours, false when somebody else got there first"""
    def take(self, task):
        return self.store.add(self._key(), task, LOCK_TTL)

    """Whose it is, as far as anyone can tell: a lock let go of between asking and reading has none"""
    def holder(self):
        return self.store.get(self._key())

    def release(self):
        self.store.delete(self._key())

    def _key(self):
        return LOCK_KEY.format(operation = self.operation)
