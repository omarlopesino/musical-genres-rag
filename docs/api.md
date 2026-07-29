# The JSON API

What an orchestrator runs this project by: building the index, writing the questions to ask it,
answering them and scoring those answers. Each endpoint runs the project's own code for it, the same
code the equivalent command runs, so there is one way of ingesting and one way of evaluating however
it was asked for.

Served by the `app` compose service on port 8000, with no authentication of any kind. The
documentation, and the engines it offers to pick from, are at
[localhost:8000/docs](http://localhost:8000/docs).

## Everything is a task

Each of these operations takes minutes and spends paid LLM calls, so none of them is answered by
holding the connection open until it is over. A `POST` starts the work and replies **202** with the
task it is followed by; what the work produced is read afterwards from `/progress/{task_id}`.

| Method | Path | Body | Does |
|---|---|---|---|
| `POST` | `/ingest` | `engine`, `task_id` | Rebuilds the index from every stored genre |
| `POST` | `/ground-truth` | `task_id` | Writes the questions every evaluation is scored against |
| `POST` | `/create-answers` | `engine`, `task_id` | Answers those questions through the RAG and records what came back |
| `POST` | `/evaluate-rag` | `engine`, `task_id` | Scores the whole pipeline over the answers recorded |
| `POST` | `/evaluate-retrieval` | `engine`, `task_id` | Scores the index alone, live, with no LLM call |
| `GET` | `/progress/{task_id}` | — | Says how far a task got, and what it left behind |

Both body fields are optional, and a body of `{}` is a valid request:

- `engine` is one of the engines the project knows, `postgres_text` today, defaulting to it. It is
  the same list `--engine` takes on the command line. `/ground-truth` takes none, because the
  questions come straight from the repository and no index is searched.
- `task_id` is the caller's own name for the run, so it knows where to poll before the POST returns.
  Anything matching `[A-Za-z0-9._-]{1,128}`; one is invented when it is left out.

```bash
curl -X POST localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"engine": "postgres_text", "task_id": "20260729T101500-ingest"}'
```
```json
{"task_id": "20260729T101500-ingest", "status": "running"}
```

**409** answers a POST for an operation that is already running, naming the task that holds it; one
ingest may not truncate the index under another. **422** answers an engine nobody has heard of.

## Reading a task

```bash
curl localhost:8000/progress/20260729T101500-ingest
```
```json
{"task_id": "20260729T101500-ingest", "operation": "ingest", "phase": "indexing",
 "current": 57, "total": 118, "percent": 48.3,
 "started_at": "2026-07-29T10:15:00.512+00:00", "updated_at": "2026-07-29T10:16:04.238+00:00",
 "done": false, "success": null, "info": null, "result": null}
```

`phase` is what the run is spending its time on — `queued`, `indexing`, `generating`, `answering`,
`scoring`, `judging`, `saving`. `total` and `percent` are null until whatever is being counted is
known.

Once `done`, `result` carries what the operation was asked to report:

| Operation | `result` |
|---|---|
| ingest | `{"ingested": 118, "success": true, "info": "Data has been ingested sucessfully."}` |
| ground-truth | `{"generated": 590, "success": true, "info": "..."}` |
| create-answers | `{"answered": 590, "success": true, "info": "..."}` |
| evaluate-rag, evaluate-retrieval | `{"success": true, "info": "...", "link": "http://localhost:8501/report?run=21"}` |

`link` is the evaluation's own page on the Streamlit app, the same one its list of runs links to.

**Status codes.** 200 while it runs and once it has succeeded. **500**, carrying that very document,
once a run is `done` and not `success` — so a caller that only watches what it polls still fails on
it. **404** for a task nobody started, or one finished over an hour ago and since forgotten.

A failure says which target to run by hand:

```json
{"done": true, "success": false,
 "info": "There was an error ingesting data. Please run make ingest in the server for more details."}
```

The reason itself is in the `app` service's log, in full, where `docker compose logs app` finds it.

## How far the progress goes

- **ingest** counts genres indexed, and **ground-truth** and **create-answers** count questions:
  a true bar in each case.
- **evaluate-retrieval** counts cases as the index answers them, which is where its time goes.
- **evaluate-rag** replays answers `create-answers` already paid for, so its cases fill up almost at
  once and the rest of the run is the `judging` phase — reported as the phase it is, and not as a
  share of anything.

## From Airflow

Airflow draws no progress bar of its own: what the endpoint buys is a sensor that logs how far the
run has got, and a task that fails on its own when the run did.

```python
from airflow.providers.http.operators.http import HttpOperator
from airflow.providers.http.sensors.http import HttpSensor

import json

ENGINE = 'postgres_text'
TASK = '{{ ts_nodash }}-ingest'

start = HttpOperator(
    task_id = 'ingest',
    http_conn_id = 'musical_genres_rag',
    endpoint = '/ingest',
    method = 'POST',
    headers = {'Content-Type': 'application/json'},
    data = json.dumps({'engine': ENGINE, 'task_id': TASK}),
)

# A run that ended badly answers with a 500, which fails this task without a check of its own
wait = HttpSensor(
    task_id = 'ingest_done',
    http_conn_id = 'musical_genres_rag',
    endpoint = '/progress/' + TASK,
    response_check = lambda response: response.json()['done'],
    poke_interval = 10,
    mode = 'reschedule',
)

start >> wait
```

A full pass is those two tasks per operation, in the order the files are needed:

```
ingest → ground-truth → create-answers → evaluate-rag
```

`evaluate-rag` needs the answers file `create-answers` writes for that engine, and refuses to start
without one. `evaluate-retrieval` needs neither answers nor an LLM call, so it may be run against an
engine as often as the engine changes.

## What it does not do

Tasks live in the API process. A restart loses whatever was running and leaves its document reading
`running` for the hour it is cached — `updated_at` is what tells a reader it has stopped moving.
Surviving a restart would mean a real queue, which this does not have.
