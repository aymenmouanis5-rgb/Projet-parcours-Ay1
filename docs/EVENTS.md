# Events (C1, C3, F3, F4)

## Flow

```
simulation -> Kafka topic filets.events -> recorder -> runs/<run>/events.jsonl
                                              |
                                              -> filets.events.dlq (non-conforming events)
```

The simulation never writes the log itself, so `events.jsonl` only holds what went through Kafka. Later consumers, such as the Godot bridge and the live indicators, read the same topic.

Start the broker with `docker compose up -d`.

## Topics

| Topic | Partitions | Content |
|---|---|---|
| `filets.events` | 1 | All events, keyed by run id |
| `filets.events.dlq` | 1 | Rejected events, with the reasons |

Both topics have exactly 1 partition, and every event is keyed by run id. Check it with `docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic filets.events`.

There is a single partition because replay needs one total order across the whole run. The key lets the recorder and later consumers keep only one run's events, since all runs share the topic. Splitting by agent or by event type would lose the order between a message and the decision it influenced. A run produces a few hundred events, so throughput is not a constraint.

## Granularity (C1)

An event is one thing a viewer or an analysis must be able to see separately: a sentence said, a retrieval, a decision, a landing, a sale, a closed season. Tokens and raw prompts are not published: they are not needed to replay the run, and would multiply the volume with no use. The lake is published once per season because it only changes through catches, which are published individually, and regrowth, which is computed from them.

## Common fields

Every event carries these fields. `SCHEMA_VERSION` is defined in `filets/schemas.py`; the current version is 8.

| Field | Type | Meaning |
|---|---|---|
| `v` | int | Schema version |
| `id` | string | Unique event id, run id plus a sequence number |
| `run` | string | Run id |
| `type` | string | Event type |
| `season` | int | Season it belongs to |
| `sim_time` | number | Simulated moment it happened |
| `processed_at` | number | Real time it was produced |
| `consumed_at` | number | Real time it was recorded, added by the recorder |

`sim_time` and `processed_at` are the two clocks required by C3. The gap between `processed_at` and `consumed_at` is the transport delay.

## Event types

| Type | Required fields |
|---|---|
| `run_started` | `agents`, `seasons`, `mode`, `seed`, `model`, `hint`, `timing`, `prompt_version`, `stock` |
| `message` | `agent`, `text`, `planned_catch`, `seed` |
| `retrieval` | `agent`, `phase`, `query`, `documents` |
| `decision` | `agent`, `model`, `requested`, `safe_total` |
| `catch` | `agent`, `caught`, `planned` |
| `sale` | `agent`, `hamlet`, `tons`, `price`, `revenue` |
| `lake` | `stock`, `total_caught`, `safe_total`, `safe_violation`, `overshoot` |
| `incident` | `kind` |
| `collapse` | `stock` |
| `run_ended` | `status`, `seasons_survived`, `total_catch`, `final_stock`, `mean_stock`, `safe_violations` |

Extra fields are allowed. `decision` carries the `seed` of the LLM call, derived from the run seed, season, fisher, call index and attempt, so a retry never shifts a later call. `message` and `decision` also carry `served_model`, the name Ollama returned; if it differs from the requested model, a `model_mismatch` incident is logged. For LLM fishers, `decision` also carries `retrieved_promise`, `promise_age` and `promise_cited`. `promise_cited` is a literal check: the reasoning refers in the first person to something the fisher already promised or announced ("I announced", "my promise"), or names the season of the retrieved promise. It does not prove the promise changed the decision. In async timing, `catch` also carries `decided_in`, `stock_seen`, `stock_at_landing` and `seen_at`.

## Rejected events (F4)

The recorder validates each event against `filets/schemas.py`. A non-conforming event is sent to `filets.events.dlq` with the reasons, left out of the log, and counted in `events_rejected` in `summary.json`. The run continues.

## Timing modes (C3, C4)

| | `--timing sync` | `--timing async` |
|---|---|---|
| Clock | Moved by the season loop | Follows the wall clock, `--season-seconds` per season |
| Talk order | Shuffled, one at a time | Order of arrival: a fisher hears only those already finished |
| Fishing | Simultaneous, on the same stock | Each catch lands on the lake as it is at that moment |
| A slow fisher | Makes the others wait | Lands late and misses his next turn |
| Seasons | End when everyone has acted | End on time, whoever has acted |

A fisher acts at most once per season. In async timing, `summary.json` reports late landings, missed turns, and how much the stock moved between the fisher's look and his landing.

Time consistency (C6) is enforced at retrieval, which only returns documents older than the decision. `filets.report` also counts any violation found in the logs.
