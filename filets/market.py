"""Hamlet markets: every catch is sold the season it is landed.

The price depends on the total supply of the valley that season:

    price = BASE_PRICE * 2 / (1 + supply / NORMAL_SUPPLY)

At a normal supply the price is BASE_PRICE. It tends to twice that when fish is
scarce, and keeps falling, without ever reaching zero, when the market is flooded.
"""

BASE_PRICE = 10.0
NORMAL_SUPPLY = 12.0  # tons a season, close to what the lake can regrow at best


def price(supply: float) -> float:
    return BASE_PRICE * 2 / (1 + supply / NORMAL_SUPPLY)


class Market:
    def __init__(self, hamlets: list[str]):
        self.ledger = {hamlet: {"tons": 0.0, "revenue": 0.0, "seasons": []} for hamlet in hamlets}

    def sell(self, season: int, landings: list[dict]) -> tuple[float, list[dict]]:
        """Sell landings ({agent, name, hamlet, tons}) and return the price and the sales."""
        current = price(sum(item["tons"] for item in landings))
        sales = [{**item, "price": current, "revenue": item["tons"] * current} for item in landings]
        for hamlet, account in self.ledger.items():
            local = [sale for sale in sales if sale["hamlet"] == hamlet]
            tons = sum(sale["tons"] for sale in local)
            revenue = sum(sale["revenue"] for sale in local)
            account["tons"] += tons
            account["revenue"] += revenue
            account["seasons"].append({"season": season, "tons": round(tons, 2), "price": round(current, 2),
                                       "revenue": round(revenue, 2)})
        return current, sales
