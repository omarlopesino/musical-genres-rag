from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildEvaluationRunner


class Command(BaseCommand):
    help = 'Offline local evaluation of ground truth.'

    def handle(self, *args, **options):
        buildEvaluationRunner().execute()
        self.stdout.write(self.style.SUCCESS('Finished evaluation.'))
