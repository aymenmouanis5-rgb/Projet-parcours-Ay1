A common context exists when, for at least two consecutive seasons: (1) at least 3 of 4 fishermen refer in their messages to the same catch rule (e.g. '5 tons each', 'keep the lake half full'); (2) their announced catches converge on that rule; (3) their actual catches respect it. Point 3 separates a norm from a coincidence.

## Indicator (B2)

`filets/indicator.py` computes this from events only, one record per closed season. Each run writes `indicator.jsonl`; `uv run python -m filets.indicator runs/<run>` rebuilds it from the log.

| Value | Definition | Holds when |
|---|---|---|
| Dominant rule | The collective limit most mentioned in the season's messages | One exists |
| Mention share | Fishers whose message states that limit, out of all fishers | At least 75% |
| Announced | Per-person rule: standard deviation of announced catches. Group rule: their sum | Per person: spread at most 1.5 tons and at least 75% announce within the rule. Group: the sum stays within the limit (+0.05 t) |
| Respect share | Fishers whose **requested** amount (`decision` event) keeps to the rule, out of all fishers | At least 75% |

Respect uses the amount each fisher asked for, not what landed. When the lake runs low, every catch is cut, and that rationing must not count as restraint. `requested_sum` and `caught_sum` are both reported.

**Each or total, once per season.** Mentions are counted by number, so "8 tons" said four times is one rule however each speaker meant it. Its kind is then settled by majority of the mentioners: a mentioner who says "each", "per fisher", "per person", "all" or "everyone" votes per person, one who says "in total", "together" or "combined" votes total, and one who says neither votes by their own plan (above a fair share, the limit divided by the number of fishers, means per person). A tie goes to the mentioners' mean plan against the fair share. "Keep the lake half full" is a group rule whose limit is the safe total.

A per-person rule is judged fisher by fisher. A group rule is judged on the sum, so every fisher passes or fails together, and unequal shares are fine. `rule_limit` is the tons stated, never an equal share.

Common context is flagged when all of these hold for 2 consecutive seasons **on the same rule**. A change of rule restarts the count, because a norm has to last.

A rule must address the group. "I plan to catch 5 tons" is a personal plan, and "I agree with Ines" states no rule, so neither counts as a mention. Detection uses text patterns, so it can miss rephrased rules.

### Hint flags

Prompts are frozen at version 2. These flags measure how much of an agreement comes from the prompt; they are results, not bugs to fix.

- `echoes_hint`: the rule is one the prompt gave: keeping the lake half full, or the safe total or its equal share. Always false without the hint.
- `misread_hint`: a per-person rule uses the safe total, the number for the whole group, within 0.15 tons. With a safe total of 8 tons, "8 tons each" allows four times too much. The two flags exclude each other.
- `hint_derived`: `echoes_hint` or `misread_hint`, in a run with the hint. A common context on such a rule does not show that the fishers invented it.
- `misread_baseline`: true in `--no-hint` runs. The safe total was hidden there, but `misread_hint` is still computed against it, so its rate is the chance of landing on that number without being told. `filets.report` prints it as `misread (chance)`, to compare with the hint runs. `hint_derived` stays false.

`sources` lists the event ids behind each value. Logs older than schema 8 have no ids, so the indicator uses their position in the log, such as `#12`.
