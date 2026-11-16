# FILETS

EIGSI projet parcours, subject 05: LLM fishermen sharing one regenerating lake.

**Progress and decisions: [docs/STATUS.md](docs/STATUS.md).** Read it first when resuming.

## Setup on a new machine

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com).

```sh
uv sync                                   # creates .venv from uv.lock
ollama pull llama3.2:3b
ollama pull llama3.2:1b
ollama pull nomic-embed-text
docker compose up -d                      # Kafka on localhost:9092
uv run python -m filets --mode talk --seed 1
uv run python -m unittest discover tests
```

Runs are written to `runs/`.

## Working rules (carry over between sessions)

- Prompts are frozen at `PROMPT_VERSION = 2`. Do not change them.
- `misread_hint` is a result to measure, not a bug to fix.
- Plan, in order, stopping at each checkpoint for approval:
  0. keep `docs/STATUS.md` updated after every step;
  1. final indicator changes (done);
  2. Godot 4 scene + Python websocket bridge, drought command on `filets.commands`, LLM-free replay (D1–D3, E3);
  3. batch script, 5 seeds per config. Write it, do not start it (E2, B3, C5, E5).
