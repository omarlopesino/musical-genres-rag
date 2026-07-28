from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildGroundTruthAnswers


class Command(BaseCommand):
    help = 'Create ground truth answers via RAG.'

    def handle(self, *args, **options):
        attachment = buildGroundTruthAnswers().generate()
        self.stdout.write(self.style.SUCCESS('Ground truth answers written to {path}.'.format(path = attachment.getPath())))
