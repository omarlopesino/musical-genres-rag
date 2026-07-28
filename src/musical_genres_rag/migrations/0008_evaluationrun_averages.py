from django.db import migrations, models


# The aggregate is computed while the evaluation runs and cannot be recovered from a report that
# never carried it, so the runs stored before this column existed are cleared and evaluated again.
# Both evaluations replay files that are already on disk, so regenerating them costs no LLM call.
def clearRunsWithoutAverages(apps, schema_editor):
    apps.get_model('musical_genres_rag', 'EvaluationRun').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0007_evaluationrun_type_and_more'),
    ]

    operations = [
        migrations.RunPython(clearRunsWithoutAverages, migrations.RunPython.noop),
        migrations.AddField(
            model_name='evaluationrun',
            name='averages',
            field=models.JSONField(null=True),
        ),
    ]
