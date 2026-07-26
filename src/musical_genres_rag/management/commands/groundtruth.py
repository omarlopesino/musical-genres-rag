from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildGenresGroundTruth

DEFAULT_OUTPUT = './tests/ground_truth/ground_truth.csv'


class Command(BaseCommand):
    help = 'Generates the ground truth question set, one row per generated question.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default = DEFAULT_OUTPUT,
            help = 'Where to write the CSV. Defaults to {path}.'.format(path = DEFAULT_OUTPUT),
        )

    def handle(self, *args, **options):
        buildGenresGroundTruth().generate(options['output'])
        self.stdout.write(self.style.SUCCESS('Ground truth written to {path}.'.format(path = options['output'])))
