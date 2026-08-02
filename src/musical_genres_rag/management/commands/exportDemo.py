from django.core.management.base import BaseCommand

from musical_genres_rag.services import buildDemoExport


class Command(BaseCommand):
    help = 'Exports the latest evaluation of each kind into the committed demo data.'

    def handle(self, *args, **options):
        [runs, attachments] = buildDemoExport().export()
        self.stdout.write(self.style.SUCCESS('Exported {runs} runs and {attachments} files. Commit ./data/demo to publish them.'.format(
            runs = len(runs),
            attachments = len(attachments),
        )))
