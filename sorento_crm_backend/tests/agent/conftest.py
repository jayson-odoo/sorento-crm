"""Fixtures for tests/agent.

`session_factory` (a blank-schema session factory rolled back at teardown) lives in
tests/chatbot/conftest.py; the route and settings tests reuse the chatbot console harness,
so it is re-exported here rather than copied.
"""
from tests.chatbot.conftest import session_factory  # noqa: F401
