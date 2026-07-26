# Class diagram

Classes under `src/musical_genres_rag`.

Persistence is Django's: `models.py` holds the ORM models, connections come from
`django.db`, and the schema lives in `migrations/`. `Repository` survives only as a
thin ordering-preserving facade over the managers.

```mermaid
classDiagram
    direction TB

    namespace models {
        class EntityModel {
            +id
            +name
            +description
            +getId()
            +getName()
            +getDescription()
            +getProperties()
        }

        class Genre {
            +parents: ManyToMany~Genre~
            +instruments: ManyToMany~Instrument~
            +getProperties()
        }

        class Instrument {
            +genres: ManyToMany~Genre~
        }

        class GenreHierarchy {
            +genre: FK~Genre~
            +parent: FK~Genre~
        }

        class InstrumentGenres {
            +instrument: FK~Instrument~
            +genre: FK~Genre~
        }

        class GenreIndex {
            +id
            +content
        }
    }

    namespace Repository {
        class RepositoryBase {
            +model
            +prefetch
            +load(id)
            +loadMultiple(ids)
        }

        class InstrumentsRepository {
        }

        class GenresRepository {
            +instrumentsRepository: InstrumentsRepository
        }
    }

    class DjangoORM["django.db"] {
        +connection
        +Manager.prefetch_related()
        +QuerySet.in_bulk()
    }

    EntityModel <|-- Genre
    EntityModel <|-- Instrument
    RepositoryBase <|-- InstrumentsRepository
    RepositoryBase <|-- GenresRepository

    Genre "1" o-- "*" Genre : parents
    Genre "1" o-- "*" Instrument : instruments
    GenreHierarchy ..> Genre : through
    InstrumentGenres ..> Instrument : through
    InstrumentGenres ..> Genre : through

    RepositoryBase --> DjangoORM : loads, prefetches, restores id order
    GenresRepository *-- InstrumentsRepository

    InstrumentsRepository ..> Instrument : loads
    GenresRepository ..> Genre : loads
```

## Entry points

The `uv` scripts became `manage.py` subcommands, wired through `services.py`:

| Command | Does |
|---|---|
| `manage.py ingest` | Rebuilds `genre_index` from every stored genre |
| `manage.py rag [question]` | Answers a question from the indexed context |
| `manage.py groundtruth [--output]` | Regenerates the ground truth question set |
| `manage.py debug [--mode]` | `renderers`, `genres` or `queries` inspection |

`PostgresSearchEngine` still issues raw SQL through `django.db.connection`: the bm25
operator (`content <@> to_bm25query(...)`) has no ORM expression, and the same will be
true of the hybrid query once a pgvector column is added.
