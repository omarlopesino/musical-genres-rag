from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildDemoLoad


class Command(BaseCommand):
    help = 'Loads the committed demo evaluations, so the dashboard has something to show without a paid run.'

    def handle(self, *args, **options):
        [loaded, alreadyThere] = buildDemoLoad().load()

        if alreadyThere:
            return self.stdout.write('The demo data is already loaded, nothing to do.')

        self.stdout.write(self.style.SUCCESS('Demo data loaded, {loaded} evaluations to read.'.format(loaded = loaded)))
