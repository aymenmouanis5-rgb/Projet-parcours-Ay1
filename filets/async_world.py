"""Asynchronous mode: each fisher lives on his own thread, at the pace of his real LLM latency.

The simulated clock follows the wall clock, and the seasons close whether or not everyone
has acted. A fisher acts at most once per season. A slow reply lands on a lake that has
changed since he looked at it, possibly in the next season, and costs him his next turn.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

from filets.lake import safe_total
from filets.sim import World, decide, finish_season, read_amount, remember, speak, talk_document

POLL_SECONDS = 0.05


class RealClock:
    """Simulated time derived from the wall clock, starting at season 1."""

    def __init__(self, seconds_per_season: float):
        self.seconds_per_season = seconds_per_season
        self.started = time.monotonic()

    def now(self) -> float:
        return 1 + (time.monotonic() - self.started) / self.seconds_per_season

    def seconds_until(self, moment: float) -> float:
        return max(0.0, (moment - self.now()) * self.seconds_per_season)


@dataclass
class Shared:
    """What the threads share during a run."""

    stop: threading.Event = field(default_factory=threading.Event)
    heard: dict = field(default_factory=lambda: defaultdict(list))
    plans: dict = field(default_factory=lambda: defaultdict(dict))
    caught: dict = field(default_factory=lambda: defaultdict(dict))
    landings: list = field(default_factory=list)
    failure: BaseException | None = None


def land(world: World, shared: Shared, fisher, decided_in: int, amount: float, stock_seen: float,
         seen_at: float) -> None:
    """Apply a catch to the lake as it is now, not as the fisher saw it."""
    with world.lock:
        if shared.stop.is_set():
            return
        moment = world.clock.now()
        season = int(moment)
        stock_now = world.lake.stock
        amount, _ = read_amount(amount, stock_now)
        caught = world.lake.fish([amount])[0]
        shared.caught[season][fisher.id] = caught
        shared.landings.append({"agent": fisher.id, "decided_in": decided_in, "landed_in": season,
                                "stock_seen": stock_seen, "stock_at_landing": stock_now,
                                "lag": moment - seen_at})
        world.log.write("catch", season, agent=fisher.id, caught=caught,
                        planned=shared.plans[decided_in].get(fisher.id), decided_in=decided_in,
                        stock_seen=stock_seen, stock_at_landing=stock_now, seen_at=seen_at)
        if world.lake.collapsed:
            shared.stop.set()


def act(world: World, shared: Shared, fisher, season: int) -> None:
    if world.mode == "talk":
        promise = speak(world, fisher, season, shared.heard[season], shared.plans[season], world.clock.now())
        if promise:
            remember(world, season, [promise])
    fisher.last_talk = list(shared.heard[season])
    seen_at, stock_seen = world.clock.now(), world.lake.stock
    amount = decide(world, fisher, season)
    land(world, shared, fisher, season, amount, stock_seen, seen_at)


def fisher_loop(world: World, shared: Shared, fisher, seasons: int) -> None:
    next_season = 1
    try:
        while not shared.stop.is_set():
            season = int(world.clock.now())
            if season > seasons:
                return
            if season < next_season:
                shared.stop.wait(POLL_SECONDS)
                continue
            act(world, shared, fisher, season)
            next_season = int(world.clock.now()) + 1
    except BaseException as failure:
        shared.failure = failure
        shared.stop.set()


def close_season(world: World, shared: Shared, season: int, opening_stock: float, played: list[dict]) -> None:
    with world.lock:
        caught = [shared.caught[season].get(fisher.id, 0.0) for fisher in world.fishers]
        heard = list(shared.heard[season])
        if heard and world.knowledge:
            remember(world, season, [talk_document(season, heard, world.clock.now())])
        finish_season(world, season, caught, shared.plans[season], safe_total(opening_stock), played)


def run_async(world: World, seasons: int, played: list[dict]) -> tuple[str, list[dict]]:
    shared = Shared()
    threads = [threading.Thread(target=fisher_loop, args=(world, shared, fisher, seasons), daemon=True)
               for fisher in world.fishers]
    for thread in threads:
        thread.start()

    status = "completed"
    for season in range(1, seasons + 1):
        opening_stock = world.lake.stock
        shared.stop.wait(world.clock.seconds_until(season + 1))
        if shared.failure:
            raise shared.failure
        close_season(world, shared, season, opening_stock, played)
        if played[-1]["collapsed"]:
            world.log.write("collapse", season, stock=world.lake.stock)
            status = "collapsed"
            break
    shared.stop.set()
    for thread in threads:
        thread.join()
    return status, shared.landings
