# Status: EIGSI projet parcours, subject 05 FILETS

Updated at the end of every step. Last update: 2026-11-13, step 1.

## Decisions

- Prompts are frozen at `PROMPT_VERSION = 2`. They are not changed.
- `misread_hint` is a result to measure, not a bug to fix: the prompt stays as it is, and the indicator counts how often a group limit is read as a per-person limit.

## Done

| Item | Where |
|---|---|
| Simulation: talk, silent, rules, quota; sync and async timing | `filets/sim.py`, `filets/async_world.py` |
| Market with one price per hamlet | `filets/market.py` |
| RAG with a corpus, time-consistent retrieval | `filets/knowledge.py`, `corpus/`, `docs/RAG.md` |
| Kafka bus, recorder, dead-letter topic | `filets/bus.py`, `docker-compose.yml`, `docs/EVENTS.md` |
| Schema validation (schema 8) | `filets/schemas.py` |
| Live web viewer | `filets/viewer.py`, `filets/viewer.html` |
| B1 definition and B2 indicator, final version (step 1): respect on requested amounts, each/total settled once per season, sum check for group rules, `hint_derived`, chance baseline in --no-hint runs. 14 tests | `docs/B1_contexte_commun.md`, `filets/indicator.py`, `tests/test_indicator.py` |

## Missing for the Socle

| Item | Step |
|---|---|
| Godot scene and websocket bridge (D1–D3) | 2 |
| Replay of a recorded run into Godot, verified (E3) | 2 |
| Final experiment batch (E2, B3, C5, E5) | 3 |

## Indicator choices made in step 1 (to confirm)

- A mentioner who says "each" or "in total" votes by that word; only unmarked mentions vote by their plan. A tie goes to the mentioners' mean plan.
- Group rule, announced check: the sum must not exceed the limit by more than 0.05 t. It is a ceiling, not a two-sided band, so announcing well below the total also passes.
- `hint_derived` is false in --no-hint runs, even when the chance `misread_hint` is true, since no hint was given.
