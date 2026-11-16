"""F2: sample decisions of a run for manual relevance scoring.

`uv run python -m filets.retrieval_check runs/<run>`
"""

import argparse
import json
import random
from pathlib import Path

SAMPLE_SIZE = 20
EXCERPT = 70

parser = argparse.ArgumentParser(prog="filets.retrieval_check")
parser.add_argument("run", type=Path)
parser.add_argument("--seed", type=int, default=0)
args = parser.parse_args()

lines = (args.run / "events.jsonl").read_text(encoding="utf-8").splitlines()
retrievals = [e for e in map(json.loads, lines) if e["type"] == "retrieval" and e["phase"] == "fish"]
documents = {d["id"]: d for d in json.loads((args.run / "documents.json").read_text(encoding="utf-8"))}
sample = random.Random(args.seed).sample(retrievals, min(SAMPLE_SIZE, len(retrievals)))

for number, event in enumerate(sorted(sample, key=lambda e: (e["season"], e["agent"])), start=1):
    print(f"\n[{number}] season {event['season']}, agent {event['agent']}, sim_time {event['sim_time']}")
    print(f"situation: {event['query']}")
    print(f"{'score':<7}{'slot':<9}{'document':<26}{'excerpt':<{EXCERPT + 2}}relevance (0-2)")
    for hit in event["documents"]:
        excerpt = " ".join(documents[hit["id"]]["text"].split())[:EXCERPT]
        print(f"{hit['score']:<7.3f}{hit['slot']:<9}{hit['id']:<26}{excerpt:<{EXCERPT + 2}}____")
