from musical_genres_rag.Embed import TextEmbedder
from psycopg import sql

class Index():

    def __init__(self, database, table, entityRepository):
        self.database = database
        self.table = table
        self.textIndex = table + '_text'
        self.entityRepository = entityRepository
        self.embedders = {
            'content': TextEmbedder
        }

    def index(self):
        # @todo improve to make it paralelly!
        truncate = sql.SQL('TRUNCATE {table}').format(table = sql.Identifier(self.table))
        with self.database.query(truncate):
            pass

        entities = self.entityRepository.loadMultiple()
        self._indexEntityBatch(entities)

    def search(self, query, limit = 5):
        # The bare "content <@> 'text'" form only resolves the index when the
        # query is inlined, so name the index explicitly to use a placeholder.
        sqlQuery = sql.SQL('SELECT id FROM {table} ORDER BY content <@> to_bm25query(%s, {index}) LIMIT {limit}').format(
            table = sql.Identifier(self.table),
            index = sql.Literal(self.textIndex),
            limit = sql.Literal(limit)
        )
        with self.database.query(sqlQuery, [query]) as queryResult:
            return [id for [id] in queryResult.fetchall()]

    def _indexEntityBatch(self, entities):
        for entity in entities:
            self._indexDatabase(entity)

    def _indexDatabase(self, entity):
        attributes = ['id']
        params = [entity.getId()]
        for key, embedder  in self.embedders.items():
            attributes.append(key)
            embedderInstance = embedder(entity)
            params.append(embedderInstance.embed())
        
        query = sql.SQL('INSERT INTO {table} ({fields}) VALUES ({values})').format(
            table = sql.Identifier(self.table),
            fields = sql.SQL(',').join(sql.Identifier(attribute) for attribute in attributes),
            values = sql.SQL(',').join(sql.Placeholder() for attribute in attributes)
        )

        with self.database.query(query, params):
            pass
