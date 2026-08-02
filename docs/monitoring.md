# Monitoring

What the system is doing while it runs, rather than what it did in any one evaluation. The Streamlit
pages answer a question at a time — this conversation, that batch of feedback — and Grafana answers
the one they cannot: how any of it is moving. Whether answers are getting slower, what a week of
traffic costs, whether the judge's verdicts are drifting.

Served by the `grafana` compose service at [localhost:3000](http://localhost:3000), logging in with
`admin` / `admin`. It reads the same Postgres the chat writes to, so there is nothing to feed it and
nothing to keep in step.

## The dashboard

One dashboard, **Conversations**, refreshing every 30 seconds over the last 7 days. Traffic here is
a handful of questions a day, so a range of hours would usually be empty.

| Panel | Reads |
|---|---|
| Conversations, median response time, spend, thumbs up | The four tiles across the top, over whatever range is selected |
| Recent conversations | The last twenty, beside whatever was made of them |
| Model usage | Which model answered, `no model asked` where nothing was retrieved |
| Relevance | What the judge made of the answers it has read |
| Thumbs | What the people who asked pressed |
| Response time | One point per question: retrieval and the model together, which is what the person waited |
| Token usage | Read and written, averaged inside each bucket |
| Cost | Answering stacked against judging those same answers |

Two things a reader trips on otherwise:

- **The relevance bands are a dashboard convention.** The judge stores a score between 0 and 1, not
  a verdict out of three. The pie cuts it at 0.8 and 0.4 to read at a glance; nothing stored says
  where those lines are, and moving them is a change to one `CASE` in the panel.
- **Feedback exists only where somebody pressed a thumb.** A conversation nobody rated is never
  judged either, so the relevance and thumbs panels cover rated answers rather than all traffic.
  The conversation panels beside them cover everything.

## Traffic to draw

Both tables only fill up when somebody sits in the chat, a paid call per question, so on a fresh
clone every panel above is empty. `make sample` — or the **7. Sample traffic** dag — writes some
instead, replaying the answers committed under `data/demo` as conversations and rating some of them.
It costs nothing, and it takes the window it is spread over on purpose: rows written in one instant
share a timestamp and draw no line.

Two things to know while doing it:

- **Set the range to the last 15 minutes.** The default is 7 days, and `$__timeGroup` sizes its
  buckets from the range, so half a minute of traffic lands in a single bucket: token usage becomes
  one point and cost one bar. The default is right for real traffic and wrong for watching this
  arrive. Remember the dashboard refreshes every 30 seconds, so a run of that length may take a
  cycle to show up.
- **A sampled conversation carries `sampled` in its `answer`.** Nothing here reads it — every panel
  reads `answer->'answer'->>'answer'` and no more — so it changes nothing and still tells the made-up
  rows from the real ones. `delete from feedback where conversation_id in (select id from
  conversation where answer ? 'sampled')`, then the same over `conversation`, takes them all back
  out.

The verdicts a sampling run leaves are made up rather than judged, which is why nothing is spent and
why **6. Feedback judge** will not read those rows back: it looks for feedback with no judgement.

## Where it comes from

Provisioned out of this repository rather than built by hand in the UI, so a fresh volume comes up
already wired:

| File | Is |
|---|---|
| `grafana/provisioning/datasources/postgres.yml` | The database, named by the same `.env` everything else reads |
| `grafana/provisioning/dashboards/dashboards.yml` | Where to find dashboards, and that they may be edited |
| `grafana/dashboards/conversations.json` | The dashboard: its panels, their queries and their layout |

The data source pins its `uid`, and the dashboard names that `uid` in every panel. Left to Grafana
they would be generated afresh on a new volume and every panel would come up pointing at nothing.
The dashboard pins a `uid` of its own for the same reason: provisioning it again updates the one
that is there instead of leaving a second copy beside it.

Panels can still be dragged about and edited in the UI — `allowUiUpdates` is on — but the file is
what comes back on a restart. Anything worth keeping is exported back into it from **Dashboard
settings → JSON Model**, with `id` set to `null` and the `uid` left alone.

## What it is reading

Both LLM calls record what they took and spent, in the same shape, which is why answering and
judging can be read against each other:

- `conversation` carries `duration`, `input_tokens`, `output_tokens`, `cost` and `model` for the
  call that wrote the answer. The `answer` JSON holds the first three as well, as the call reported
  them; the columns exist because a dashboard reads them a time range at a time and would otherwise
  dig through the JSON on every row.
- `feedback` carries `input_tokens`, `output_tokens` and `cost` for the call that judged it, and
  `score` for the thumb somebody pressed.

Costs are worked out at what the model charges, priced in one place, `cost()` in `Rag.py`. Nothing
in Grafana knows a price: it sums a column.
