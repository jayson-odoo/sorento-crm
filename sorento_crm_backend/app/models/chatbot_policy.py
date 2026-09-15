"""The chatbot's policy tables: `chatbot_domains` and `chatbot_entity_kinds` (AC-1501,
AC-1502).

Declared as models so `Base.metadata.create_all` builds them for every blank-schema test
fixture - the migration (`chatbot_rearch_s0`) is what SEEDS them on a real database, and
`app.services.chatbot.turn.policy.load_policy` falls back to
`turn/policy_rows.py`'s rows when the table is present but empty, which is exactly the
create_all case. Both columns sets mirror that migration exactly.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.database import Base


class ChatbotDomain(Base):
    __tablename__ = "chatbot_domains"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False, unique=True)
    label = Column(Text, nullable=False)
    intents = Column(ARRAY(Text), nullable=False, server_default="{}")
    tools = Column(ARRAY(Text), nullable=False, server_default="{}")
    primary_tool = Column(Text, nullable=True)
    escalation_team_code = Column(Text, nullable=True)
    switch_words = Column(ARRAY(Text), nullable=False, server_default="{}")
    narrowing = Column(JSONB, nullable=False, server_default="{}")
    takes_date_filter = Column(Boolean, nullable=False, server_default="false")
    reveal_key = Column(Text, nullable=True)
    supported = Column(Boolean, nullable=False, server_default="true")
    ladder = Column(ARRAY(Text), nullable=False, server_default="{}")
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatbotEntityKind(Base):
    __tablename__ = "chatbot_entity_kinds"

    kind = Column(Text, primary_key=True)
    label = Column(Text, nullable=False)
    resolver_source = Column(Text, nullable=False)
    did_you_mean = Column(Boolean, nullable=False, server_default="true")
    default_narrowing = Column(Text, nullable=False)
    family_grouping = Column(Text, nullable=True)
    base_property_words = Column(JSONB, nullable=False, server_default="{}")
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )
