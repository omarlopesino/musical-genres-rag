from django.db import migrations, models

# Where a conversation id comes from. A composite primary key cannot carry an AutoField, and the
# user's row and the judge's row have to be inserted under the same id, so the id is drawn here
# and handed to both rather than assigned by the table.
SEQUENCE_NAME = 'feedback_id_seq'


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0008_evaluationrun_averages'),
    ]

    operations = [
        migrations.RunSQL(
            sql = 'CREATE SEQUENCE {name};'.format(name = SEQUENCE_NAME),
            reverse_sql = 'DROP SEQUENCE IF EXISTS {name};'.format(name = SEQUENCE_NAME),
        ),
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('pk', models.CompositePrimaryKey('id', 'source', blank=True, editable=False, primary_key=True, serialize=False)),
                ('id', models.BigIntegerField()),
                ('source', models.CharField(choices=[('user', 'User'), ('llm', 'Llm')], max_length=16)),
                ('question', models.CharField(max_length=255)),
                ('answer', models.JSONField()),
                ('score', models.FloatField(null=True)),
                ('judgement', models.TextField(null=True)),
                ('relevance', models.FloatField(null=True)),
            ],
            options={
                'db_table': 'feedback',
            },
        ),
    ]
