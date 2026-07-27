from django.db import models

"""Shared shape of every indexable entity: an id, a name and a description"""
class EntityModel(models.Model):

    name = models.CharField(max_length = 255, null = True)
    description = models.TextField(null = True)

    class Meta:
        abstract = True

    def getId(self):
        return self.id

    def getName(self):
        return self.name

    def getDescription(self):
        return self.description

    """The properties a Renderer walks, in the order they must be rendered"""
    def getProperties(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
        }

    def __str__(self):
        return self.name or ''

class Genre(EntityModel):

    parents = models.ManyToManyField(
        'self',
        through = 'GenreHierarchy',
        through_fields = ('genre', 'parent'),
        symmetrical = False,
        related_name = 'children',
    )

    class Meta:
        db_table = 'genre'

    """Relations come after the scalars, matching the order the renderer has always emitted"""
    def getProperties(self):
        properties = super().getProperties()
        properties['parents'] = list(self.parents.all())
        properties['instruments'] = list(self.instruments.all())
        return properties

class Instrument(EntityModel):

    genres = models.ManyToManyField(
        Genre,
        through = 'InstrumentGenres',
        through_fields = ('instrument', 'genre'),
        related_name = 'instruments',
    )

    class Meta:
        db_table = 'instrument'

class GenreHierarchy(models.Model):

    pk = models.CompositePrimaryKey('genre', 'parent')
    genre = models.ForeignKey(Genre, on_delete = models.CASCADE, db_column = 'genre', related_name = '+')
    parent = models.ForeignKey(Genre, on_delete = models.CASCADE, db_column = 'parent', related_name = '+')

    class Meta:
        db_table = 'genre_hierarchy'

class InstrumentGenres(models.Model):

    pk = models.CompositePrimaryKey('instrument', 'genre')
    instrument = models.ForeignKey(Instrument, on_delete = models.CASCADE, db_column = 'instrument', related_name = '+')
    genre = models.ForeignKey(Genre, on_delete = models.CASCADE, db_column = 'genre', related_name = '+')

    class Meta:
        db_table = 'instrument_genres'

"""Search documents, keyed by the id of the entity they render.

Deliberately not a foreign key: SearchEngine writes the entity id itself and is
written to be generic over whichever table it is pointed at.
"""
class GenreIndex(models.Model):

    id = models.BigAutoField(primary_key = True)
    content = models.TextField()

    class Meta:
        db_table = 'genre_index'

"""Evaluation run results"""
class EvaluationRun(models.Model):

    created_at = models.DateTimeField(auto_now_add = True)
    retriever = models.CharField(max_length = 64)
    k = models.PositiveSmallIntegerField()
    embedding_model = models.CharField(max_length = 128)
    hit_rate = models.FloatField(null = True)
    mrr = models.FloatField(null = True)
    report = models.JSONField()

    class Meta:
        db_table = 'evaluation_run'
