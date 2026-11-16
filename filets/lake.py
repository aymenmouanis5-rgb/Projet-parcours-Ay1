"""The lake is plain deterministic code, never an LLM."""

from dataclasses import dataclass

CAPACITY = 100.0
GROWTH_RATE = 0.5
COLLAPSE_LEVEL = 5.0
BOAT_LIMIT = 20.0
SUSTAINABLE_REGROWTH = GROWTH_RATE * CAPACITY / 4  # the most the lake can regrow in a season, at half capacity


def regrowth(stock: float) -> float:
    """Logistic growth: fastest at half capacity, slow when nearly full or empty."""
    return GROWTH_RATE * stock * (1 - stock / CAPACITY)


def safe_total(stock: float) -> float:
    """Largest total catch that leaves the lake at least half full, where it regrows best."""
    return max(0.0, stock - CAPACITY / 2)


@dataclass
class Lake:
    stock: float = CAPACITY

    def fish(self, requested: list[float]) -> list[float]:
        """Apply simultaneous catches, sharing proportionally if they exceed the stock."""
        total = sum(requested)
        ratio = min(1.0, self.stock / total) if total > 0 else 0.0
        caught = [amount * ratio for amount in requested]
        self.stock = max(0.0, self.stock - sum(caught))
        return caught

    def regrow(self) -> None:
        self.stock = min(CAPACITY, self.stock + regrowth(self.stock))

    @property
    def collapsed(self) -> bool:
        return self.stock < COLLAPSE_LEVEL
