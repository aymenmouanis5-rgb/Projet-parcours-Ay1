"""LLM fishermen: profile, memory, and the two decisions they make each season."""

from dataclasses import dataclass, field, replace

from filets import prompts
from filets.lake import safe_total
from filets.llm import LLMClient

LARGE_MODEL = "llama3.2:3b"
SMALL_MODEL = "llama3.2:1b"
MEMORY_SEASONS = 2
TALK_CALL = 0  # call index of each LLM call a fisher makes in a season
FISH_CALL = 1
HAMLETS = ["Ostrel", "Tilque", "Bramois", "Hennad"]
NAMES = ["Mara", "Nils", "Tomas", "Ines", "Lena", "Oskar", "Ada", "Emil", "Sana", "Rurik", "Vera", "Bram"]

TALK_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "planned_catch": {"type": "number", "minimum": 0},
    },
    "required": ["message", "planned_catch"],
}

FISH_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "catch": {"type": "number", "minimum": 0},
    },
    "required": ["reasoning", "catch"],
}


@dataclass(frozen=True)
class Profile:
    model: str
    background: str
    situation: str  # own debt or need, used to build retrieval queries
    rule_share: float  # part of the stock this profile takes in the 4-fisher proportional rule


PROFILES = [
    Profile(LARGE_MODEL, "Your family has fished here for generations and lived through a famine. "
                         "You need 2 tons a season to live.",
            "no debt, needing 2 tons a season to live", 0.05),
    Profile(SMALL_MODEL, "You arrived recently and are in debt. You need 5 tons a season to repay it, "
                         "and you think about this season more than the next decade.",
            "in debt, needing 5 tons a season to repay it", 0.10),
    Profile(LARGE_MODEL, "You are an elder the valley respects, though you hold no official power. "
                         "You need 2 tons a season to live.",
            "no debt, needing 2 tons a season to live", 0.05),
    Profile(SMALL_MODEL, "You arrived recently with a loan on your boat. You need 5 tons a season to repay it, "
                         "and you say less than you think.",
            "in debt on a boat loan, needing 5 tons a season to repay it", 0.10),
]


def fisher_name(index: int) -> str:
    """Unique name for any population size: Mara, ..., Bram, then Mara2, ..."""
    base = NAMES[index % len(NAMES)]
    round_ = index // len(NAMES)
    return f"{base}{round_ + 1}" if round_ else base


@dataclass
class Fisher:
    id: int
    name: str
    hamlet: str
    profile: Profile
    fleet: int
    hint: bool
    history: list[str] = field(default_factory=list)
    last_talk: list[str] = field(default_factory=list)

    def _system(self) -> str:
        world = prompts.WORLD.format(refill=prompts.REFILL_DETAIL if self.hint else "")
        return prompts.IDENTITY.format(world=world, name=self.name, hamlet=self.hamlet,
                                       background=self.profile.background)

    def _memories(self) -> str:
        return "\n".join(self.history[-MEMORY_SEASONS:]) or prompts.NOTHING_YET

    def _lake_state(self, stock: float) -> str:
        state = prompts.LAKE_STATE.format(stock=stock)
        if self.hint:
            safe = safe_total(stock)
            state += prompts.LAKE_HINT.format(safe=safe, share=safe / self.fleet)
        return state

    def talk(self, llm: LLMClient, season: int, stock: float, heard: list[str], recalled: str) -> dict:
        user = prompts.TALK.format(season=season, lake=self._lake_state(stock), memories=self._memories(),
                                   recalled=recalled, tonight="\n".join(heard) or prompts.NOBODY_SPOKE)
        return llm.ask(self.profile.model, self._system(), user, TALK_SCHEMA, season, self.id, TALK_CALL)

    def fish(self, llm: LLMClient, season: int, stock: float, recalled: str) -> dict:
        user = prompts.FISH.format(season=season, lake=self._lake_state(stock), memories=self._memories(),
                                   recalled=recalled, talk="\n".join(self.last_talk) or prompts.NOTHING_SAID)
        return llm.ask(self.profile.model, self._system(), user, FISH_SCHEMA, season, self.id, FISH_CALL)


def make_fishers(count: int, model: str | None = None, hint: bool = True) -> list[Fisher]:
    """Create fishers, rotating through the profiles and the four hamlets."""
    fishers = [Fisher(i, fisher_name(i), HAMLETS[i % len(HAMLETS)], PROFILES[i % len(PROFILES)], count, hint)
               for i in range(count)]
    if model:
        for fisher in fishers:
            fisher.profile = replace(fisher.profile, model=model)
    return fishers
