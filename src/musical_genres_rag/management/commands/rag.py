from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildGenresRag

DEFAULT_QUESTION = 'Which genre started alongside rock and roll before becoming more commercially oriented?'


class Command(BaseCommand):
    help = 'Answers a question about musical genres from the indexed context.'

    def add_arguments(self, parser):
        parser.add_argument(
            'question',
            nargs = '?',
            default = DEFAULT_QUESTION,
            help = 'The question to ask. Defaults to a sample question.',
        )

    def handle(self, *args, **options):
        response = buildGenresRag().query(options['question'])
        self.stdout.write(response.toJson())
