from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildGenresGroundTruth


class Command(BaseCommand):
    help = 'Generates the ground truth question set, one row per generated question.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default = None,
            help = 'Where to write the CSV. Defaults to a timestamped file under ./tests/ground_truth.',
        )

    def handle(self, *args, **options):
        [attachment, questions] = buildGenresGroundTruth().generate(options['output'])
        self.stdout.write(self.style.SUCCESS('Ground truth written to {path}, {questions} questions generated.'.format(
            path = attachment.getPath(),
            questions = questions,
        )))
