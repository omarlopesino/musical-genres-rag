from django.core.management.base import BaseCommand

from musical_genres_rag.services import DEFAULT_ENGINE, ENGINES

"""A command that acts through a search engine, and so has to be told which one.

An engine is named the same way everywhere: on the command line, in Attachment.engine and
in EvaluationRun.retriever. That way what one engine generated is only ever read back by
that same engine, and two engines are only ever compared as two rows.
"""
class EngineCommand(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--engine',
            choices = list(ENGINES),
            default = DEFAULT_ENGINE,
            help = 'Which search engine to run through. Defaults to "{default}".'.format(default = DEFAULT_ENGINE),
        )
