from musical_genres_rag.Command import EngineCommand
from musical_genres_rag.models import EvaluationRun
from musical_genres_rag.services import buildGenresRagEvaluationRunner, buildGenresRetrievalEvaluationRunner

"""Which runner scores which half of the pipeline, keyed by the type its runs are stored as"""
RUNNERS = {
    EvaluationRun.Type.RAG: buildGenresRagEvaluationRunner,
    EvaluationRun.Type.RETRIEVAL: buildGenresRetrievalEvaluationRunner,
}


class Command(EngineCommand):
    help = 'Offline local evaluation of ground truth.'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--type',
            choices = list(RUNNERS),
            default = EvaluationRun.Type.RAG,
            help = 'How much of the pipeline to score. "retrieval" queries the index live, costs no LLM call '
                   'and needs no answers file, so it measures an engine as often as it changes.',
        )

    def handle(self, *args, **options):
        run = RUNNERS[options['type']](options['engine']).execute()
        self.stdout.write(self.style.SUCCESS('Finished {type} evaluation of {engine}, stored as run {id}.'.format(
            type = options['type'],
            engine = options['engine'],
            id = run.id,
        )))
