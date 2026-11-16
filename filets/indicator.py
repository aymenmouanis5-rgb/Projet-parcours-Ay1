"""B1 emergence indicator, computed only from events. See docs/B1_contexte_commun.md.

Feed events one at a time to EmergenceIndicator.add(): this module imports nothing from the
simulation, so the viewer, the Godot bridge and a finished run's log all use the same code.

`uv run python -m filets.indicator runs/<run>` writes runs/<run>/indicator.jsonl.
"""

import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

MENTION_SHARE = 0.75  # at least 3 of 4 fishers, scaled to the population
RESPECT_SHARE = 0.75
SPREAD_LIMIT = 1.5  # tons, standard deviation of the announced catches
CONSECUTIVE_SEASONS = 2
TOLERANCE = 0.05  # tons
HINT_MARGIN = 0.15  # tons, the rounding of a share the prompt gave

NUMBER = r"(\d+(?:\.\d+)?)"
TONS = rf"{NUMBER}\s*tons?\b"
HALF = re.compile(r"half[- ]full|half (?:of )?(?:the )?lake|at least half", re.I)
EACH = re.compile(rf"{TONS}\s+(?:each|apiece|per fisher|per person|per boat)\b"
                  rf"|\beach\s+(?:of us\s+)?(?:take|catch|fish)\w*\s+(?:about\s+|only\s+|just\s+)?{TONS}", re.I)
CAPPED = re.compile(rf"(?:no more than|not more than|more than|at most|maximum of|max of|limit of|up to|"
                    rf"under|below|less than|only|just)\s+(?:about\s+)?{TONS}", re.I)
AIMED = re.compile(rf"(?:let'?s|we should|we must|we can|we could|we need to)\b[^.!?;]*?{TONS}", re.I)
COLLECTIVE = re.compile(r"\b(?:we|us|our|everyone|everybody|all|each|let'?s|together)\b", re.I)
TOTAL = re.compile(r"\b(?:in total|total|together|between us|combined|in all)\b", re.I)
PER_FISHER = re.compile(r"\b(?:each|apiece|per fisher|per person|per boat|all|everyone|everybody)\b", re.I)
AMOUNT_LEFT = re.compile(r"\b(?:leave|leaves|left|remain\w*|hold\w*)\b", re.I)
PERSONAL_PLAN = re.compile(r"\bI(?:'ll|'m|'d| will| plan| am| would| aim| need| want| can)\b", re.I)
FLOOR = re.compile(r"\bat least\s+$", re.I)


def plan_vote(word: str | None, tons: float, planned: float, fleet: int) -> str:
    """How one mentioner reads a limit. A word ("each", "in total") decides; without one, the
    speaker's own plan does: planning above a fair share means they read it per person."""
    if word:
        return word
    return "each" if planned > tons / fleet else "total"


def find_limits(text: str) -> dict:
    """The collective limits a message states, as {tons: word}, plus {"half": None}.

    The word is "each" or "total" when the message says which, else None: the kind is then
    settled once per season by the mentioners' plans (see classify). A personal plan such as
    "I plan to catch 5 tons" is not a rule: a rule has to address the group. "I agree with
    Ines" restates nothing, so it does not count as a mention. Numbers are read clause by
    clause, so that a plan or the lake's stock mentioned next to "we" is not taken for a rule.
    """
    limits: dict = {}
    if HALF.search(text):
        limits["half"] = None
    for clause in re.split(r"[.!?;,]\s+|[.!?;,]$", text):
        for match in EACH.finditer(clause):
            if not FLOOR.search(clause[:match.start()]):
                limits[float(match.group(1) or match.group(2))] = "each"
        if AMOUNT_LEFT.search(clause) or not COLLECTIVE.search(clause) or PERSONAL_PLAN.search(clause):
            continue
        word = "total" if TOTAL.search(clause) else "each" if PER_FISHER.search(clause) else None
        for pattern in (CAPPED, AIMED):
            for match in pattern.finditer(clause):
                if not FLOOR.search(clause[:match.start(1)]):
                    tons = float(match.group(1))
                    if limits.get(tons) is None:
                        limits[tons] = word
    return limits


def extract_rules(text: str, planned: float, fleet: int) -> set[tuple[str, float | None]]:
    """The rules one message states, each read with this speaker's plan alone, as (kind, tons)."""
    return {("half", None) if key == "half" else (plan_vote(word, key, planned, fleet), key)
            for key, word in find_limits(text).items()}


def classify(tons: float, mentions: list[tuple[str | None, float]], fleet: int) -> str:
    """Settle each/total once per season, by majority of the mentioners' readings.
    A tie goes to the mentioners' mean plan against a fair share."""
    votes = Counter(plan_vote(word, tons, planned, fleet) for word, planned in mentions)
    if votes["each"] != votes["total"]:
        return "each" if votes["each"] > votes["total"] else "total"
    mean_plan = sum(planned for _, planned in mentions) / len(mentions)
    return "each" if mean_plan > tons / fleet else "total"


def rule_limit(rule: tuple[str, float | None], safe_total: float) -> float:
    """The tons a rule allows: to one fisher for an "each" rule, otherwise to the whole group."""
    kind, tons = rule
    return safe_total if kind == "half" else tons


def within_rule(rule: tuple[str, float | None] | None, limit: float | None, items: list[dict], field: str) -> list[dict]:
    """The items that keep to a rule. A group limit is judged on the sum, not on equal shares."""
    if rule is None:
        return []
    if rule[0] == "each":
        return [item for item in items if item[field] <= limit + TOLERANCE]
    return items if sum(item[field] for item in items) <= limit + TOLERANCE else []


def echoes_hint(rule: tuple[str, float | None], fleet: int, safe_total: float, hint: bool) -> bool:
    """True when the prompt itself gave this rule, so agreeing on it does not show emergence."""
    if not hint:
        return False
    kind, tons = rule
    return kind == "half" or abs(tons - (safe_total if kind == "total" else safe_total / fleet)) <= HINT_MARGIN


def misread_hint(rule: tuple[str, float | None], fleet: int, safe_total: float, hint: bool) -> bool:
    """True when a per-person rule uses the safe total, the number for the whole group.

    With the hint, the prompt gave that number. Without it, the safe total is hidden, so a match
    is chance: the same test then gives the chance baseline for the hint runs."""
    kind, tons = rule
    return (kind == "each" and abs(tons - safe_total) <= HINT_MARGIN
            and not echoes_hint(rule, fleet, safe_total, hint))


def rule_label(rule: tuple[str, float | None]) -> str:
    kind, tons = rule
    if kind == "half":
        return "keep the lake half full"
    return f"{tons:g} tons in total" if kind == "total" else f"{tons:g} tons each"


class EmergenceIndicator:
    """Follows one run at a time and yields one record each time a season closes."""

    def __init__(self):
        self._reset()

    def _reset(self) -> None:
        self.run = None
        self.fleet = 4
        self.hint = True
        self.position = 0
        self.messages: dict[int, list[dict]] = {}
        self.decisions: dict[int, list[dict]] = {}
        self.catches: dict[int, list[dict]] = {}
        self.streak = 0
        self.last_rule = None
        self.records: list[dict] = []

    def add(self, event: dict) -> dict | None:
        """Take one event, and return a record if it closed a season."""
        kind = event.get("type")
        if kind == "run_started":
            self._reset()
            self.run = event.get("run")
            self.fleet = event.get("agents", 4)
            self.hint = event.get("hint", True)
        self.position += 1
        source = event.get("id", f"#{self.position}")  # logs older than schema 8 have no ids
        if kind == "message":
            self.messages.setdefault(event["season"], []).append({**event, "source": source})
        elif kind == "decision":  # logged in the season it was decided, even if it lands later
            self.decisions.setdefault(event["season"], []).append({**event, "source": source})
        elif kind == "catch":
            season = event.get("decided_in", event["season"])
            self.catches.setdefault(season, []).append({**event, "source": source})
        elif kind == "lake":
            return self._close_season(event, source)
        return None

    def _dominant_rule(self, messages: list[dict]) -> tuple[tuple[str, float | None] | None, list[dict]]:
        """The most mentioned limit, its kind settled once for the season, and who mentioned it."""
        limits_of = [(m, find_limits(m["text"])) for m in messages]
        counts = Counter(key for _, limits in limits_of for key in limits)
        if not counts:
            return None, []
        key = counts.most_common(1)[0][0]
        mentioning = [(m, limits[key]) for m, limits in limits_of if key in limits]
        if key == "half":
            return ("half", None), [m for m, _ in mentioning]
        kind = classify(key, [(word, m["planned_catch"]) for m, word in mentioning], self.fleet)
        return (kind, key), [m for m, _ in mentioning]

    def _close_season(self, lake: dict, lake_source: str) -> dict:
        season = lake["season"]
        messages = self.messages.get(season, [])
        decisions = self.decisions.get(season, [])
        catches = self.catches.get(season, [])
        needed = math.ceil(MENTION_SHARE * self.fleet)
        rule, mentioning = self._dominant_rule(messages)

        planned = [m["planned_catch"] for m in messages]
        safe_total = lake.get("safe_total", 0.0)
        limit = rule_limit(rule, safe_total) if rule else None
        # Respect is judged on what each fisher asked for: a catch cut short by an empty lake
        # is rationing, not restraint.
        respecting = within_rule(rule, limit, decisions, "requested")

        mention_share = len(mentioning) / self.fleet
        spread = statistics.pstdev(planned) if len(planned) > 1 else None
        within = within_rule(rule, limit, messages, "planned_catch")
        respect_share = len(respecting) / self.fleet if rule else 0.0
        if rule and rule[0] == "each":  # announcements converge on a per-person rule
            announced = spread is not None and spread <= SPREAD_LIMIT and len(within) >= needed
        else:  # a group rule allows unequal shares, so only their sum counts
            announced = bool(rule) and bool(planned) and sum(planned) <= limit + TOLERANCE
        holds = {
            "mention": len(mentioning) >= needed,
            "announced": announced,
            "respect": bool(rule) and respect_share >= RESPECT_SHARE,
        }
        if all(holds.values()):  # a norm has to last: a new rule starts the count again
            self.streak = self.streak + 1 if rule == self.last_rule else 1
        else:
            self.streak = 0
        self.last_rule = rule
        echoes = bool(rule) and echoes_hint(rule, self.fleet, safe_total, self.hint)
        misread = bool(rule) and misread_hint(rule, self.fleet, safe_total, self.hint)
        record = {
            "run": self.run, "season": season, "hint": self.hint,
            "rule": rule_label(rule) if rule else None,
            "rule_kind": rule[0] if rule else None,
            "rule_limit": round(limit, 2) if rule else None,
            "echoes_hint": echoes,
            "misread_hint": misread,
            # Without the hint the safe total was hidden, so a misread there is a chance baseline.
            "misread_baseline": not self.hint,
            "hint_derived": echoes or (misread and self.hint),
            "mention_share": round(mention_share, 3),
            "announced_spread": round(spread, 2) if spread is not None else None,
            "announced_within": len(within),
            "announced_sum": round(sum(planned), 2),
            "requested_sum": round(sum(d["requested"] for d in decisions), 2),
            "caught_sum": round(sum(c["caught"] for c in catches), 2),
            "respect_share": round(respect_share, 3),
            "holds": holds,
            "streak": self.streak,
            "common_context": self.streak >= CONSECUTIVE_SEASONS,
            "sources": {
                "mention_share": [m["source"] for m in mentioning],
                "announced": [m["source"] for m in messages],
                "respect_share": [d["source"] for d in decisions],
                "rule_limit": [lake_source],
            },
        }
        self.records.append(record)
        return record


def records_from_log(path: Path) -> list[dict]:
    indicator = EmergenceIndicator()
    for line in path.read_text(encoding="utf-8").splitlines():
        indicator.add(json.loads(line))
    return indicator.records


def write_records(run_dir: Path) -> list[dict]:
    records = records_from_log(run_dir / "events.jsonl")
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    (run_dir / "indicator.jsonl").write_text(lines, encoding="utf-8")
    return records


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    for item in write_records(folder):
        print(f"season {item['season']:>2}: rule {item['rule']}, mention {item['mention_share']:.0%}, "
              f"spread {item['announced_spread']}, respect {item['respect_share']:.0%}, "
              f"common context {item['common_context']}, misread hint {item['misread_hint']}"
              + (" (chance baseline)" if item["misread_baseline"] else ""))
