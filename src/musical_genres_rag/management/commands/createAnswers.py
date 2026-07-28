from musical_genres_rag.Command import EngineCommand
from musical_genres_rag.services import buildGroundTruthAnswers


class Command(EngineCommand):
    help = 'Create ground truth answers via RAG.'

    def handle(self, *args, **options):
        attachment = buildGroundTruthAnswers(options['engine']).generate()
        self.stdout.write(self.style.SUCCESS('Ground truth answers written to {path}.'.format(path = attachment.getPath())))
