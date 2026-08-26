"""Agent brains.

Tier B runs on utility AI: a handful of scored options, no reasoning, no model. Tier A runs
the same utility layer first and only escalates to a language model when the situation is
important enough and the compute budget allows it (spec sections 26–27).

A brain never mutates the world. It returns an :class:`ActionIntent` and the kernel decides.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.kernel.actions import ActionIntent
from hydra.kernel.rng import DeterministicRng

from .view import AgentView


@dataclass(slots=True)
class Option:
    action: str
    score: float
    params: dict
    rationale: str


class UtilityBrain:
    """Deterministic, cheap, and good enough for the overwhelming majority of decisions."""

    def options(self, view: AgentView) -> list[Option]:
        options: list[Option] = []
        needs = view.needs
        traits = view.personality

        options.append(
            Option(
                "rest",
                score=(1.0 - view.energy) * 1.5 + view.stress * 0.8 + (1.0 - needs.get("rest", 0.8)) * 0.6,
                params={},
                rationale="tired",
            )
        )

        if needs.get("food", 1.0) < 0.75:
            options.append(
                Option(
                    "buy_food",
                    score=(1.0 - needs.get("food", 1.0)) * 2.1,
                    params={"quantity": round(1.0 + (1.0 - needs.get("food", 1.0)) * 2.0, 2)},
                    rationale="hungry",
                )
            )

        if view.employed and 7 <= view.hour <= 17:
            options.append(Option("go_to_work", score=1.25 + traits.get("conscientiousness", 0.5) * 0.5,
                                  params={}, rationale="working hours"))

        if not view.employed and 8 <= view.hour <= 18 and view.age_years < 67:
            urgency = 1.6 + view.stress * 0.8 + traits.get("ambition", 0.5) * 0.5
            if view.openings:
                best = max(view.openings, key=lambda o: o.wage_minor)
                options.append(
                    Option("apply_for_job", score=urgency + 0.3, params={"opening_id": best.opening_id},
                           rationale="unemployed, opening known")
                )
            options.append(Option("look_for_job", score=urgency, params={}, rationale="unemployed"))

        options.append(
            Option(
                "socialise",
                score=(1.0 - needs.get("social", 0.6)) * 1.2 + traits.get("extraversion", 0.5) * 0.7,
                params={},
                rationale="wants company",
            )
        )

        options.append(
            Option(
                "read_news",
                score=0.35 + traits.get("openness", 0.5) * 0.7 + view.inbox_importance * 0.9,
                params={},
                rationale="checking what is going on",
            )
        )

        strong = [f for f in view.known_facts if f.confidence > 0.55]
        if strong:
            top = max(strong, key=lambda f: f.confidence)
            options.append(
                Option(
                    "post_online",
                    score=0.25 + traits.get("extraversion", 0.5) * 0.8 + view.inbox_importance * 0.6
                    + (0.5 if view.political_trust < 0.35 else 0.0),
                    params={"fact_id": top.fact_id},
                    rationale="has something to say",
                )
            )

        grievance = (1.0 - view.political_trust) + view.perceived_unrest + max(0.0, 0.6 - needs.get("food", 1.0))
        if grievance > 1.25 and 9 <= view.hour <= 20 and view.age_years >= 16:
            options.append(
                Option(
                    "protest",
                    score=0.55 * grievance + traits.get("risk_tolerance", 0.5) * 0.5 - (0.4 if view.employed else 0.0),
                    params={},
                    rationale="angry at the city",
                )
            )

        if (
            view.balance_minor > 4_000_000
            and traits.get("ambition", 0.5) > 0.72
            and traits.get("risk_tolerance", 0.5) > 0.6
            and not view.employed
        ):
            options.append(Option("found_company", score=1.1 + traits.get("ambition", 0.5), params={},
                                  rationale="capital and ambition"))

        return options

    def decide(self, view: AgentView, rng: DeterministicRng) -> ActionIntent | None:
        options = [o for o in self.options(view) if o.score > 0.0]
        if not options:
            return None
        options.sort(key=lambda o: (-o.score, o.action))
        top = options[:4]
        chosen = rng.weighted_choice(top, [max(0.01, o.score) ** 2 for o in top])
        return ActionIntent(
            action=chosen.action,
            actor=view.person_id,
            params=dict(chosen.params),
            rationale=chosen.rationale,
            source="utility",
            importance=min(1.0, chosen.score / 3.0),
        )


def situation_importance(view: AgentView) -> float:
    """How much this decision matters — the gate for spending a model call."""

    stakes = 0.0
    if not view.employed:
        stakes += 0.35
    stakes += view.inbox_importance * 0.5
    stakes += max(0.0, 0.5 - view.needs.get("food", 1.0)) * 0.6
    stakes += max(0.0, 0.4 - view.political_trust) * 0.5
    stakes += view.salience * 0.4
    return round(min(1.0, stakes), 4)
