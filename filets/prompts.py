"""Every text the agents can read. Changing any of it requires bumping PROMPT_VERSION."""

from filets.lake import BOAT_LIMIT, CAPACITY

PROMPT_VERSION = 2

WORLD = f"""You live in a closed valley around Lake Vellmor, its only source of fish.
Four hamlets share it. All amounts are in tons of fish.
The lake holds at most {CAPACITY:.0f} tons. It refills on its own after each season{{refill}}. If it falls below 5 tons it is dead.
A boat carries at most {BOAT_LIMIT:.0f} tons a season. Each catch is sold at the hamlet's market.
Nobody owns the lake. There are NO laws, authorities, permits or quotas: never invent any.
Only rely on the facts given here and on your memories. Speak only as yourself, in the first person."""

REFILL_DETAIL = ", fastest when about half full, and slowly when nearly full or nearly empty"

IDENTITY = "{world}\n\nYou are {name} of {hamlet}. {background}"

LAKE_STATE = "The lake holds {stock:.1f} tons."
LAKE_HINT = (" To leave it at least half full, all fishers together can take at most {safe:.1f} tons "
             "this season, which is {share:.1f} tons per fisher if shared equally.")

TALK = """Season {season}, evening at the elder's house. {lake}
Past seasons:
{memories}

What you recall:
{recalled}

Said tonight:
{tonight}

Write your exact words to the others in one or two complete sentences, and state how many tons you plan to catch."""

FISH = """Season {season}, dawn. {lake}
Past seasons:
{memories}

What you recall:
{recalled}

Said last evening:
{talk}

Everyone will learn your catch after the season. Give your private reasoning in one sentence, then give the number of tons you catch."""

NOTHING_YET = "Nothing yet."
NOBODY_SPOKE = "Nobody has spoken yet."
NOTHING_SAID = "Nothing was said."
NOTHING_RECALLED = "Nothing comes to mind."

HEARD_LINE = '{name}: "{message}" (plans {planned:.1f} tons)'
CATCH_WITH_PLAN = "{name} announced {planned:.1f} and caught {caught:.1f}"
CATCH_NO_PLAN = "{name} caught {caught:.1f}"
SEASON_LINE = ("Season {season}: {report}. Market price: {price:.1f} coins a ton. "
               "Lake after refill: {stock:.1f} tons.")

RETRIEVAL_QUERY = "Season {season}. {name} of {hamlet}, {situation}. The lake holds {stock:.1f} tons and is {trend}."
TREND_RISING = "rising"
TREND_FALLING = "falling"
TREND_STEADY = "steady"

LEDGER_DOC = ("{hamlet} market ledger, season {season}. {lines} "
              "Price this season: {price:.1f} coins a ton. Market total for the season: {revenue:.1f} coins.")
LEDGER_LINE = "{name} sold {tons:.1f} tons for {revenue:.1f} coins."
TALK_DOC = "Evening talk at the elder's house, season {season}. {lines}"
PROMISE_DOC = 'Season {season}, at the evening talk I said: "{message}" I announced I would catch {planned:.1f} tons.'
