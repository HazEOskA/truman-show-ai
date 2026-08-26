"""Media system: the same event, several stories.

An outlet picks a fact up when it clears that outlet's own bar (importance × sensationalism),
then frames it according to who owns it and who reads it. Nothing is invented: the framing
changes the wrapper, the numbers underneath stay the fact's.
"""

from __future__ import annotations

from hydra.events.importance import ImportanceInputs
from hydra.events.model import Topics, TruthStatus
from hydra.information.model import KnowledgeState
from hydra.information.net import NetState, Post
from hydra.information.rendering import render_headline
from hydra.kernel.clock import TICKS_PER_DAY
from hydra.kernel.systems import Phase, SystemSpec

from .model import BusinessModel, MediaState, Narrative, OutletKind, Publication

POLITICAL_TOPICS = ("gov.", "env.power", "person.protest", "market.shortage")
BUSINESS_TOPICS = ("company.", "market.price.move", "bank.")


class MediaSystem:
    spec = SystemSpec(
        name="media",
        phase=Phase.INFORMATION,
        cadence_ticks=3,
        priority=20,
        reads=("media", "information", "net", "government"),
        writes=("media", "net", "information"),
        emits=(Topics.MEDIA_PUBLISH,),
        description="Outlet pickup, framing, narratives and publication reach.",
    )

    def __init__(self, cadence_ticks: int = 3) -> None:
        self.spec = MediaSystem.spec.with_cadence(cadence_ticks)

    def step(self, ctx) -> None:  # noqa: ANN001
        media = ctx.state.domain(MediaState)
        knowledge = ctx.state.domain(KnowledgeState)
        net = ctx.state.domain(NetState)
        rng = ctx.rng("media")
        threshold = ctx.config.information.media_pickup_threshold
        window = ctx.tick - self.spec.cadence_ticks * 4

        published_facts = {p.fact_id for p in media.publications.values() if p.tick >= ctx.tick - TICKS_PER_DAY}
        candidates = [
            f for f in knowledge.facts.values()
            if f.tick >= window and f.importance >= threshold and f.fact_id not in published_facts
        ]
        candidates.sort(key=lambda f: (-f.importance, f.fact_id))

        for fact in candidates[:4]:
            for outlet_id in sorted(media.outlets):
                outlet = media.outlets[outlet_id]
                appetite = fact.importance * (0.5 + outlet.sensationalism) * (0.4 + outlet.audience_share * 1.6)
                if appetite < threshold or not rng.chance(min(0.8, appetite)):
                    continue
                framing = self._framing(outlet, fact.topic, rng)
                sentiment = self._sentiment(framing, outlet)
                accurate = rng.chance(outlet.accuracy)
                media.next_publication_index += 1
                publication = Publication(
                    publication_id=media.new_publication_id(),
                    outlet_id=outlet.outlet_id,
                    tick=ctx.tick,
                    topic=fact.topic,
                    headline=render_headline(framing, fact.text, outlet.sensationalism > 0.6),
                    framing=framing,
                    fact_id=fact.fact_id,
                    sentiment=sentiment,
                    reach=int(outlet.audience_share * 40_000 * (0.7 + outlet.reputation)),
                    truth=TruthStatus.TRUE if accurate else TruthStatus.DISTORTED,
                    event_id=fact.origin_event_id,
                )
                media.add_publication(publication)

                if outlet.site_id in net.sites:
                    net.add_post(
                        Post(
                            post_id=net.new_post_id(),
                            site_id=outlet.site_id,
                            author_id=outlet.outlet_id,
                            tick=ctx.tick,
                            topic=fact.topic,
                            text=publication.headline,
                            fact_id=fact.fact_id,
                            stance=sentiment,
                            reach=publication.reach,
                            truth=publication.truth,
                        )
                    )

                narrative = media.narratives.get(fact.topic)
                if narrative is None:
                    narrative = Narrative(topic=fact.topic)
                    media.narratives[fact.topic] = narrative
                narrative.framings[framing] = round(narrative.framings.get(framing, 0.0) + outlet.audience_share, 4)
                narrative.momentum = round(min(5.0, narrative.momentum + fact.importance), 4)
                narrative.last_tick = ctx.tick
                narrative.dominant = max(narrative.framings.items(), key=lambda kv: (kv[1], kv[0]))[0]

                if outlet.business_model in (BusinessModel.ADVERTISING, BusinessModel.SUBSCRIPTION):
                    outlet.revenue_minor += publication.reach * 2

                ctx.emit(
                    Topics.MEDIA_PUBLISH,
                    "published",
                    actor=outlet.outlet_id,
                    target=fact.fact_id,
                    location=fact.district_id or None,
                    payload={
                        "headline": publication.headline,
                        "framing": framing,
                        "topic": fact.topic,
                        "reach": publication.reach,
                        "outlet": outlet.name,
                    },
                    inputs=ImportanceInputs(
                        people_affected=publication.reach * 0.35,
                        political_impact=0.35 if framing == "blame_government" else 0.15,
                        novelty=0.4,
                    ),
                    causes=[fact.origin_event_id] if fact.origin_event_id else None,
                )

        for narrative in media.narratives.values():
            narrative.momentum = round(narrative.momentum * 0.94, 4)
        ctx.telemetry.gauge("publications", float(len(media.publications)))

    @staticmethod
    def _framing(outlet, topic: str, rng) -> str:  # noqa: ANN001
        political = topic.startswith(POLITICAL_TOPICS)
        business = topic.startswith(BUSINESS_TOPICS)
        if outlet.kind is OutletKind.STATE and political:
            return "reassure" if outlet.bias_government > 0.2 else "neutral"
        if political and outlet.bias_government < -0.15:
            return "blame_government"
        if business and outlet.bias_business < -0.15:
            return "blame_business"
        if outlet.sensationalism > 0.65 and rng.chance(0.6):
            return "alarm"
        if rng.chance(0.2):
            return "human_interest"
        return "neutral"

    @staticmethod
    def _sentiment(framing: str, outlet) -> float:  # noqa: ANN001
        base = {
            "blame_government": -0.7,
            "blame_business": -0.55,
            "alarm": -0.6,
            "reassure": 0.45,
            "human_interest": -0.25,
            "neutral": -0.05,
        }[framing]
        return round(max(-1.0, min(1.0, base * (0.7 + outlet.sensationalism * 0.6))), 4)
