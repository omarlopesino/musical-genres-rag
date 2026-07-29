from django.db import connection

from musical_genres_rag.models import Attachment, EvaluationRun, Feedback, Genre, Instrument

# The sequence migration 0009 creates, read here and nowhere else
CONVERSATION_SEQUENCE = 'feedback_id_seq'

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

class FeedbackRepository(RepositoryBase):

    def __init__(self):
        super().__init__(Feedback)

    """A conversation id nobody else will be given, drawn before there is a row to put it on"""
    def nextConversation(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT nextval(%s)', [CONVERSATION_SEQUENCE])
            [conversation] = cursor.fetchone()

        return conversation

    """Stores what a source made of one answer.

    Written as an update where the row exists, so pressing the other thumb corrects the
    verdict rather than colliding with the key it was already stored under.
    """
    def save(self, conversation, source, question, answer, score = None, judgement = None, relevance = None):
        [feedback, _] = self.model.objects.update_or_create(
            id = conversation,
            source = source,
            defaults = {
                'question': question,
                'answer': answer,
                'score': score,
                'judgement': judgement,
                'relevance': relevance,
            },
        )

        return feedback

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
