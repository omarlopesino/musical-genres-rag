from django.db import connection
from musical_genres_rag.Embed import TextEmbedder
from psycopg import sql

class Index():

    def __init__(self, searchEngine, entityRepository):
        self.searchEngine = searchEngine
        self.entityRepository = entityRepository

    def index(self):
        self.searchEngine.clearContent()
        entities = self.entityRepository.loadMultiple()
        # @todo improve to make it paralelly!
        self._indexEntityBatch(entities)

    def search(self, query, limit = 5):
        return self.searchEngine.search(query, limit)

    def _indexEntityBatch(self, entities):
        for entity in entities:
            self.searchEngine.indexEntity(entity)

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
    
    def getName():
        pass

class PostgresSearchEngine(SearchEngine):

    def __init__(self, table, mode = 'text'):
        super().__init__(self._getEmbedders(mode))
        self.table = table
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

    def getName():
        return 'postgres_' + self.mode
