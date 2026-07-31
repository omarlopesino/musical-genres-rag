from django.db.models import Avg, Count, Sum

from musical_genres_rag.models import Attachment, Conversation, EvaluationRun, Feedback, Genre, Instrument, JudgeBatch

class RepositoryBase():

    def __init__(self, model, prefetch = ()):
        self.model = model
        self.prefetch = prefetch

    def load(self, id):
        rows = self.loadMultiple([id])
        return rows[0] if rows else None

    """Loads the given ids in one query, keeping their order, or every entity when none are given"""
    def loadMultiple(self, ids = None):
        entities = self.model.objects.prefetch_related(*self.prefetch)

        if not ids:
            return list(entities)

        # The index returns ids ranked by relevance and "id IN (...)" does not preserve
        # that order, so restore it here rather than let the ranking dissolve in the prompt.
        byId = entities.in_bulk(ids)

        return [byId[id] for id in ids if id in byId]

class InstrumentsRepository(RepositoryBase):

    def __init__(self):
        super().__init__(Instrument)

class AttachmentsRepository(RepositoryBase):

    def __init__(self):
        super().__init__(Attachment)

    def getLatestGroundTruth(self):
        return self._getLatest(Attachment.Type.GROUND_TRUTH)

    """Answers are only comparable within the engine that produced them, so the engine picks the file"""
    def getLatestGroundTruthResponses(self, engine):
        return self._getLatest(Attachment.Type.GROUND_TRUTH_ANSWERS, engine)

    def create(self, path, type, engine = None):
        return self.model.objects.create(path = path, type = type, engine = engine)

    """Ties break on id so two files written inside the same second still order deterministically"""
    def _getLatest(self, type, engine = None):
        attachments = self.model.objects.filter(type = type)
        if engine is not None:
            attachments = attachments.filter(engine = engine)
        return attachments.order_by('-created', '-id').first()

class EvaluationRunsRepository(RepositoryBase):

    def __init__(self):
        super().__init__(EvaluationRun)

    """The attachments are kept as relations so a run always names the exact files it scored"""
    def create(self, type, groundTruth, groundTruthAnswers, retriever, k, embeddingModel, hitRate, mrr, report, averages):
        return self.model.objects.create(
            type = type,
            ground_truth = groundTruth,
            ground_truth_answers = groundTruthAnswers,
            retriever = retriever,
            k = k,
            embedding_model = embeddingModel,
            hit_rate = hitRate,
            mrr = mrr,
            report = report,
            averages = averages,
        )

    """The runs a filter asks for. An empty filter is no filter, so the page opens on everything"""
    def findFiltered(self, types = None, embeddingModels = None, since = None, until = None):
        runs = self.model.objects.all()

        if types:
            runs = runs.filter(type__in = types)
        if embeddingModels:
            runs = runs.filter(embedding_model__in = embeddingModels)
        if since is not None:
            runs = runs.filter(created_at__date__gte = since)
        if until is not None:
            runs = runs.filter(created_at__date__lte = until)

        return list(runs.order_by('-created_at'))

    """The filter options come from what is actually stored, so a filter can never empty the list by itself"""
    def getTypes(self):
        return self._getDistinct('type')

    def getEmbeddingModels(self):
        return self._getDistinct('embedding_model')

    def _getDistinct(self, field):
        return list(self.model.objects.values_list(field, flat = True).distinct().order_by(field))

class ConversationsRepository(RepositoryBase):

    def __init__(self):
        # Each is listed beside whatever was made of it, so the feedback comes along rather than
        # being asked for one conversation at a time
        super().__init__(Conversation, prefetch = ('feedback',))

    """Every answer given is one of these, whether anybody went on to rate it or not"""
    def create(self, question, answer):
        return self.model.objects.create(question = question, answer = answer)

    """Every conversation, newest first. Ties break on id so two inside the same second still order"""
    def findLatest(self):
        return list(self.model.objects.prefetch_related(*self.prefetch).order_by('-created', '-id'))

class FeedbackRepository(RepositoryBase):

    def __init__(self):
        super().__init__(Feedback)

    """Stores what a source made of one answer.

    Written as an update where the row exists, so pressing the other thumb corrects the verdict
    rather than colliding with the conversation it was already stored under. Only the thumb is
    written: a judgement already on that row is what somebody else made of the same answer.
    """
    def save(self, conversation, source, score = None):
        [feedback, _] = self.model.objects.update_or_create(
            conversation = conversation,
            source = source,
            defaults = {'score': score},
        )

        return feedback

    """The oldest answers nobody has judged yet, as many of them as were asked for.

    Oldest first, so a run that cannot read everything pending reads what has waited longest, and
    the ones it leaves are the ones the next run starts on.
    """
    def findWithoutJudgement(self, limit = None):
        # Each one is read for the question and the answer it is about, which is one query and not one per row
        pending = self.model.objects.select_related('conversation').filter(judgement__isnull = True).order_by('id')

        return list(pending[:limit] if limit is not None else pending)

    """What a judge made of an answer, written onto the row it read rather than beside it.

    Named fields, so a thumb pressed while the judge was reading is not written back over. What the
    call spent is named among them: a field left off this list is assigned and never stored.
    """
    def saveJudgement(self, feedback):
        feedback.save(update_fields = [
            'judgement', 'relevance', 'judge_batch', 'input_tokens', 'output_tokens', 'cost',
        ])

        return feedback

    """The feedback left, newest first, of the run and over the days asked for.

    Everything left, whether a judge has read it back yet or not: what somebody said of an answer
    is worth reading before anything else has been made of it.

    An empty filter is no filter, so the page opens on everything. Ties break on id so two
    verdicts left inside the same second still order deterministically.
    """
    def findFiltered(self, since = None, until = None, batch = None, conversation = None):
        feedbacks = self._filtered(since, until, batch, conversation).select_related('conversation')

        return list(feedbacks.order_by('-created', '-id'))

    """The numbers the feedback is read under, worked out where the rows are.

    The thumbs are stored as 1 and 0, so their mean is the share of them that were positive.
    An average ignores the rows that never had one, and a count of judgements ignores the rows
    nobody has judged, which is what tells the two totals apart.

    The cost is a total and not a mean: what was spent is spent whether it was spread over many
    answers or a few. Nothing judged yet is nothing spent, which a sum gives as no number at all.
    """
    def getFeedbackSummary(self, since = None, until = None, batch = None, conversation = None):
        return self._filtered(since, until, batch, conversation).aggregate(
            positive = Avg('score'),
            relevance = Avg('relevance'),
            judgements = Count('judgement'),
            feedbacks = Count('id'),
            cost = Sum('cost'),
        )

    def _filtered(self, since = None, until = None, batch = None, conversation = None):
        feedbacks = self.model.objects.all()

        if since is not None:
            feedbacks = feedbacks.filter(created__date__gte = since)
        if until is not None:
            feedbacks = feedbacks.filter(created__date__lte = until)
        if batch is not None:
            feedbacks = feedbacks.filter(judge_batch = batch)
        if conversation is not None:
            feedbacks = feedbacks.filter(conversation = conversation)

        return feedbacks

class JudgeBatchRepository(RepositoryBase):

    def __init__(self):
        super().__init__(JudgeBatch)

    """Opened by a run that found something to judge, and named by the link it hands back"""
    def create(self):
        return self.model.objects.create()

class GenresRepository(RepositoryBase):

    def __init__(self):
        self.instrumentsRepository = InstrumentsRepository()
        # The renderer expands parents recursively, so each parent is asked for its own
        # relations too. Prefetching that second level keeps a full render flat; deeper
        # hierarchies would just move the lazy boundary down, not reintroduce the N+1.
        super().__init__(Genre, prefetch = (
            'parents',
            'instruments',
            'parents__parents',
            'parents__instruments',
        ))
