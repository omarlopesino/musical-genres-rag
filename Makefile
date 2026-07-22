empty :=
space := $(empty) $(empty)
.RECIPEPREFIX := $(space)

.PHONY: up psql

DB_NAME = musical_genres

setup:
    docker compose down -v
    docker compose up -d

build:
    docker compose build

start:
    docker compose up -d

stop:
    docker compose stop

drop:
    docker compose down -v

psql:
    docker compose exec db psql -U postgres -d $(DB_NAME)
