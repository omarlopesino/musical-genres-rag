import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0004_alter_evaluationrun_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attachment',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('path', models.CharField(max_length=512)),
                ('type', models.CharField(choices=[('ground_truth', 'Ground Truth'), ('ground_truth_answers', 'Ground Truth Answers')], max_length=32)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('engine', models.CharField(max_length=64, null=True)),
            ],
            options={
                'db_table': 'attachment',
                'indexes': [models.Index(fields=['type', '-created'], name='attachment_type_created')],
            },
        ),
        # evaluation_run has never been written to, so the one-off default only serves the column
        # rewrite and is dropped again right after it.
        migrations.AddField(
            model_name='evaluationrun',
            name='ground_truth',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, related_name='evaluation_runs', to='musical_genres_rag.attachment'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='evaluationrun',
            name='ground_truth_answers',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='musical_genres_rag.attachment'),
        ),
    ]
