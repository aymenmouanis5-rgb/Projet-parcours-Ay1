"""The world and its synchronous season loop: evening talk, fishing, market, regrowth, public report."""

import random
import re
import threading
from dataclasses import dataclass, field

from filets import prompts
from filets.agent import HAMLETS
from filets.bus import EventBus
from filets.knowledge import Document, KnowledgeBase
from filets.lake import BOAT_LIMIT, SUSTAINABLE_REGROWTH, Lake, safe_total
from filets.llm import LLMClient, LLMFailure
from filets.market import Market

MODES = ("talk", "silent", "rules", "quota")
STATED_CATCH = re.compile(
    r"(?:catch(?:ing)?|take|taking)\s+(?:about\s+|around\s+|only\s+|just\s+)?(\d+(?:\.\d+)?)", re.I)
CITES_PROMISE = re.compile(
    r"\b(?:i (?:had |have |already )?(?:promised|announced|said|told|agreed|committed)|i'd (?:promised|announced|said|told|agreed)|my (?:promise|word|announcement|commitment|pledge))\b", re.I)
SPEECH_PREFIX = re.compile(r"^(?:I'?d like to say|I would say)\s*:\s*", re.I)
RULE_NOISE = 0.2
REFERENCE_FLEET = 4
TREND_TOLERANCE = 1.0

# Simulated clock in synchronous mode: season + fraction of the season.
EVENING = 0.0
TALK_ENDS = 0.25
DAWN = 0.5
MARKET_CLOSES = 0.75


class StepClock:
    """Synchronous time: it only moves when the season loop moves it."""

    def __init__(self):
        self.moment = 0.0

    def set(self, moment: float) -> None:
        self.moment = moment

    def now(self) -> float:
        return self.moment


@dataclass
class World:
    mode: str
    fishers: list
    llm: LLMClient
    lake: Lake
    market: Market
    knowledge: KnowledgeBase | None
    rng: random.Random
    log: EventBus
    stocks: list[float]
    clock: object
    lock: threading.RLock = field(default_factory=threading.RLock)


def read_amount(value, stock: float) -> tuple[float, bool]:
    """Return a catch within what the boat and lake allow, and whether it had to be corrected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0, True
    amount = min(max(float(value), 0.0), BOAT_LIMIT, stock)
    return amount, amount != value


def states_other_amount(reasoning: str, amount) -> bool:
    """True when the reasoning names a catch different from the catch decided."""
    stated = STATED_CATCH.findall(reasoning)
    return (bool(stated) and isinstance(amount, (int, float))
            and abs(float(stated[-1]) - float(amount)) > 0.05)


def clean_message(text: str, name: str) -> str:
    """Remove the leftovers small models leave around their speech: JSON marks, labels, quotes."""
    text = re.sub(r"[{}\[\]]", "", text).strip()
    text = re.sub(rf"^{re.escape(name)}\s*:\s*", "", text)
    text = SPEECH_PREFIX.sub("", text)
    text = re.sub(r"(?<=[.!?])['\"]", "", text)
    return text.strip().strip("'\"").rstrip(",:; ")


def is_broken_message(text: str) -> bool:
    return len(text.split()) < 3


def lake_trend(stocks: list[float]) -> str:
    """Direction of the lake over the last season, ignoring small changes."""
    change = stocks[-1] - stocks[-2] if len(stocks) > 1 else 0.0
    if abs(change) <= TREND_TOLERANCE:
        return prompts.TREND_STEADY
    return prompts.TREND_RISING if change > 0 else prompts.TREND_FALLING


def cites_promise(reasoning: str, promise: Document) -> bool:
    """True when the reasoning explicitly mentions a promise or the season it was made.

    This detects a literal mention. It does not prove that the promise changed the decision.
    """
    return bool(CITES_PROMISE.search(reasoning)
                or re.search(rf"\bseason {int(promise.sim_time)}\b", reasoning, re.I))


def served_model(world: World, fisher, season: int, reply: dict) -> str | None:
    """Return the model Ollama says answered, and flag it if it is not the one requested."""
    served = reply.get("served_model")
    if served != fisher.profile.model:
        world.log.write("incident", season, agent=fisher.id, kind="model_mismatch",
                        requested=fisher.profile.model, served=served)
    return served


def recall(world: World, fisher, season: int, phase: str) -> tuple[str, Document | None]:
    """Retrieve what this fisher may know now: the text for the prompt, and his promise if any."""
    moment = world.clock.now()
    query = prompts.RETRIEVAL_QUERY.format(season=season, name=fisher.name, hamlet=fisher.hamlet,
                                           situation=fisher.profile.situation, stock=world.lake.stock,
                                           trend=lake_trend(world.stocks))
    try:
        hits = world.knowledge.search(query, fisher.id, moment)
    except LLMFailure:
        world.log.write("incident", season, agent=fisher.id, kind="retrieval_failed", phase=phase)
        return prompts.NOTHING_RECALLED, None
    world.log.write("retrieval", season, agent=fisher.id, phase=phase, sim_time=moment, query=query,
                    documents=[{"slot": slot, "id": doc.id, "score": round(score, 4)} for slot, doc, score in hits])
    promise = next((doc for slot, doc, _ in hits if slot == "promise"), None)
    return "\n\n".join(doc.text for _, doc, _ in hits) or prompts.NOTHING_RECALLED, promise


def remember(world: World, season: int, documents: list[Document]) -> None:
    try:
        world.knowledge.add(documents)
    except LLMFailure:
        world.log.write("incident", season, kind="indexing_failed", documents=[d.id for d in documents])


def speak(world: World, fisher, season: int, heard: list[str], plans: dict, indexed_at: float) -> Document | None:
    """One fisher speaks. Returns the personal document of his promise, if he was heard."""
    log, stock = world.log, world.lake.stock
    recalled, _ = recall(world, fisher, season, "talk")
    try:
        reply = fisher.talk(world.llm, season, stock, list(heard), recalled)
    except LLMFailure:
        log.write("incident", season, agent=fisher.id, kind="no_reply", phase="talk")
        return None
    planned, corrected = read_amount(reply["planned_catch"], stock)
    if corrected:
        log.write("incident", season, agent=fisher.id, kind="invalid_amount", phase="talk",
                  raw=reply["planned_catch"])
    message = clean_message(str(reply["message"]), fisher.name)
    if is_broken_message(message):
        log.write("incident", season, agent=fisher.id, kind="broken_message", raw=reply["message"])
        return None
    plans[fisher.id] = planned  # a plan exists only if the others actually heard it
    heard.append(prompts.HEARD_LINE.format(name=fisher.name, message=message, planned=planned))
    log.write("message", season, agent=fisher.id, text=message, planned_catch=planned, seed=reply["seed"],
              served_model=served_model(world, fisher, season, reply))
    return Document(id=f"said_s{season}_a{fisher.id}", type="own_promise", sim_time=indexed_at,
                    visibility="personal", owner=fisher.id,
                    text=prompts.PROMISE_DOC.format(season=season, message=message, planned=planned))


def talk_document(season: int, heard: list[str], indexed_at: float) -> Document:
    return Document(id=f"talk_s{season}", type="talk_summary", sim_time=indexed_at, visibility="shared",
                    text=prompts.TALK_DOC.format(season=season, lines=" ".join(heard)))


def evening(world: World, season: int) -> dict[int, float]:
    world.clock.set(season + EVENING)
    heard, plans, documents = [], {}, []
    for fisher in world.rng.sample(world.fishers, len(world.fishers)):
        promise = speak(world, fisher, season, heard, plans, season + TALK_ENDS)
        if promise:
            documents.append(promise)
    for fisher in world.fishers:
        fisher.last_talk = heard
    if heard:
        documents.append(talk_document(season, heard, season + TALK_ENDS))
    remember(world, season, documents)
    return plans


def decide(world: World, fisher, season: int) -> float:
    """One fisher chooses his catch, seeing the lake as it is now."""
    log, stock = world.log, world.lake.stock
    recalled, promise = recall(world, fisher, season, "fish")
    try:
        reply = fisher.fish(world.llm, season, stock, recalled)
        if states_other_amount(str(reply["reasoning"]), reply["catch"]):
            log.write("incident", season, agent=fisher.id, kind="reasoning_mismatch",
                      reasoning=reply["reasoning"], raw=reply["catch"])
        amount, corrected = read_amount(reply["catch"], stock)
        if corrected:
            log.write("incident", season, agent=fisher.id, kind="invalid_amount", phase="fish",
                      raw=reply["catch"])
    except LLMFailure:
        log.write("incident", season, agent=fisher.id, kind="no_reply", phase="fish")
        reply, amount = {"reasoning": None}, 0.0
    reasoning = reply["reasoning"]
    log.write("decision", season, agent=fisher.id, model=fisher.profile.model,
              served_model=served_model(world, fisher, season, reply) if reasoning is not None else None,
              requested=amount, reasoning=reasoning, safe_total=safe_total(stock), seed=reply.get("seed"),
              retrieved_promise=promise.id if promise else None,
              promise_age=season - int(promise.sim_time) if promise else None,
              promise_cited=bool(promise and reasoning and cites_promise(str(reasoning), promise)))
    return amount


def dawn(world: World, season: int) -> list[float]:
    return [decide(world, fisher, season) for fisher in world.fishers]


def rule_dawn(world: World, season: int) -> list[float]:
    """Baseline: each profile takes a fixed share of the stock, with a little seeded noise.

    Shares are scaled by 4/N, so the rule takes 30% of the stock on average for any
    population. With r = 0.5 it cannot collapse the lake, since a nearly empty lake still
    grows by 0.7 * 1.5 = 1.05 per season. It is therefore a reference, not a competitor.
    """
    scale = REFERENCE_FLEET / len(world.fishers)
    requested = []
    for fisher in world.fishers:
        share = fisher.profile.rule_share * scale
        amount, _ = read_amount(world.lake.stock * share
                                * world.rng.uniform(1 - RULE_NOISE, 1 + RULE_NOISE), world.lake.stock)
        requested.append(amount)
        world.log.write("decision", season, agent=fisher.id, model="rules", requested=amount,
                        rule=f"take {share:.1%} of the stock",
                        safe_total=safe_total(world.lake.stock))
    return requested


def quota_dawn(world: World, season: int) -> list[float]:
    """Baseline: everyone takes an equal part of the sustainable regrowth, whatever the lake's state.

    Scaled by 1/N, so the total stays at the most the lake can regrow for any population.
    """
    quota = SUSTAINABLE_REGROWTH / len(world.fishers)
    requested = []
    for fisher in world.fishers:
        amount, _ = read_amount(quota, world.lake.stock)
        requested.append(amount)
        world.log.write("decision", season, agent=fisher.id, model="quota", requested=amount,
                        rule=f"take {quota:.2f} tons", safe_total=safe_total(world.lake.stock))
    return requested


def choose_catches(world: World, season: int) -> list[float]:
    world.clock.set(season + DAWN)
    if world.mode == "rules":
        return rule_dawn(world, season)
    if world.mode == "quota":
        return quota_dawn(world, season)
    return dawn(world, season)


def sell_catches(world: World, season: int, caught: list[float]) -> float:
    """Sell each catch at its hamlet's market, and index the ledgers when the market closes."""
    landings = [{"agent": f.id, "name": f.name, "hamlet": f.hamlet, "tons": c}
                for f, c in zip(world.fishers, caught)]
    current, sales = world.market.sell(season, landings)
    for sale in sales:
        world.log.write("sale", season, agent=sale["agent"], hamlet=sale["hamlet"], tons=sale["tons"],
                        price=sale["price"], revenue=sale["revenue"])
    if world.knowledge:
        ledgers = []
        for hamlet in HAMLETS:
            local = [s for s in sales if s["hamlet"] == hamlet]
            lines = " ".join(prompts.LEDGER_LINE.format(**s) for s in local)
            ledgers.append(Document(
                id=f"ledger_s{season}_{hamlet}", type="market_ledger", hamlet=hamlet, visibility="shared",
                sim_time=world.clock.now(),
                text=prompts.LEDGER_DOC.format(hamlet=hamlet, season=season, lines=lines, price=current,
                                               revenue=sum(s["revenue"] for s in local))))
        remember(world, season, ledgers)
    return current


def finish_season(world: World, season: int, caught: list[float], plans: dict, limit: float,
                  played: list[dict]) -> None:
    """Close a season: market, regrowth unless the lake died, and the public report."""
    fishers, lake, log = world.fishers, world.lake, world.log
    total = sum(caught)
    current = sell_catches(world, season, caught)
    collapsed = lake.collapsed  # the lake dies when fishing leaves it too low, before any regrowth
    if not collapsed:
        lake.regrow()
    overshoot = max(0.0, total - limit)
    log.write("lake", season, stock=lake.stock, total_caught=total, safe_total=limit,
              safe_violation=overshoot > 0, overshoot=overshoot)
    world.stocks.append(lake.stock)
    played.append({"season": season, "stock": lake.stock, "total_caught": total, "price": current,
                   "safe_total": limit, "overshoot": overshoot, "collapsed": collapsed})

    report = ", ".join(
        prompts.CATCH_WITH_PLAN.format(name=f.name, planned=plans[f.id], caught=c) if f.id in plans
        else prompts.CATCH_NO_PLAN.format(name=f.name, caught=c)
        for f, c in zip(fishers, caught))
    for fisher in fishers:
        fisher.history.append(prompts.SEASON_LINE.format(season=season, report=report, price=current,
                                                         stock=lake.stock))
    print(f"season {season:>2}: caught {total:6.1f} at {current:4.1f} ({report}) -> lake {lake.stock:6.1f}",
          flush=True)


def play_season(world: World, season: int, played: list[dict]) -> None:
    plans = evening(world, season) if world.mode == "talk" else {}
    requested = choose_catches(world, season)
    limit = safe_total(world.lake.stock)
    caught = world.lake.fish(requested)
    for fisher, amount in zip(world.fishers, caught):
        world.log.write("catch", season, agent=fisher.id, caught=amount, planned=plans.get(fisher.id))
    world.clock.set(season + MARKET_CLOSES)
    finish_season(world, season, caught, plans, limit, played)


def run_sync(world: World, seasons: int, played: list[dict]) -> str:
    for season in range(1, seasons + 1):
        play_season(world, season, played)
        if played[-1]["collapsed"]:
            world.log.write("collapse", season, stock=world.lake.stock)
            return "collapsed"
    return "completed"
