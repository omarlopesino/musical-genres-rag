from musical_genres_rag.Embed import TextEmbedder
from psycopg import sql

class Index():

    def __init__(self, database, table, entityRepository):
        self.database = database
        self.table = table
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
        self.indexEntityBatch(entities)

    def indexEntityBatch(self, entities):
        for entity in entities:
            self.indexDatabase(entity)

    def indexDatabase(self, entity):
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
