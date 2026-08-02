empty :=
space := $(empty) $(empty)
.RECIPEPREFIX := $(space)

.PHONY: setup build start stop drop psql migrate seed config directories downloadModel ingest rag groundtruth evaluate evaluateRetrieval createAnswers demo demoExport

DB_NAME = musical_genres
MANAGE = uv run python manage.py
GROUND_TRUTH_DIRECTORY = tests/ground_truth

# Which search engine the index, rag and evaluation targets run through, as in
# "make evaluateRetrieval ENGINE=postgres_hybrid". One of postgres_text, postgres_embed or
# postgres_hybrid. Left unset, each command uses its own default.
ENGINE ?=
ENGINE_ARG = $(if $(ENGINE),--engine $(ENGINE))

setup:
    uv sync
    $(MAKE) config
    $(MAKE) directories
    $(MAKE) downloadModel
    docker compose down -v
    docker compose up -d --wait
    $(MAKE) migrate
    $(MAKE) seed

# The prompts, the models and the engine, which are edited rather than committed. Before
# downloadModel on purpose: which weights that fetches is read from here. Never overwrites a
# config.yml already there, since what it holds is somebody's tuning.
config:
    cp -n config.yml.dist config.yml

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

# Ninety megabytes of weights, which are not source and are not committed. Only the vector engines
# read them, and this needs no database: it runs before the containers are up on purpose.
downloadModel:
    $(MANAGE) downloadModel

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

# The committed evaluations, read into a fresh database so the dashboard has an evaluation of each
# kind to show without a single paid call. What "0. Demo data" runs in Airflow.
demo:
    $(MANAGE) demo

# Rewrites what that loads from the latest runs stored here. Run it after a retune, and commit.
demoExport:
    $(MANAGE) exportDemo
