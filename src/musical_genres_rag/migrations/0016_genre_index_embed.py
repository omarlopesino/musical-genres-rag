from django.db import migrations, models
from musical_genres_rag.Vectorizer import VECTOR_DIMENSIONS
from pgvector.django import VectorExtension, VectorField

"""The index the vector engines search through.

Created by hand, as the bm25 one is: pgvector's own HnswIndex is a django.contrib.postgres index,
and a model declaring one fails the system checks unless that app joins INSTALLED_APPS, which this
project keeps to itself alone. Unlike the bm25 index nothing names this one back — the planner
picks it up from the ordering by distance — so the name is only ever read here.
"""
INDEX_NAME = 'genre_index_embed'

# pgvector defines no default operator class for hnsw, so the one the distance operator belongs to
# has to be named: cosine, which is what the vectorizer's unit length makes the dot product too.
OPERATOR_CLASS = 'vector_cosine_ops'


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0015_conversation_metrics'),
    ]

    operations = [
        # First: the column below cannot be added while its type does not exist yet
        VectorExtension(),
        migrations.AlterField(
            model_name = 'genreindex',
            name = 'content',
            field = models.TextField(null = True),
        ),
        migrations.AddField(
            model_name = 'genreindex',
            name = 'embed',
            field = VectorField(dimensions = VECTOR_DIMENSIONS, null = True),
        ),
        migrations.RunSQL(
            sql = 'CREATE INDEX {name} ON genre_index USING hnsw (embed {operator});'.format(
                name = INDEX_NAME,
                operator = OPERATOR_CLASS,
            ),
            reverse_sql = 'DROP INDEX IF EXISTS {name};'.format(name = INDEX_NAME),
        ),
    ]
