"""ONE notion of "the customer changed the subject" (owner ruling, 2026-09-06).

Three of the four rules from the 6 Sep console pass need the same question answered, and
answering it three times is exactly how the picker roster, the carried entities and the
pending escalation offer end up disagreeing about what the conversation is still about:

* the TAIL keeps an offer roster alive until the topic changes, so "1", then "2", then
  "3" all answer against the list the customer can still see (rule 1, `compile_state`);
* the HEAD drops previously carried entities when the topic changes, so a scope from the
  old subject cannot silently narrow the new one (rule 2, `output_exchange`);
* the HEAD reads a filter-only reply under a pending member offer as a continuation of
  the SAME topic rather than as an out-of-range pick (rule 3, `output_exchange`).

So it is one pure function over three values, imported by both halves. It lives in its
own module rather than in `contracts.py` because that file declares vocabularies and
payload shapes and this is a decision, and it lives outside `head/` and `tail/` because
both import it and neither may import the other.

The truth table, in the order the branches are read:

    previous domain   new domain    new offer this turn   changed
    ---------------   -----------   -------------------   -------
    anything          anything      yes                   YES
    "order"           null          no                    no
    null              "inventory"   no                    no
    "order"           "order"       no                    no
    "order"           "inventory"   no                    YES

Two of those rows are the ones that cost real turns, so they are stated rather than left
to be inferred from the code:

* **A turn that names NO domain never changes the topic.** A pick ("2"), a date window
  ("last month") and a bare product code all arrive with `domain_hint: null`, and reading
  that as "the subject changed" is what dropped the roster the customer was answering.
* **A carried domain of `null` is not a change either.** The customer typed a code, the
  turn had no domain, and the next turn finally names one - that is the SAME subject
  acquiring a name, and dropping the carried entity there breaks the ordinary
  "SRTWC286" -> "do you have stock" continuation. A caller that knows the carried
  offer's own domain (a tier menu only ever lives in a promotion thread) passes THAT
  rather than a null, which is how the tier menu still dies on a domain change.

A new offer this turn always wins, whatever the domains say: the roster on the
customer's screen is the one this turn just rendered, and carrying the previous one back
over it arms the session against a list nobody can see (H29).

**One older reader of "did the domain change?" is deliberately NOT folded in here.** The
did-you-mean lifecycle (`tail/compile_state.py`, rule 2 of the eight) compares this turn's
domain against `dym_offer.domain` - the domain the OFFER itself recorded - rather than
against the previous turn's. That is a different question with a different answer (an
offer can outlive the turn that made it, and then a domain the session moved on from is
still the offer's own), it is a faithful port of the n8n rule, and its eight-rule order is
graded against captures. Rewriting it to call this function would be a behaviour change
smuggled in as a tidy-up. If a future ruling makes the two one question, that is the point
to fold them, and this paragraph is the note saying where the other copy lives.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import jsc


def changed(previous_domain: Any, new_domain: Any, *, new_offer: bool = False) -> bool:
    """True when the previous turn's pending context must NOT be carried forward."""
    if new_offer:
        return True
    if not jsc.truthy(new_domain) or not jsc.truthy(previous_domain):
        return False
    return jsc.js_string(new_domain) != jsc.js_string(previous_domain)
