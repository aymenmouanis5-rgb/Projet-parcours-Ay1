"""The event contract. Documented in docs/EVENTS.md; bump SCHEMA_VERSION when it changes."""

SCHEMA_VERSION = 8

NUMBER = (int, float)
OPTIONAL_NUMBER = (int, float, type(None))
OPTIONAL_TEXT = (str, type(None))

COMMON_FIELDS = {"v": int, "id": str, "run": str, "type": str, "season": int, "sim_time": NUMBER, "processed_at": NUMBER}

EVENT_FIELDS = {
    "run_started": {"agents": int, "seasons": int, "mode": str, "seed": int, "model": OPTIONAL_TEXT,
                    "hint": bool, "timing": str, "prompt_version": int, "stock": NUMBER},
    "message": {"agent": int, "text": str, "planned_catch": NUMBER, "seed": int},
    "retrieval": {"agent": int, "phase": str, "query": str, "documents": list},
    "decision": {"agent": int, "model": str, "requested": NUMBER, "safe_total": NUMBER},
    "catch": {"agent": int, "caught": NUMBER, "planned": OPTIONAL_NUMBER},
    "sale": {"agent": int, "hamlet": str, "tons": NUMBER, "price": NUMBER, "revenue": NUMBER},
    "lake": {"stock": NUMBER, "total_caught": NUMBER, "safe_total": NUMBER, "safe_violation": bool,
             "overshoot": NUMBER},
    "incident": {"kind": str},
    "collapse": {"stock": NUMBER},
    "run_ended": {"status": str, "seasons_survived": int, "total_catch": NUMBER, "final_stock": OPTIONAL_NUMBER,
                  "mean_stock": NUMBER, "safe_violations": int},
}


def validate(event: object) -> list[str]:
    """Return what is wrong with an event; an empty list means it conforms."""
    if not isinstance(event, dict):
        return ["not an object"]
    if event.get("type") not in EVENT_FIELDS:
        return [f"unknown type {event.get('type')!r}"]
    if event.get("v") != SCHEMA_VERSION:
        return [f"schema version {event.get('v')!r}"]
    errors = []
    for name, expected in {**COMMON_FIELDS, **EVENT_FIELDS[event["type"]]}.items():
        if name not in event:
            errors.append(f"missing {name}")
        elif not isinstance(event[name], expected):
            errors.append(f"wrong type for {name}")
    return errors
