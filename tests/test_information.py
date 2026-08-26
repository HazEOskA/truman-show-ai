"""Information, media, memory, the social graph and demography."""

from __future__ import annotations

from hydra.agents.model import AgentsState
from hydra.events.model import Event, TruthStatus, Visibility
from hydra.history.causal import CausalGraph
from hydra.information.model import Fact, KnowledgeState, KnownFact, Observation, Source
from hydra.information.net import NetState, SiteKind
from hydra.information.rendering import render_fact, render_headline
from hydra.information.systems import FactSystem
from hydra.kernel.clock import TICKS_PER_DAY, TICKS_PER_MONTH
from hydra.media.model import MediaState
from hydra.memory.model import MemoryKind, MemoryState
from hydra.memory.operations import consolidate, decay, recall, record
from hydra.social.model import Relation, SocialState
from hydra.world import create_world

from conftest import small_config


def test_facts_are_rendered_without_a_model():
    event = Event(
        event_id="e1", tick=10, topic="company.layoff", action="laid_off_workers",
        actor="company_0007", payload={"count": 24, "company_name": "Kelvar Works"},
    )
    claim, text, value = render_fact(event)
    assert claim == "layoff" and "24" in text and value == 24.0
    assert render_headline("blame_government", text, True).startswith("City hall")
    assert render_headline("neutral", text, False)[0].isupper()


def test_only_observable_events_become_facts(world):
    knowledge = world.state.domain(KnowledgeState)
    system = FactSystem()
    ctx = world.kernel.ctx
    before = len(knowledge.facts)

    system.on_event(ctx, Event(event_id="e_hidden", tick=1, topic="company.layoff", action="x",
                               importance=0.9, visibility=Visibility.HIDDEN))
    assert len(knowledge.facts) == before, "a hidden event is not public knowledge"

    system.on_event(ctx, Event(event_id="e_small", tick=1, topic="company.layoff", action="x", importance=0.01))
    assert len(knowledge.facts) == before, "trivia does not become a fact about the world"

    system.on_event(ctx, Event(event_id="e_real", tick=1, topic="company.layoff", action="laid_off_workers",
                               importance=0.8, payload={"count": 5}))
    assert len(knowledge.facts) == before + 1


def test_knowledge_is_per_agent_and_can_be_wrong(world):
    knowledge = world.state.domain(KnowledgeState)
    fact = knowledge.add_fact(Fact(fact_id="fact_x", tick=1, topic="price.food", subject="food",
                                   claim="price_level", value=100.0, text="food costs 1.00"))
    knowledge.learn("person_000001", KnownFact(fact_id=fact.fact_id, acquired_tick=1, source=Source.MEDIA,
                                               confidence=0.6, value=140.0, distorted=True,
                                               believed_truth=TruthStatus.DISTORTED))
    assert knowledge.knows("person_000001", "fact_x")
    assert not knowledge.knows("person_000002", "fact_x")
    assert knowledge.known("person_000001")["fact_x"].value != fact.value, "belief may differ from truth"


def test_repeating_a_fact_reinforces_confidence(world):
    knowledge = world.state.domain(KnowledgeState)
    knowledge.add_fact(Fact(fact_id="fact_y", tick=1, topic="t", subject="s", claim="c"))
    first = knowledge.learn("person_000003", KnownFact(fact_id="fact_y", acquired_tick=1, source=Source.SOCIAL, confidence=0.4))
    again = knowledge.learn("person_000003", KnownFact(fact_id="fact_y", acquired_tick=2, source=Source.MEDIA, confidence=0.4))
    assert again is first and again.confidence > 0.4 and again.reinforcements == 1


def test_inbox_drains_in_order_and_is_bounded(world):
    knowledge = world.state.domain(KnowledgeState)
    for index in range(knowledge.max_inbox + 20):
        knowledge.observe("person_000004", Observation(tick=index, kind="event", topic="t",
                                                       summary=f"thing {index}", importance=index / 100))
    assert len(knowledge.inboxes["person_000004"]) <= knowledge.max_inbox
    drained = knowledge.drain_inbox("person_000004")
    assert drained == sorted(drained, key=lambda o: (o.tick, o.topic))
    assert knowledge.inboxes["person_000004"] == []


def test_media_produce_competing_narratives(world):
    world.kernel.run(TICKS_PER_DAY)
    media = world.state.domain(MediaState)
    assert media.publications, "a day in the city produces news"
    framings = {p.framing for p in media.publications.values()}
    assert len(framings) > 1
    for outlet in media.outlets.values():
        assert -1.0 <= outlet.bias_government <= 1.0


def test_hydranet_indexes_and_bounds_posts(world):
    from hydra.information.net import Post

    net = world.state.domain(NetState)
    assert net.sites_of_kind(SiteKind.SEARCH), "the world has a search engine"
    for index in range(20):
        net.add_post(Post(post_id=net.new_post_id(), site_id="site_social", author_id="person_000001",
                          tick=index, topic="price.food", text="prices again", engagement=index))
    found = net.search("price.food", limit=5)
    assert len(found) == 5
    assert found[0].engagement >= found[-1].engagement


def test_memory_consolidates_and_forgets():
    state = MemoryState()
    for index in range(60):
        record(state, "person_1", tick=index, topic="day", summary=f"day {index}",
               salience=0.05 if index < 40 else 0.8, working_limit=5)
    memory = state.for_person("person_1")
    assert len(memory.working) <= 5, "working memory is small by design"

    forgotten = decay(memory, tick=TICKS_PER_MONTH * 6, per_day=0.05)
    assert forgotten > 0, "old, low-salience memories fade"

    for index in range(300):
        record(state, "person_1", tick=1000 + index, topic="noise", summary=f"n{index}", salience=0.5)
    summary = consolidate(state.for_person("person_1"), tick=2000, episodic_limit=50)
    assert summary is not None and summary.kind is MemoryKind.SUMMARY
    assert len(state.for_person("person_1").episodic) <= 50


def test_memory_recall_prefers_salient_and_recent():
    state = MemoryState()
    record(state, "p", tick=1, topic="job", summary="old and dull", salience=0.1)
    record(state, "p", tick=900, topic="job", summary="recent and vivid", salience=0.9)
    top = recall(state.for_person("p"), "job", tick=1000, limit=1)
    assert top[0].summary == "recent and vivid"
    assert top[0].recall_count == 1


def test_social_edges_carry_history():
    social = SocialState()
    edge = social.link("person_1", "person_2", Relation.FRIEND, tick=0, strength=0.4, trust=0.5)
    edge.adjust(10, field_name="trust", delta=0.3, reason="stood by me")
    assert edge.trust > 0.5 and edge.history and edge.history[-1].reason == "stood by me"
    assert social.neighbours("person_1") == [edge]
    assert social.inbound("person_2") == [edge]
    assert social.between("person_1", "person_2") == [edge]


def test_causal_graph_answers_why():
    events = [
        Event(event_id="e1", tick=1, topic="env.weather", action="drought"),
        Event(event_id="e2", tick=2, topic="market.shortage", action="food_shortage", causes=["e1"]),
        Event(event_id="e3", tick=3, topic="econ.inflation", action="inflation", causes=["e2"]),
        Event(event_id="e4", tick=4, topic="person.protest", action="unrest", causes=["e3"]),
    ]
    graph = CausalGraph(events)
    chain = graph.why("e4")
    assert [node.event.action for node in chain] == ["drought", "food_shortage", "inflation", "unrest"]
    assert [event.action for event in graph.roots("e4")] == ["drought"]
    assert [node.event.action for node in graph.consequences("e1")] == ["food_shortage", "inflation", "unrest"]


def test_demography_ages_the_city_and_records_events():
    # A month of ticks: run it on the smallest world that still has every subsystem in it.
    config = small_config()
    config.population.total_residents = 1_200
    config.population.lightweight_agents = 60
    config.population.persistent_agents = 8
    config.economy.company_count = 25
    runtime = create_world(config, seed=4321, world_id="world_demo")
    agents = runtime.state.domain(AgentsState)
    before_age = sum(p.age_years for p in agents.people.values()) / len(agents.people)
    before_population = agents.total_population()

    runtime.kernel.run(TICKS_PER_MONTH + 1)

    after_age = sum(p.age_years for p in agents.people.values() if p.alive) / max(1, len(agents.alive_people()))
    assert after_age > before_age, "a month should pass for everyone"
    assert agents.total_population() > 0
    assert abs(agents.total_population() - before_population) < before_population * 0.2
