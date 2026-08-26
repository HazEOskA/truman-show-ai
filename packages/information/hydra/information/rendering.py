"""Deterministic text rendering.

Every fact and headline in Hydra is written by a template, not by a model. That keeps the
world runnable with no provider, keeps replays byte-identical, and keeps the *content* of a
story tied to the numbers that produced it. An LLM may later restyle this prose; it can never
invent the fact underneath.
"""

from __future__ import annotations

from hydra.events.model import Event

_MINOR = 100.0


def render_fact(event: Event) -> tuple[str, str, float]:
    """Returns ``(claim, text, value)`` for an event that becomes public knowledge."""

    payload = event.payload
    topic = event.topic

    if topic == "market.price.move":
        change = float(payload.get("change_pct", 0.0))
        code = str(payload.get("code", "goods"))
        direction = "rose" if change > 0 else "fell"
        return (
            "price_level",
            f"the price of {code.replace('_', ' ')} {direction} {abs(change):.1f}% to "
            f"{float(payload.get('price_minor', 0)) / _MINOR:.2f} HYD",
            float(payload.get("price_minor", 0.0)),
        )
    if topic == "market.shortage":
        return (
            "shortage",
            f"{str(payload.get('code', 'goods')).replace('_', ' ')} is running short in the city",
            float(payload.get("unmet", 0.0)),
        )
    if topic == "env.power.shortage":
        return (
            "power_shortage",
            f"the grid is {float(payload.get('deficit_mw', 0.0)):.0f} MW short of demand",
            float(payload.get("deficit_mw", 0.0)),
        )
    if topic == "company.layoff":
        return (
            "layoff",
            f"{payload.get('company_name', event.actor)} laid off {payload.get('count', 0)} workers",
            float(payload.get("count", 0)),
        )
    if topic == "company.bankrupt":
        return (
            "bankruptcy",
            f"{payload.get('company_name', event.actor)} went bankrupt, {payload.get('jobs_lost', 0)} jobs lost",
            float(payload.get("jobs_lost", 0)),
        )
    if topic == "company.output_cut":
        return (
            "output_cut",
            f"{event.actor} cut production of {payload.get('product', 'goods')}",
            float(payload.get("utilisation", payload.get("output", 0.0))),
        )
    if topic == "gov.policy":
        return (
            "policy",
            f"the city government enacted {str(payload.get('policy', 'a measure')).replace('_', ' ')}",
            float(payload.get("value", 0.0)),
        )
    if topic == "gov.emergency":
        return ("emergency", f"the city declared emergency level {payload.get('level', 1)}",
                float(payload.get("level", 1)))
    if topic == "person.protest":
        return (
            "protest",
            f"{payload.get('participants', 'people')} protested in {event.location or 'the city'} "
            f"over {str(payload.get('grievance', 'conditions')).replace('_', ' ')}",
            float(payload.get("participants", 0.0)),
        )
    if topic == "tech.discovery":
        return ("discovery", f"researchers announced {payload.get('name', 'a breakthrough')}", 1.0)
    if topic == "person.death":
        return ("death", f"{payload.get('name', event.actor)} died", 1.0)
    if topic == "env.weather":
        return ("weather", f"extreme weather: {float(payload.get('temperature_c', 0.0)):.1f}°C", 
                float(payload.get("temperature_c", 0.0)))
    return (event.action, f"{event.action.replace('_', ' ')} ({event.actor or event.location or 'city'})", 0.0)


FRAMINGS = ("blame_government", "blame_business", "alarm", "reassure", "neutral", "human_interest")


def render_headline(framing: str, text: str, sensational: bool) -> str:
    """One fact, several narratives (spec section 17)."""

    core = text[0].upper() + text[1:] if text else "News"
    if framing == "blame_government":
        return f"City hall under fire: {core.lower()}"
    if framing == "blame_business":
        return f"Profits before people: {core.lower()}"
    if framing == "alarm":
        return f"{'CRISIS' if sensational else 'Warning'}: {core.lower()}"
    if framing == "reassure":
        return f"Officials say situation is under control as {core.lower()}"
    if framing == "human_interest":
        return f"'We are the ones paying' — {core.lower()}"
    return core
