# Musical genres RAG

RAG to get information about musical genres:

- Getting information about genres: its description, its related gnres and instruments.
- Get the genres that originated a specific genre.
- Allow to know which genres can be created with specific instruments.

In short, ask anything about any musical genre and you will get all the information you want. 

## Services

`make start` brings all of these up, and `make stop` puts them down again:

| Service | Purpose | Local |
|---|---|---|
| `ui` | Streamlit: the chat, and the conversations, feedback and evaluation pages | [localhost:8501](http://localhost:8501) |
| `app` | Django: the JSON API the pipeline is driven by, documented in [api.md](docs/api.md) | [localhost:8000](http://localhost:8000/docs) |
| `grafana` | The dashboard over live traffic, `admin` / `admin`, described in [monitoring.md](docs/monitoring.md) | [localhost:3000](http://localhost:3000) |
| `airflow` | The orchestrator running the dags in `dags/`, with no login | [localhost:8080](http://localhost:8080) |
| `db` | Postgres with pgvector and BM25: the genres, the index, the conversations and the feedback | `postgres://localhost:5432/musical_genres` |
| `redis` | Where a running task writes its progress, so whoever polls it reads what another process wrote | `redis://localhost:6379` |

`make setup` is the first run: it installs, writes the configuration, downloads the embedding
weights, starts everything, migrates and seeds. The classes behind all of it are drawn in
[architecture.md](docs/architecture.md).

## Configuration

`config.yml` holds what decides how the RAG behaves: every prompt it sends, which model writes and
judges its answers, which model it embeds with, and which engine it searches through. Changing any
of them is editing that file, not the code.

`make setup` copies it from the committed `config.yml.dist`, and `make config` does the same on its
own. Your copy is not committed and is never overwritten, so a prompt you are tuning stays yours.
The secrets stay in `.env`, and `.env.example` is what that one is copied from.

Every target that touches the index takes `ENGINE=`, which is `postgres_text` for bm25,
`postgres_embed` for vectors or `postgres_hybrid` for both fused by rank — as in
`make evaluateRetrieval ENGINE=postgres_hybrid`, which scores the index alone and costs nothing to
re-run. It overrides `index_engine` for that one run; left out, the file decides. The weights the
vector engines embed with are fetched by `make downloadModel` and are not committed.

## Data license

The content is derived from [MusicBrainz](https://musicbrainz.org/) data and is licensed under
[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/).

Descriptions come from [Wikidata](https://www.wikidata.org/) and the English Wikipedia, reached
through the links MusicBrainz itself records — the same source musicbrainz.org renders. Wikidata is
[CC0](https://creativecommons.org/publicdomain/zero/1.0/); Wikipedia text is
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
