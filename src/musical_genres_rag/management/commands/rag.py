from musical_genres_rag.Command import EngineCommand
from musical_genres_rag.Rag import EmptyRagResponse, EmptyRetrievalError
from musical_genres_rag.services import buildGenresRag

DEFAULT_QUESTION = 'Which genre started alongside rock and roll before becoming more commercially oriented?'


class Command(EngineCommand):
    help = 'Answers a question about musical genres from the indexed context.'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            'question',
            nargs = '?',
            default = DEFAULT_QUESTION,
            help = 'The question to ask. Defaults to a sample question.',
        )

    def handle(self, *args, **options):
        try:
            response = buildGenresRag(options['engine']).query(options['question'])
        # Nothing retrieved is an answer of its own, not a crash: reply as the LLM would have
        except EmptyRetrievalError as error:
            response = EmptyRagResponse(error.getQuery(), error.getDuration())
        self.stdout.write(response.toJson())
