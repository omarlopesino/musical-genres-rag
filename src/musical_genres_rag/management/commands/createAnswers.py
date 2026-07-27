from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildGroundTruthAnswers

DEFAULT_OUTPUT = './tests/ground_truth/ground_truth.csv'


class Command(BaseCommand):
    help = 'Create ground truth answers via RAG.'

    def handle(self, *args, **options):
        buildGroundTruthAnswers().generate()
        self.stdout.write(self.style.SUCCESS('Finished ground truth answers generation.'))
