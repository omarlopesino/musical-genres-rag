from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildEvaluationRunner

DEFAULT_OUTPUT = './tests/ground_truth/ground_truth.csv'


class Command(BaseCommand):
    help = 'Offline local evaluation of ground truth.'

    def handle(self, *args, **options):
        buildEvaluationRunner().execute()
        self.stdout.write(self.style.SUCCESS('Finished evaluationGround truth written to {path}.'))
