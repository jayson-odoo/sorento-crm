"""`$variable` resolution for composer snippets (UAC AC-L4, slice S4.4).

Pure-function tests over ``resolve_snippet_variables`` plus the context builder
that reads a ticket. The rules being pinned here:

- the three documented tokens resolve from the ticket context;
- ANY other ``$token`` is left in the text exactly as typed (an unknown token is
  wording, not a bug - "$50 deposit" must survive a snippet insert);
- a contact with no name resolves to a neutral greeting rather than an empty
  hole ("Hi ," is worse than "Hi there,").

Run:
    venv/bin/pytest tests/test_message_snippet_variables.py -q
"""
from __future__ import annotations

import uuid

import pytest

from app.services.message_snippet_service import (
    SnippetContext,
    resolve_snippet_variables,
    snippet_context_for_tracking,
    ticket_reference,
)

CTX = SnippetContext(
    contact_name="Aisyah Rahman",
    assignee_name="Agent One",
    ticket_ref="ENQ-ABC123",
)


# ------------------------------------------------------------ the three tokens


def test_contact_name_resolves():
    assert resolve_snippet_variables("Hi $contact_name,", CTX) == "Hi Aisyah Rahman,"


def test_assignee_name_resolves():
    assert (
        resolve_snippet_variables("Regards,\n$assignee_name", CTX)
        == "Regards,\nAgent One"
    )


def test_ticket_ref_resolves():
    assert (
        resolve_snippet_variables("Your reference is $ticket_ref.", CTX)
        == "Your reference is ENQ-ABC123."
    )


def test_all_three_in_one_body():
    body = "Hi $contact_name, this is $assignee_name about $ticket_ref."
    assert (
        resolve_snippet_variables(body, CTX)
        == "Hi Aisyah Rahman, this is Agent One about ENQ-ABC123."
    )


def test_a_token_used_twice_resolves_twice():
    assert (
        resolve_snippet_variables("$contact_name, hello $contact_name", CTX)
        == "Aisyah Rahman, hello Aisyah Rahman"
    )


# ------------------------------------------------------------- unknown tokens


def test_unknown_token_is_left_literal():
    assert (
        resolve_snippet_variables("Deposit is $50 for $order_no", CTX)
        == "Deposit is $50 for $order_no"
    )


def test_a_longer_token_that_merely_starts_with_a_known_one_is_literal():
    """`$contact_names` is not `$contact_name` followed by an "s"."""
    assert resolve_snippet_variables("$contact_names", CTX) == "$contact_names"


def test_a_bare_dollar_survives():
    assert resolve_snippet_variables("Total: $", CTX) == "Total: $"


def test_empty_body_stays_empty():
    assert resolve_snippet_variables("", CTX) == ""


# ------------------------------------------------------------------ fallbacks


def test_missing_contact_name_falls_back_to_a_neutral_greeting():
    ctx = SnippetContext(contact_name="", assignee_name="Agent One", ticket_ref="ENQ-1")
    assert resolve_snippet_variables("Hi $contact_name,", ctx) == "Hi there,"


def test_missing_assignee_name_falls_back_to_the_team_name():
    ctx = SnippetContext(contact_name="A", assignee_name="", ticket_ref="ENQ-1")
    assert resolve_snippet_variables("- $assignee_name", ctx) == "- Customer Service"


# -------------------------------------------------------------- ticket_reference


def test_ticket_reference_is_stable_and_readable():
    tid = "6f1c9a20-4f3e-4b0a-9c1e-0d2b3a4c5d6e"
    assert ticket_reference(tid) == "ENQ-4C5D6E"
    assert ticket_reference(tid) == ticket_reference(tid)


def test_ticket_reference_of_nothing_is_empty():
    assert ticket_reference(None) == ""
    assert ticket_reference("") == ""


# ------------------------------------------------------- context from a ticket


class _Contact:
    def __init__(self, name=None, first_name=None, last_name=None, phone_number=""):
        self.name = name
        self.first_name = first_name
        self.last_name = last_name
        self.phone_number = phone_number


class _Tracking:
    def __init__(self, contact=None, assigned_to=None):
        self.id = "6f1c9a20-4f3e-4b0a-9c1e-0d2b3a4c5d6e"
        self.contact = contact
        self.assigned_to = assigned_to


def test_context_reads_the_contact_name_and_the_viewer():
    ctx = snippet_context_for_tracking(
        _Tracking(contact=_Contact(name="Aisyah Rahman"), assigned_to="Agent One"),
        viewer_name="Manager Mei",
    )
    assert ctx.contact_name == "Aisyah Rahman"
    # The person INSERTING signs the message, not the row's assignee: a manager
    # answering on someone's behalf must not sign with the assignee's name.
    assert ctx.assignee_name == "Manager Mei"
    assert ctx.ticket_ref == "ENQ-4C5D6E"


def test_context_falls_back_to_the_assignee_when_the_viewer_is_unknown():
    ctx = snippet_context_for_tracking(
        _Tracking(contact=_Contact(name="Aisyah"), assigned_to="Agent One"),
        viewer_name=None,
    )
    assert ctx.assignee_name == "Agent One"


def test_context_builds_a_name_from_first_and_last_when_there_is_no_name():
    ctx = snippet_context_for_tracking(
        _Tracking(contact=_Contact(first_name="Siti", last_name="Nur")),
        viewer_name="Agent",
    )
    assert ctx.contact_name == "Siti Nur"


def test_context_with_no_contact_at_all_leaves_the_greeting_neutral():
    ctx = snippet_context_for_tracking(_Tracking(contact=None), viewer_name="Agent")
    assert ctx.contact_name == ""
    assert resolve_snippet_variables("Hi $contact_name", ctx) == "Hi there"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_whitespace_contact_name_is_treated_as_missing(blank):
    ctx = snippet_context_for_tracking(
        _Tracking(contact=_Contact(name=blank)), viewer_name="Agent"
    )
    assert ctx.contact_name == ""
