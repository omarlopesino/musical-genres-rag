from django.db import migrations

# The index name is not free: PostgresSearchEngine derives it as <table>_text and
# names it explicitly in the search query, because the bare "content <@> 'text'"
# form only resolves the index when the query is inlined.
INDEX_NAME = 'genre_index_text'


class Migration(migrations.Migration):

    dependencies = [
        ('musical_genres_rag', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql = 'CREATE EXTENSION IF NOT EXISTS pg_textsearch;',
            reverse_sql = 'DROP EXTENSION IF EXISTS pg_textsearch;',
        ),
        migrations.RunSQL(
            sql = "CREATE INDEX {name} ON genre_index USING bm25(content) WITH (text_config='english');".format(name = INDEX_NAME),
            reverse_sql = 'DROP INDEX IF EXISTS {name};'.format(name = INDEX_NAME),
        ),
    ]
