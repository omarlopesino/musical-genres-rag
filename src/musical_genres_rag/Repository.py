import json

from psycopg import sql

from musical_genres_rag.Model import Genre, Instrument

class RepositoryBase():

    def __init__(self, table, database, cache):
        self.table = table
        self.database = database
        self.cache = cache
        self.rows = {}
        self.ids = {}

    def load(self, id):
        rows = self.loadMultiple([id])
        return rows[0] if rows else None

    def _buildEntity(self, row):
        pass

    """Loads the given ids, from cache when available and by query otherwise, keeping their order"""
    def loadMultiple(self, ids = []):
        if not ids:
            return [self._buildEntity(row) for row in self._cacheRows(self._queryRows())]

        rows = self._cachedRows(ids)
        missing = [id for id in ids if id not in rows]

        for row in self._cacheRows(self._queryRows(missing)) if missing else []:
            [id, *values] = row
            rows[id] = row

        return [self._buildEntity(rows[id]) for id in ids if id in rows]

    def _queryRows(self, ids = []):
        query = sql.SQL('SELECT * FROM {table}').format(table = sql.Identifier(self.table))
        params = None

        if ids:
            query = query + sql.SQL(' WHERE id = ANY(%s)')
            params = [list(ids)]

        with self.database.query(query, params) as result:
            return result.fetchall()

    def _cacheId(self, id):
        return '{table}:{id}'.format(table = self.table, id = id)

    """Reads the individually cached rows keyed by id, statically first and from Redis next, skipping the ones missing from both"""
    def _cachedRows(self, ids):
        rows = {}

        for id in ids:
            if id in self.rows:
                rows[id] = self.rows[id]
                continue

            value = self.cache.getValue(self._cacheId(id))
            if value is not None:
                rows[id] = self.rows[id] = json.loads(value)

        return rows

    """Resolves a list of related ids under the given cid, statically first, from Redis next and by query last"""
    def _cachedIds(self, cid, query, params = None):
        if cid in self.ids:
            return self.ids[cid]

        value = self.cache.getValue(cid)
        if value is None:
            with self.database.query(query, params) as result:
                ids = [id for (id, ) in result.fetchall()]
            self.cache.setValue(cid, json.dumps(ids))
        else:
            ids = json.loads(value)

        self.ids[cid] = ids

        return ids

    """Caches every row individually, statically and in Redis, before any entity is built out of them"""
    def _cacheRows(self, rows):
        for row in rows:
            [id, *values] = row
            self.rows[id] = row
            self.cache.setValue(self._cacheId(id), json.dumps(list(row)))

        return rows

class InstrumentsRepository(RepositoryBase):

    def __init__(self, database, cache):
        super().__init__('instrument', database, cache)
    
    def _buildEntity(self, entity):
        [id, name, description] = entity
        return Instrument(id, name, description)

class GenresRepository(RepositoryBase):

    def __init__(self, database, cache):
        self.instrumentsRepository = InstrumentsRepository(database, cache)
        super().__init__('genre', database, cache)
    
    def _buildEntity(self, entity):
        [id, name, description] = entity
        genre = Genre(id, name, description)
        instruments = self.loadGenreInstruments(genre)
        genre.setInstruments(instruments)
        parents = self.loadGenreParents(genre)
        genre.setParents(parents)
        return genre

    def loadGenreParents(self, genre: Genre):
        query = sql.SQL('SELECT parent FROM genre_hierarchy WHERE genre = (%s)')
        cid = 'genre_hierarchy:{genre}'.format(genre = genre.getId())
        ids = self._cachedIds(cid, query, [genre.getId()])
        return self.loadMultiple(ids) if len(ids) > 0 else []

    def loadGenreInstruments(self, genre: Genre):
        query = sql.SQL('SELECT instrument FROM instrument_genres WHERE genre = (%s)')
        cid = 'instrument_genres:{genre}'.format(genre = genre.getId())
        ids = self._cachedIds(cid, query, [genre.getId()])
        return self.instrumentsRepository.loadMultiple(ids) if len(ids) > 0 else []
