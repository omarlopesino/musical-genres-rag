from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildGenresIndex


class Command(BaseCommand):
    help = 'Rebuilds the search index from every stored genre.'

    def handle(self, *args, **options):
        buildGenresIndex().index()
        self.stdout.write(self.style.SUCCESS('Index rebuilt.'))
