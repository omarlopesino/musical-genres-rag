from musical_genres_rag.Command import EngineCommand
from musical_genres_rag.services import buildGenresIndex


class Command(EngineCommand):
    help = 'Rebuilds the search index from every stored genre.'

    def handle(self, *args, **options):
        buildGenresIndex(options['engine']).index()
        self.stdout.write(self.style.SUCCESS('Index rebuilt for {engine}.'.format(engine = options['engine'])))
