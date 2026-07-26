from musical_genres_rag.models import Genre, Instrument

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
