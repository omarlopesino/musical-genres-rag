from django.db import connection
from musical_genres_rag.Embed import TextEmbedder, VectorEmbedder
from musical_genres_rag.Fusion import ReciprocalRankFusion
from musical_genres_rag.Progress import NULL_PROGRESS
from musical_genres_rag.Vectorizer import Vectorizer
from psycopg import sql

DEFAULT_LIMIT = 4

INDEXING = 'indexing'

# The columns a document is written to, which are also the ways it can be searched
TEXT_COLUMN = 'content'
VECTOR_COLUMN = 'embed'

"""What a value has to be cast to on its way in, for the columns whose type its parameter does not
carry by itself.

A vector arrives as its own literal text, "[0.1,0.2]", and parameters are bound client side, so this
cast is the whole of what turns that literal into a vector. Nothing is registered on the connection
to write one, or to read one back.
"""
COLUMN_CASTS = {
    VECTOR_COLUMN: sql.SQL('::vector'),
}

"""How deep each half of a hybrid search reads before the two are fused.

A document one half never returned cannot be recovered by any fusion, so each of them is read past
what was asked for. Five times the limit, and never fewer than twenty, which is where 1 / (60 + rank)
has flattened enough that a deeper candidate can no longer outweigh what both halves agreed on.
"""
CANDIDATE_FACTOR = 5
CANDIDATE_MINIMUM = 20

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
        return ','.join(sorted(embedder.getModelName() for embedder in self.embedders.values()))

class PostgresSearchEngine(SearchEngine):

    def __init__(self, table, mode = 'text'):
        super().__init__(self._getEmbedders(mode))
        self.table = table
        self.mode = mode
        self.textIndex = table + '_text'
        self.fusion = ReciprocalRankFusion()

    """Which columns the mode writes, and what writes them.

    Keyed by the column, so what an engine indexes and what it searches are the one decision. The
    modes are matched as literals rather than as constants: a bare name in a case pattern binds the
    subject instead of comparing against it.
    """
    def _getEmbedders(self, mode):
        embedders = {}
        match mode:
            case 'embed':
                embedders[VECTOR_COLUMN] = VectorEmbedder

            case 'hybrid':
                embedders[TEXT_COLUMN] = TextEmbedder
                embedders[VECTOR_COLUMN] = VectorEmbedder

            case 'text' | _:
                embedders[TEXT_COLUMN] = TextEmbedder

        return embedders

    def search(self, query, limit = DEFAULT_LIMIT):
        match self.mode:
            case 'embed':
                return self._searchVector(query, limit)

            case 'hybrid':
                return self._searchHybrid(query, limit)

            case 'text' | _:
                return self._searchText(query, limit)

    def clearContent(self):
        truncate = sql.SQL('TRUNCATE {table}').format(table = sql.Identifier(self.table))
        with connection.cursor() as cursor:
            cursor.execute(truncate)

    def getName(self):
        return 'postgres_' + self.mode

    def _searchText(self, query, limit):
        # The bare "content <@> 'text'" form only resolves the index when the
        # query is inlined, so name the index explicitly to use a placeholder.
        sqlQuery = sql.SQL('SELECT id FROM {table} ORDER BY {column} <@> to_bm25query(%s, {index}) LIMIT {limit}').format(
            table = sql.Identifier(self.table),
            column = sql.Identifier(TEXT_COLUMN),
            index = sql.Literal(self.textIndex),
            limit = sql.Literal(limit)
        )

        return self._fetchIds(sqlQuery, [query])

    """Cosine distance, which is what the hnsw index was built on, and what the unit length the
    vectorizer returns makes the same ordering as the dot product"""
    def _searchVector(self, query, limit):
        sqlQuery = sql.SQL('SELECT id FROM {table} ORDER BY {column} <=> %s::vector LIMIT {limit}').format(
            table = sql.Identifier(self.table),
            column = sql.Identifier(VECTOR_COLUMN),
            limit = sql.Literal(limit)
        )

        return self._fetchIds(sqlQuery, [Vectorizer.getShared().encode(query)])

    """Both searches, fused by the rank each of them gave rather than by the score.

    The two are read deeper than what was asked for and then cut back to it, so what both of them
    found rises over what only one of them put first.
    """
    def _searchHybrid(self, query, limit):
        depth = max(limit * CANDIDATE_FACTOR, CANDIDATE_MINIMUM)

        return self.fusion.fuse(
            [self._searchText(query, depth), self._searchVector(query, depth)],
            limit
        )

    def _fetchIds(self, sqlQuery, params):
        with connection.cursor() as cursor:
            cursor.execute(sqlQuery, params)
            return [id for [id] in cursor.fetchall()]

    def _doIndex(self, attributes, params):
        query = sql.SQL('INSERT INTO {table} ({fields}) VALUES ({values})').format(
            table = sql.Identifier(self.table),
            fields = sql.SQL(',').join(sql.Identifier(attribute) for attribute in attributes),
            values = sql.SQL(',').join(self._getPlaceholder(attribute) for attribute in attributes)
        )

        with connection.cursor() as cursor:
            cursor.execute(query, params)

    """A value goes in as it comes, unless its column is one the parameter does not type by itself"""
    def _getPlaceholder(self, attribute):
        return sql.SQL('{placeholder}{cast}').format(
            placeholder = sql.Placeholder(),
            cast = COLUMN_CASTS.get(attribute, sql.SQL(''))
        )
