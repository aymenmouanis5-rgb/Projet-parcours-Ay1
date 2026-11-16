# Knowledge base and data architecture (F1, F3)

## Why fishermen retrieve at all

Each prompt only holds the last 2 seasons. Anything older, such as a promise made six seasons ago or an old famine, can only come back through retrieval. This is what makes memory selective: a fisherman recalls what his present situation brings to mind, not everything he has lived through.

## Sources

| Source | Examples | Visibility | Why it is included |
|---|---|---|---|
| Static corpus, `corpus/` | The Hollow Winters, the Silver Year, market accounts, the Reed Bay agreement, lake observations, Halvard's story | Shared | The past of the valley, as listed under "Matière à consulter" for FILETS |
| Market ledgers | One per hamlet, per season | Shared | Everyone can consult what was sold, and by whom |
| Evening talk summaries | One per season | Shared | What was publicly said |
| Personal documents | A fisherman's own words and announced catch | Only that fisherman | Lets him remember his own promise (A1) |

The static corpus is balanced on purpose: reassuring and worrying observations, a success and a failure of restraint, the cost of poverty as well as the risk of depletion.

**The static corpus contains no numeric catch rule and no "keep the lake half full".** Otherwise a norm detected in a run could simply come from the corpus, and the `--no-hint` experiment would be meaningless. The stories also never mention laws, authorities or quotas, because the world has none.

Each corpus file starts with its metadata: `id`, `type`, `hamlet` if any, `sim_time` and `visibility`. Dates in the past are negative, one season being one year.

## Retrieval

1. Before each talk and each decision, the fisherman builds a query from his situation: season, name, hamlet, own debt or need, lake stock and its recent trend. What was said is deliberately left out: with speech in the query, talk summaries took 78% of the results.
2. The query is embedded with `nomic-embed-text` through Ollama (`/api/embed`). This model is small enough to share the GPU with the fishermen's models, runs locally and costs no quota. It expects a `search_query:` or `search_document:` prefix.
3. The store keeps only the documents that pass two filters, then ranks them by cosine similarity.
4. Three slots are filled with the best document of each kind: one corpus document, one own promise, and one ledger or talk summary. A slot stays empty if nothing qualifies, as for promises in a silent run. The results go in the prompt under "What you recall:".
5. A `retrieval` event logs the query, the slots, the document ids and the scores.

Documents are embedded whole, without chunking, because they are short.

The two filters are hard rules, not preferences:

- **Time (C6):** a document is returned only if its `sim_time` is strictly before the moment of the decision.
- **Visibility:** a personal document is returned only to its owner.

The simulated clock inside a season is:

| Moment | `sim_time` |
|---|---|
| Evening talk | season + 0.00 |
| Talk summary and promises indexed | season + 0.25 |
| Dawn decision | season + 0.50 |
| Market closes, ledgers indexed | season + 0.75 |

So a dawn decision can use the previous evening's talk, but not its own season's ledger.

## Vector store

A numpy matrix of normalized vectors in memory, with a JSON cache for the corpus (`corpus/.embeddings.json`). Cosine similarity is then a dot product. With a few hundred documents, exact search takes no noticeable time, so an approximate index or a vector database would add complexity without any gain, and this version can be explained line by line.

## Where each kind of data lives (F3)

| Data | Where | Volume and frequency | Latency need | Kept for |
|---|---|---|---|---|
| Events | Kafka topic `filets.events`, recorded append-only in `events.jsonl` (see `docs/EVENTS.md`) | Hundreds per run, written continuously | Low, must reach the viewer live | Permanently: it is the source for replay and traceability |
| Current world state | Python objects in memory (`Lake`, `Fisher`, `Market`) | Small, read and changed at every step | Immediate | One run only, and rebuilt from events on replay |
| Run history | `summary.json` per run, read by `filets.report` | One file per run, written once | None, read for analysis | Permanently: it produces the report's results |
| Knowledge base | `corpus/` plus the in-memory store; each run's documents in `documents.json` | About 10 new documents per season | Under a second per search | Corpus permanently; dynamic documents with their run |

`documents.json` does not store vectors because they can be recomputed from the text.
