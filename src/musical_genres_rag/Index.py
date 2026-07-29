from django.db import connection
from musical_genres_rag.Embed import TextEmbedder
from musical_genres_rag.Progress import NULL_PROGRESS
from psycopg import sql

DEFAULT_LIMIT = 4

INDEXING = 'indexing'

class Index():

    def __init__(self, searchEngine, entityRepository, limit = DEFAULT_LIMIT):
        self.searchEngine = searchEngine
        self.entityRepository = entityRepository
        self.limit = limit

    """Returns how many entities were indexed, which is the whole of what was stored"""
    def index(self, progress = NULL_PROGRESS):
        self.searchEngine.clearContent()
        entities = self.entityRepository.loadMultiple()
        progress.start(INDEXING, len(entities))
        # @todo improve to make it paralelly!
        self._indexEntityBatch(entities, progress)

        return len(entities)

    def search(self, query, limit = None):
        return self.searchEngine.search(query, limit if limit is not None else self.limit)

    def getEngineName(self):
        return self.searchEngine.getName()

    """How many results a search returns, so an evaluation can record the k it scored"""
    def getLimit(self):
        return self.limit

    def getEmbeddingModel(self):
        return self.searchEngine.getEmbeddingModel()

    def _indexEntityBatch(self, entities, progress = NULL_PROGRESS):
        for entity in entities:
            self.searchEngine.indexEntity(entity)
            progress.advance()

class SearchEngine:

    def __init__(self, embedders):
        self.embedders = embedders

    def clearContent(self):
        pass

    def indexEntity(self, entity):
        attributes = ['id']
        params = [entity.getId()]
        for key, embedder  in self.embedders.items():
            attributes.append(key)
            embedderInstance = embedder(entity)
            params.append(embedderInstance.embed())
        self._doIndex(attributes, params)

    def _doIndex(self, attributes, params):
        pass

    def getName(self):
        pass

    """What embedded the indexed content, which the engine name alone does not tell apart"""
    def getEmbeddingModel(self):
        return ','.join(sorted(embedder.__name__ for embedder in self.embedders.values()))

class PostgresSearchEngine(SearchEngine):

    def __init__(self, table, mode = 'text'):
        super().__init__(self._getEmbedders(mode))
        self.table = table
        self.mode = mode
        self.textIndex = table + '_text'

    def _getEmbedders(self, mode):
        embedders = {}
        match mode:
            case 'text' | _:
                embedders['content'] = TextEmbedder

        return embedders

    def search(self, query, limit = 5):
        # The bare "content <@> 'text'" form only resolves the index when the
        # query is inlined, so name the index explicitly to use a placeholder.
        sqlQuery = sql.SQL('SELECT id FROM {table} ORDER BY content <@> to_bm25query(%s, {index}) LIMIT {limit}').format(
            table = sql.Identifier(self.table),
            index = sql.Literal(self.textIndex),
            limit = sql.Literal(limit)
        )
        with connection.cursor() as cursor:
            cursor.execute(sqlQuery, [query])
            return [id for [id] in cursor.fetchall()]

    def clearContent(self):
        truncate = sql.SQL('TRUNCATE {table}').format(table = sql.Identifier(self.table))
        with connection.cursor() as cursor:
            cursor.execute(truncate)

    def _doIndex(self, attributes, params):
        query = sql.SQL('INSERT INTO {table} ({fields}) VALUES ({values})').format(
            table = sql.Identifier(self.table),
            fields = sql.SQL(',').join(sql.Identifier(attribute) for attribute in attributes),
            values = sql.SQL(',').join(sql.Placeholder() for attribute in attributes)
        )

        with connection.cursor() as cursor:
            cursor.execute(query, params)

    def getName(self):
        return 'postgres_' + self.mode
