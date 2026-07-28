from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.utils import timezone

# Frozen copies of the Evaluation constants: a migration has to keep describing the world as it was
# when it was written, whatever those constants become later.
GROUND_TRUTH_DIRECTORY = './tests/ground_truth'
TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'

# The files generated before attachments existed, and the name each one takes now. Renaming them
# rather than regenerating keeps the evaluation history without spending another LLM run.
LEGACY_FILES = [
    ('ground_truth.csv', 'ground_truth', 'ground_truth', None),
    ('responses.json', 'ground_truth_answers', 'ground_truth_answers', 'postgres_text'),
]


def resolvePath(relativePath):
    return Path(settings.BASE_DIR) / relativePath.removeprefix('./')


def buildRelativePath(name):
    return '{directory}/{name}'.format(directory = GROUND_TRUTH_DIRECTORY, name = name)


def registerExistingAttachments(apps, schema_editor):
    Attachment = apps.get_model('musical_genres_rag', 'Attachment')

    for legacyName, prefix, type, engine in LEGACY_FILES:
        legacyPath = buildRelativePath(legacyName)
        legacyFile = resolvePath(legacyPath)
        if not legacyFile.exists():
            continue

        written = datetime.fromtimestamp(legacyFile.stat().st_mtime)
        path = buildRelativePath('{prefix}_{timestamp}{suffix}'.format(
            prefix = prefix,
            timestamp = written.strftime(TIMESTAMP_FORMAT),
            suffix = legacyFile.suffix,
        ))

        legacyFile.rename(resolvePath(path))
        attachment = Attachment.objects.create(path = path, type = type, engine = engine)
        # created is auto_now_add, so the moment the file was actually written has to be put back
        Attachment.objects.filter(pk = attachment.pk).update(created = timezone.make_aware(written))


def restoreLegacyAttachments(apps, schema_editor):
    Attachment = apps.get_model('musical_genres_rag', 'Attachment')

    for legacyName, prefix, type, engine in LEGACY_FILES:
        attachment = Attachment.objects.filter(type = type).order_by('created', 'id').first()
        if attachment is None:
            continue

        attachmentFile = resolvePath(attachment.path)
        if attachmentFile.exists():
            attachmentFile.rename(resolvePath(buildRelativePath(legacyName)))
        attachment.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0005_attachment'),
    ]

    operations = [
        migrations.RunPython(registerExistingAttachments, restoreLegacyAttachments),
    ]
