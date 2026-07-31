from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildVectorizerDownload


class Command(BaseCommand):
    help = 'Downloads the weights the vector engines embed with, and does nothing if they are here.'

    def handle(self, *args, **options):
        for path, saved in buildVectorizerDownload().download().items():
            self.stdout.write(self.style.SUCCESS('{verb} {path}'.format(
                verb = 'Saved' if saved else 'Already at',
                path = path,
            )))
