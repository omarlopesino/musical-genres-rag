empty :=
space := $(empty) $(empty)
.RECIPEPREFIX := $(space)

.PHONY: setup build start stop drop psql migrate seed ingest rag groundtruth

DB_NAME = musical_genres
MANAGE = uv run python manage.py

setup:
    uv sync
    docker compose down -v
    docker compose up -d --wait
    $(MAKE) migrate
    $(MAKE) seed

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
    $(MANAGE) ingest

rag:
    $(MANAGE) rag

groundtruth:
    $(MANAGE) groundtruth
