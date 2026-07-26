from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import CaptureQueriesContext

from musical_genres_rag.Renderer import EntityRenderer
from musical_genres_rag.services import buildGenresRepository


class Command(BaseCommand):
    help = 'Inspection helpers for the genre pipeline.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            default = 'renderers',
            choices = ['renderers', 'genres', 'queries'],
            help = 'renderers: rendered context per genre. genres: entity summary. queries: query count for a full load.',
        )

    def handle(self, *args, **options):
        getattr(self, '_' + options['mode'])(buildGenresRepository())

    """Prints what the LLM and the indexer actually see, one block per genre"""
    def _renderers(self, repository):
        for genre in sorted(repository.loadMultiple(), key = lambda genre: genre.getId()):
            self.stdout.write('===== genre {id} ====='.format(id = genre.getId()))
            self.stdout.write(EntityRenderer(genre).render())

    def _genres(self, repository):
        for genre in repository.loadMultiple():
            self.stdout.write('{id}: {name}'.format(id = genre.getId(), name = genre.getName()))
            self.stdout.write('  parents: {names}'.format(names = [parent.getName() for parent in genre.parents.all()]))
            self.stdout.write('  instruments: {names}'.format(names = [instrument.getName() for instrument in genre.instruments.all()]))

    """Counts the queries a full load costs, which prefetch_related is meant to keep flat"""
    def _queries(self, repository):
        with CaptureQueriesContext(connection) as queries:
            genres = repository.loadMultiple()
            for genre in genres:
                EntityRenderer(genre).render()

        self.stdout.write('{count} queries for {genres} genres.'.format(count = len(queries), genres = len(genres)))
