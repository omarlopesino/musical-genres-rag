from django.core.management.base import BaseCommand

from musical_genres_rag.Sample import DEFAULT_CONVERSATIONS, DEFAULT_FEEDBACK, DEFAULT_SECONDS
from musical_genres_rag.services import buildTrafficSampler


class Command(BaseCommand):
    help = 'Writes artificial conversations and feedback, so the dashboard has traffic to draw.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--seconds',
            type = int,
            default = DEFAULT_SECONDS,
            help = 'Over how long to spread them. The run takes this long on purpose.',
        )
        parser.add_argument(
            '--conversations',
            type = int,
            default = DEFAULT_CONVERSATIONS,
            help = 'How many conversations to write.',
        )
        parser.add_argument(
            '--feedback',
            type = int,
            default = DEFAULT_FEEDBACK,
            help = 'Out of a hundred, how many of them somebody rated.',
        )

    def handle(self, *args, **options):
        [batch, conversations, rated] = buildTrafficSampler().sample(
            seconds = options['seconds'],
            conversations = options['conversations'],
            feedback = options['feedback'],
        )

        self.stdout.write(self.style.SUCCESS('Sampled {conversations} conversations, {rated} of them rated as batch {batch}.'.format(
            conversations = conversations,
            rated = rated,
            batch = batch.getId(),
        )))
