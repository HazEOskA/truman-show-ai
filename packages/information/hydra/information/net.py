"""HydraNet — the world's own internet (spec section 16).

Search, news, social, forums, messaging, corporate sites, marketplaces and underground
networks. Posts reference facts, so information that travels through the net is the same
object the knowledge system reasons about, and a lie stays traceable to whoever posted it.

Text is generated deterministically from templates. An LLM can later rewrite a post's prose;
it can never invent the fact underneath it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar

from hydra.events.model import TruthStatus
from hydra.kernel.state import DomainState, register_domain


class SiteKind(str, enum.Enum):
    SEARCH = "search"
    NEWS = "news"
    SOCIAL = "social"
    FORUM = "forum"
    MESSAGING = "messaging"
    CORPORATE = "corporate"
    MARKETPLACE = "marketplace"
    UNDERGROUND = "underground"


@dataclass(slots=True)
class Site:
    site_id: str
    name: str
    kind: SiteKind
    owner_id: str = ""
    reach: float = 0.1               # share of population that can see content here
    trust: float = 0.5
    moderation: float = 0.5
    active_users: int = 0


@dataclass(slots=True)
class Post:
    post_id: str
    site_id: str
    author_id: str
    tick: int
    topic: str
    text: str
    fact_id: str = ""
    stance: float = 0.0              # -1 hostile .. +1 supportive
    reach: int = 0
    engagement: int = 0
    truth: TruthStatus = TruthStatus.UNVERIFIED
    parent_post_id: str = ""


@dataclass(slots=True)
class DirectMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    tick: int
    topic: str
    text: str
    fact_id: str = ""
    read: bool = False


@register_domain
@dataclass(slots=True)
class NetState(DomainState):
    DOMAIN: ClassVar[str] = "net"

    sites: dict[str, Site] = field(default_factory=dict)
    posts: dict[str, Post] = field(default_factory=dict)
    messages: dict[str, DirectMessage] = field(default_factory=dict)
    trending: dict[str, float] = field(default_factory=dict)
    search_index: dict[str, list[str]] = field(default_factory=dict)
    next_post_index: int = 0
    next_message_index: int = 0
    max_posts: int = 1_500
    max_messages: int = 800

    def new_post_id(self) -> str:
        self.next_post_index += 1
        return f"post_{self.next_post_index:07d}"

    def new_message_id(self) -> str:
        self.next_message_index += 1
        return f"msg_{self.next_message_index:07d}"

    def add_post(self, post: Post) -> Post:
        self.posts[post.post_id] = post
        self.search_index.setdefault(post.topic, []).append(post.post_id)
        index = self.search_index[post.topic]
        if len(index) > 60:
            del index[: len(index) - 60]
        if len(self.posts) > self.max_posts:
            for key in sorted(self.posts, key=lambda k: (self.posts[k].tick, k))[: len(self.posts) - self.max_posts]:
                topic = self.posts[key].topic
                if topic in self.search_index and key in self.search_index[topic]:
                    self.search_index[topic].remove(key)
                del self.posts[key]
        return post

    def search(self, topic: str, limit: int = 10) -> list[Post]:
        ids = self.search_index.get(topic, [])
        posts = [self.posts[i] for i in ids if i in self.posts]
        posts.sort(key=lambda p: (-p.engagement, -p.tick))
        return posts[:limit]

    def sites_of_kind(self, kind: SiteKind) -> list[Site]:
        return [s for s in self.sites.values() if s.kind is kind]
