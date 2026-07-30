import django.db.models.deletion
from django.db import migrations, models

"""Moves what was asked and what came back off the feedback and onto a conversation of its own.

Written by hand rather than generated, for the order of it. The sequence 0009 created is dropped
before feedback.id becomes an identity column, because Postgres would name that column's own
sequence "feedback_id_seq" too and the two cannot both exist; and the identity is then restarted
above the ids already stored, or it would begin at 1 and collide with them.

Nothing is thrown away: every feedback row already stored becomes a conversation carrying its
question, its answer and the moment it was given, and goes on pointing at it.
"""

# The sequence 0009 created, read here for the last time
SEQUENCE_NAME = 'feedback_id_seq'

# Where the identity of feedback.id picks up from, so a new row is never given one already taken
RESTART_IDENTITY = """
SELECT setval(
    pg_get_serial_sequence('feedback', 'id'),
    COALESCE((SELECT MAX(id) FROM feedback), 0) + 1,
    false
);
"""


def registerExistingConversations(apps, schema_editor):
    Conversation = apps.get_model('musical_genres_rag', 'Conversation')
    Feedback = apps.get_model('musical_genres_rag', 'Feedback')

    for feedback in Feedback.objects.all():
        conversation = Conversation.objects.create(
            question = feedback.question,
            answer = feedback.answer,
        )
        # created is auto_now_add, so the moment the answer was really given has to be put back
        Conversation.objects.filter(pk = conversation.pk).update(created = feedback.created)
        Feedback.objects.filter(pk = feedback.pk).update(conversation = conversation)


def restoreFeedbackAnswers(apps, schema_editor):
    Feedback = apps.get_model('musical_genres_rag', 'Feedback')

    for feedback in Feedback.objects.select_related('conversation'):
        Feedback.objects.filter(pk = feedback.pk).update(
            question = feedback.conversation.question,
            answer = feedback.conversation.answer,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0011_judge_batch'),
    ]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('question', models.CharField(max_length=255)),
                ('answer', models.JSONField()),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'conversation',
            },
        ),
        migrations.AddField(
            model_name='feedback',
            name='conversation',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='feedback', to='musical_genres_rag.conversation'),
        ),
        migrations.RunPython(registerExistingConversations, restoreFeedbackAnswers),
        migrations.AlterField(
            model_name='feedback',
            name='conversation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='feedback', to='musical_genres_rag.conversation'),
        ),
        migrations.RemoveField(
            model_name='feedback',
            name='question',
        ),
        migrations.RemoveField(
            model_name='feedback',
            name='answer',
        ),
        # Out of the way before the column below claims the same name for its identity
        migrations.RunSQL(
            sql = 'DROP SEQUENCE IF EXISTS {name};'.format(name = SEQUENCE_NAME),
            reverse_sql = 'CREATE SEQUENCE IF NOT EXISTS {name};'.format(name = SEQUENCE_NAME),
        ),
        # Dropping the composite key is a change of state and nothing else: the constraint itself is
        # on the table, and a second primary key cannot be added underneath the one already there.
        migrations.RunSQL(
            sql = 'ALTER TABLE feedback DROP CONSTRAINT feedback_pkey;',
            reverse_sql = 'ALTER TABLE feedback ADD CONSTRAINT feedback_pkey PRIMARY KEY (id, source);',
        ),
        migrations.RemoveField(
            model_name='feedback',
            name='pk',
        ),
        migrations.AlterField(
            model_name='feedback',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
        migrations.RunSQL(
            sql = RESTART_IDENTITY,
            reverse_sql = migrations.RunSQL.noop,
        ),
        migrations.AddConstraint(
            model_name='feedback',
            constraint=models.UniqueConstraint(fields=('conversation', 'source'), name='feedback_conversation_source'),
        ),
    ]
