empty :=
space := $(empty) $(empty)
.RECIPEPREFIX := $(space)

.PHONY: setup build start stop drop psql migrate seed directories ingest rag groundtruth evaluate evaluateRetrieval createAnswers

DB_NAME = musical_genres
MANAGE = uv run python manage.py
GROUND_TRUTH_DIRECTORY = tests/ground_truth

# Which search engine the index, rag and evaluation targets run through, as in
# "make evaluateRetrieval ENGINE=postgres_text". Left unset, each command uses its own default.
ENGINE ?=
ENGINE_ARG = $(if $(ENGINE),--engine $(ENGINE))

setup:
    uv sync
    $(MAKE) directories
    docker compose down -v
    docker compose up -d --wait
    $(MAKE) migrate
    $(MAKE) seed

# tests/ holds generated files only and is gitignored, so a fresh clone starts without the
# directory the ground truth is written into.
directories:
    mkdir -p $(GROUND_TRUTH_DIRECTORY)

build:
    docker compose build

start:
    docker compose up -d --wait

stop:
    docker compose stop

drop:
    docker compose down -v

psql:
    docker compose exec db psql -U postgres -d $(DB_NAME)

migrate:
    $(MANAGE) migrate

# Seeding runs through psql rather than a management command: load.sql is a
# multi-statement script whose COPY reads server-side files under /data.
seed:
    docker compose exec -T db psql -U postgres -d $(DB_NAME) -f /data/load.sql

ingest:
    $(MANAGE) ingest $(ENGINE_ARG)

rag:
    $(MANAGE) rag $(ENGINE_ARG)

# No engine: the questions come straight from the repository, with no index searched
groundtruth:
    $(MANAGE) groundtruth

evaluate:
    $(MANAGE) evaluate $(ENGINE_ARG)

# Retrieval only: no LLM call and no answers file, so it is free to re-run while tuning an engine
evaluateRetrieval:
    $(MANAGE) evaluate --type retrieval $(ENGINE_ARG)

createAnswers:
    $(MANAGE) createAnswers $(ENGINE_ARG)
