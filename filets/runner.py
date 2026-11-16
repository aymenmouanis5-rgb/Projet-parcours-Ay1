"""Run one simulation in either timing mode and summarize it."""

import json
import random
import statistics
from dataclasses import asdict
from pathlib import Path

from filets import prompts
from filets.agent import HAMLETS, make_fishers
from filets.async_world import RealClock, run_async
from filets.bus import EventBus
from filets.indicator import write_records
from filets.knowledge import KnowledgeBase
from filets.lake import CAPACITY, Lake
from filets.llm import LLMClient
from filets.market import Market
from filets.sim import StepClock, World, run_sync

TIMINGS = ("sync", "async")


def timing_summary(agents: int, played: list[dict], landings: list[dict]) -> dict:
    """How out of date the asynchronous decisions were when they reached the lake."""
    drifts = [abs(item["stock_seen"] - item["stock_at_landing"]) for item in landings]
    return {
        "landings": len(landings),
        "late_landings": sum(item["landed_in"] != item["decided_in"] for item in landings),
        "missed_turns": agents * len(played) - len(landings),
        "mean_stock_drift": round(statistics.mean(drifts), 2) if drifts else None,
        "mean_lag_seasons": round(statistics.mean(item["lag"] for item in landings), 3) if landings else None,
    }


def summarize(agents, seasons, mode, model, seed, hint, timing, status, played, market, usage) -> dict:
    alive = [s for s in played if not s["collapsed"]]
    stocks = [s["stock"] for s in alive]
    violations = [s for s in played if s["overshoot"] > 0]
    return {
        "prompt_version": prompts.PROMPT_VERSION,
        "agents": agents, "mode": mode, "model": model, "seed": seed, "hint": hint, "timing": timing,
        "status": status, "seasons_planned": seasons, "seasons_played": len(played),
        "seasons_survived": len(alive), "collapsed": status == "collapsed",
        "total_catch": round(sum(s["total_caught"] for s in played), 2),
        "final_stock": round(played[-1]["stock"], 2) if played else None,
        # a dead lake counts as empty for the seasons it did not reach
        "mean_stock": round(sum(stocks) / seasons, 2),
        "safe_violations": len(violations),
        "violation_rate": round(len(violations) / len(played), 3) if played else None,
        "mean_overshoot": round(sum(s["overshoot"] for s in played) / len(played), 2) if played else None,
        "market": {hamlet: {"tons": round(account["tons"], 2), "revenue": round(account["revenue"], 2)}
                   for hamlet, account in market.ledger.items()},
        "seasons": [{k: round(v, 2) if isinstance(v, float) else v for k, v in s.items()} for s in played],
        "usage": usage,
    }


def run(agents: int, seasons: int, mode: str, seed: int, out: Path, model: str | None = None,
        hint: bool = True, timing: str = "sync", seconds_per_season: float = 20.0) -> dict:
    llm = LLMClient(seed)
    clock = RealClock(seconds_per_season) if timing == "async" else StepClock()
    log = EventBus(out.name, out / "events.jsonl", clock)
    knowledge = KnowledgeBase(llm) if mode in ("talk", "silent") else None
    world = World(mode, make_fishers(agents, model, hint), llm, Lake(), Market(HAMLETS), knowledge,
                  random.Random(seed), log, [CAPACITY], clock)
    played: list[dict] = []
    landings: list[dict] = []
    status = "crashed"
    log.write("run_started", 0, agents=agents, seasons=seasons, mode=mode, seed=seed, model=model,
              hint=hint, timing=timing, prompt_version=prompts.PROMPT_VERSION, stock=world.lake.stock)
    try:
        if timing == "async":
            status, landings = run_async(world, seasons, played)
        else:
            status = run_sync(world, seasons, played)
    finally:
        summary = summarize(agents, seasons, mode, model, seed, hint, timing, status, played, world.market,
                            asdict(llm.usage))
        if timing == "async":
            summary["timing_detail"] = timing_summary(agents, played, landings)
            summary["seconds_per_season"] = seconds_per_season
        log.write("run_ended", len(played), status=status, seasons_survived=summary["seasons_survived"],
                  total_catch=summary["total_catch"], final_stock=summary["final_stock"],
                  mean_stock=summary["mean_stock"], safe_violations=summary["safe_violations"])
        summary["events_rejected"] = log.close()
        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        write_records(out)
        if knowledge:
            knowledge.save(out / "documents.json")
    return summary
