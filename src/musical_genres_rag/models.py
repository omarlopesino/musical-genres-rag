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

"""A generated file on disk, kept addressable so an evaluation can name the exact inputs it ran on"""
class Attachment(models.Model):

    class Type(models.TextChoices):
        GROUND_TRUTH = 'ground_truth'
        GROUND_TRUTH_ANSWERS = 'ground_truth_answers'

    id = models.BigAutoField(primary_key = True)
    path = models.CharField(max_length = 512)
    type = models.CharField(max_length = 32, choices = Type.choices)
    created = models.DateTimeField(auto_now_add = True)
    # Ground truth questions are generated straight from the repository, with no index involved
    engine = models.CharField(max_length = 64, null = True)

    class Meta:
        db_table = 'attachment'
        indexes = [models.Index(fields = ['type', '-created'], name = 'attachment_type_created')]

    def getId(self):
        return self.id

    def getPath(self):
        return self.path

    def getType(self):
        return self.type

    def getCreated(self):
        return self.created

    def getEngine(self):
        return self.engine

    def __str__(self):
        return self.path

"""Evaluation run results"""
class EvaluationRun(models.Model):

    """How much of the pipeline a run scored, so runs are only ever compared against their own kind"""
    class Type(models.TextChoices):
        RETRIEVAL = 'retrieval'
        RAG = 'rag'

    id = models.BigAutoField(primary_key = True)
    created_at = models.DateTimeField(auto_now_add = True)
    # Every run stored so far scored generation too, so existing rows are RAG runs
    type = models.CharField(max_length = 32, choices = Type.choices, default = Type.RAG)
    ground_truth = models.ForeignKey(Attachment, on_delete = models.PROTECT, related_name = 'evaluation_runs')
    ground_truth_answers = models.ForeignKey(Attachment, on_delete = models.PROTECT, related_name = '+', null = True)
    retriever = models.CharField(max_length = 64)
    k = models.PositiveSmallIntegerField()
    embedding_model = models.CharField(max_length = 128)
    hit_rate = models.FloatField(null = True)
    mrr = models.FloatField(null = True)
    report = models.JSONField()
    # pydantic-evals aggregates every case but serializes only the cases themselves, so the
    # aggregate is stored here rather than averaged again by whoever reads the run back
    averages = models.JSONField(null = True)

    class Meta:
        db_table = 'evaluation_run'
        indexes = [models.Index(fields = ['type', '-created_at'], name = 'evaluation_run_type_created')]

    def getType(self):
        return self.type

    def getAverages(self):
        return self.averages

"""One run of the judge, so the answers it read are read back together.

A batch is what the run it belongs to is linked as, exactly as an evaluation run is linked as its
own report: nothing is stored on it that the rows naming it do not already say.
"""
class JudgeBatch(models.Model):

    id = models.BigAutoField(primary_key = True)
    created = models.DateTimeField(auto_now_add = True)

    class Meta:
        db_table = 'judge_batch'

    def getId(self):
        return self.id

    def getCreated(self):
        return self.created

    def __str__(self):
        return str(self.id)

"""A question put to the RAG and what came back, recorded whether anybody rated it or not.

The answer is the whole RagResponse.toDict(), the rendered context included, so a judge scores
it against what the LLM was actually given rather than against the index as it stands today.
"""
class Conversation(models.Model):

    id = models.BigAutoField(primary_key = True)
    question = models.CharField(max_length = 255)
    answer = models.JSONField()
    created = models.DateTimeField(auto_now_add = True)

    class Meta:
        db_table = 'conversation'

    def getId(self):
        return self.id

    def getQuestion(self):
        return self.question

    def getAnswer(self):
        return self.answer

    def getCreated(self):
        return self.created

    """What was made of this answer, or nothing where nobody has made anything of it yet.

    At most one per source, and only a user's is ever written today. Read off the set as it was
    prefetched rather than asked for again, so a page listing conversations stays one query.
    """
    def getFeedback(self):
        return next(iter(self.feedback.all()), None)

    def __str__(self):
        return self.question

"""What was made of one answer, by the person who asked it or by a judge reading it back.

Both verdicts on the same answer are the same conversation, so they point at the one it was
given in and are told apart by their source.
"""
class Feedback(models.Model):

    class Source(models.TextChoices):
        USER = 'user'
        LLM = 'llm'

    id = models.BigAutoField(primary_key = True)
    conversation = models.ForeignKey(Conversation, on_delete = models.PROTECT, related_name = 'feedback')
    source = models.CharField(max_length = 16, choices = Source.choices)
    # What the thumbs said, as 1 or 0
    score = models.FloatField(null = True)
    # What a judge made of the answer, reading it back against the context it was written from
    judgement = models.TextField(null = True)
    relevance = models.FloatField(null = True)
    # What the judging call spent. Null until a judge has read the answer, and on a thumb, which
    # somebody pressed themselves and which therefore cost nothing.
    input_tokens = models.IntegerField(null = True)
    output_tokens = models.IntegerField(null = True)
    cost = models.FloatField(null = True)
    # Which run judged it, so a run links to the answers it read. Null until one has: a foreign key
    # may not point at a composite key, but a composite key may hold one, and this is that direction.
    judge_batch = models.ForeignKey(JudgeBatch, on_delete = models.PROTECT, related_name = 'judgements', null = True)
    created = models.DateTimeField(auto_now_add = True)

    class Meta:
        db_table = 'feedback'
        # One verdict per source per conversation: pressing the other thumb corrects the one stored
        constraints = [models.UniqueConstraint(fields = ['conversation', 'source'], name = 'feedback_conversation_source')]
        indexes = [models.Index(fields = ['-created', '-id'], name = 'feedback_created')]

    def getId(self):
        return self.id

    def getConversation(self):
        return self.conversation

    def getSource(self):
        return self.source

    def getScore(self):
        return self.score

    def getJudgement(self):
        return self.judgement

    def getRelevance(self):
        return self.relevance

    def getInputTokens(self):
        return self.input_tokens

    def getOutputTokens(self):
        return self.output_tokens

    def getCost(self):
        return self.cost

    def getJudgeBatch(self):
        return self.judge_batch

    def getCreated(self):
        return self.created

    # Named by the conversation it is unique under. That one is named by its id and not by its
    # question: reading the question back is a second query, and a row says what it is without
    # going to look.
    def __str__(self):
        return 'feedback on conversation {conversation}'.format(conversation = self.conversation_id)
