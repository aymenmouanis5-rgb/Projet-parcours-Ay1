"""Compare every frozen-prompt run in runs/: `uv run python -m filets.report`."""

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from filets.indicator import records_from_log
from filets.prompts import PROMPT_VERSION

OLD_PROMISE_SEASONS = 3
REFERENCES = {
    "quota": "reference, not a competitor: the sustainable regrowth shared by N, chosen with knowledge of the lake",
    "rules": "reference, not a competitor: this rule takes 30% of the stock at any population, which cannot collapse the lake with r = 0.5",
}


def spread(values: list[float]) -> str:
    if not values:
        return "n/a"
    deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"{statistics.mean(values):.1f} ± {deviation:.1f}"


def events(run_dir: Path) -> list[dict]:
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def announcements(log: list[dict]) -> tuple[int, int]:
    """Count the catches above the announced amount, out of all announced catches."""
    announced = [e for e in log if e["type"] == "catch" and e["planned"] is not None]
    return sum(e["caught"] > e["planned"] + 0.05 for e in announced), len(announced)


def promise_citations(log: list[dict]) -> tuple[int, int, int, int]:
    """Decisions citing a retrieved promise: all promises, then those at least 3 seasons old."""
    decisions = [e for e in log if e["type"] == "decision" and e.get("retrieved_promise")]
    old = [e for e in decisions if e["promise_age"] >= OLD_PROMISE_SEASONS]
    return (sum(e["promise_cited"] for e in decisions), len(decisions),
            sum(e["promise_cited"] for e in old), len(old))


def time_violations(run_dir: Path, log: list[dict]) -> int:
    """C6: count retrieved documents that were not yet available at that moment."""
    path = run_dir / "documents.json"
    if not path.exists():
        return 0
    available_at = {d["id"]: d["sim_time"] for d in json.loads(path.read_text(encoding="utf-8"))}
    return sum(available_at[hit["id"]] >= e["sim_time"]
               for e in log if e["type"] == "retrieval" for hit in e["documents"])


def main() -> None:
    groups = defaultdict(list)
    ignored = 0
    for path in sorted(Path("runs").glob("*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("prompt_version") != PROMPT_VERSION:
            ignored += 1
            continue
        key = (summary["mode"], summary["model"] or "mixed", summary["hint"], summary["agents"],
               summary.get("timing", "sync"))
        groups[key].append((path.parent, summary))

    print(f"prompt version {PROMPT_VERSION}, {ignored} runs from other versions ignored")
    for (mode, model, hint, agents, timing), runs in sorted(groups.items()):
        summaries = [s for _, s in runs]
        logs = [events(d) for d, _ in runs]
        over = [announcements(log) for log in logs]
        kinds = Counter(e["kind"] for log in logs for e in log if e["type"] == "incident")
        survivors = [s for s in summaries if not s["collapsed"]]
        played = sum(s["seasons_played"] for s in summaries)
        print(f"\n{mode} / {model} / {'hint' if hint else 'no hint'} / {agents} fishers / {timing}: {len(runs)} runs, "
              f"statuses {dict(Counter(s['status'] for s in summaries))}")
        if mode in REFERENCES:
            print(f"  {REFERENCES[mode]}")
        print(f"  seasons survived  {spread([s['seasons_survived'] for s in summaries])}")
        print(f"  total catch       {spread([s['total_catch'] for s in summaries])}")
        print(f"  among survivors   {spread([s['total_catch'] for s in survivors])} ({len(survivors)} runs)")
        print(f"  final stock       {spread([s['final_stock'] for s in summaries])}")
        print(f"  mean stock        {spread([s['mean_stock'] for s in summaries])}")
        print(f"  safe violations   {sum(s['safe_violations'] for s in summaries)}/{played} seasons, "
              f"mean overshoot {spread([s['mean_overshoot'] for s in summaries])} tons")
        print(f"  over announcement {sum(o for o, _ in over)}/{sum(a for _, a in over)}")
        records = [r for d, _ in runs for r in records_from_log(d / "events.jsonl")]
        label = "misread (chance)" if not hint else "misread hint     "
        print(f"  {label} {sum(r['misread_hint'] for r in records)}/{len(records)} seasons"
              + (", chance baseline: the safe total was hidden" if not hint else ""))
        print(f"  hint derived      {sum(r['hint_derived'] for r in records)}/{len(records)} seasons")
        print(f"  llm calls         {spread([s['usage']['calls'] for s in summaries])}, "
              f"seconds {spread([s['usage']['seconds'] for s in summaries])}")
        print(f"  incidents         {dict(kinds)}")
        cited = [sum(values) for values in zip(*(promise_citations(log) for log in logs))]
        print(f"  promises cited    {cited[0]}/{cited[1]} decisions, old promises {cited[2]}/{cited[3]}")
        print(f"  largest prompt    {max(s['usage'].get('max_input_tokens', 0) for s in summaries)} tokens")
        print(f"  time violations   {sum(time_violations(d, log) for (d, _), log in zip(runs, logs))}")
        print(f"  events rejected   {sum(s.get('events_rejected', 0) for s in summaries)}")
        details = [s["timing_detail"] for s in summaries if "timing_detail" in s]
        if details:
            print(f"  late landings     {sum(d['late_landings'] for d in details)}/{sum(d['landings'] for d in details)}, "
                  f"missed turns {sum(d['missed_turns'] for d in details)}")
            print(f"  stock drift       {spread([d['mean_stock_drift'] for d in details])} tons, "
                  f"lag {spread([d['mean_lag_seasons'] for d in details])} seasons")


if __name__ == "__main__":
    main()
