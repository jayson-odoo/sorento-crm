"""Owner retest of round 10 on PR #833 (:3084, 28 Sep 2026 19:4x to 20:0x MYT, contact Mr
Loo, parser v42 and v46) and the owner's ruling. Fix round 12.

The owner typed `any gunmetal basin have stock` and got, tagged business_query:

    Stock summary for gunmetal wash basins (2).

    1. Product Code: SRTFT206-GM
    Total: 937 (O/S: 0)
    ...

and ruled (verbatim): "what? i thought we are applying a general fix? why the fix that we
applied for incoming cannot work for stock? this is too fragile, that means our solution
is not right".

What it was: the attribute-first lane DID own that turn. The set qualified two products
(they have stock), and a set that qualified anything opened with its leg's own tool
sentence ("Stock summary for ..."), while a set that qualified nothing (the incoming ask:
no incoming) opened with "Here's what you want:". The reply shape followed the count and
the leg word. Separately, the leg was read off a fixed word table, so a product ask that
requested "in stock" or "arriving" got no leg, and a product ask that requested "stock"
listed product rows under a stock header, because the tool followed the parser's intent.

The rule now, by structure: an ask that describes a product set (a product type, a
category or a specification, no code) is the attribute-first lane's. Its leg is read off
the intent, the routed domain and every word of a requested attribute through the
registry (`_LEG_BY_ATTRIBUTE_WORD` plus each leg domain's `switch_words`), and it sets the
turn's domain before APPLY, so the leg chooses the figures, the rows and the team. Every
set answer opens with "Here's what you want:", hit or miss.

The generated test below builds the phrasings from that same registry and the owner's own
list, and asserts the one shape for every one of them.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from tests.chatbot.test_attribute_asks_round3 import _entity
from tests.chatbot.test_attribute_asks_round3 import world as r3world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round4 import world as r4world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round7 import _code_ask
from tests.chatbot.test_attribute_asks_round7 import world as r7world  # noqa: F401 - fixture used by name
from tests.chatbot.test_attribute_asks_round8 import _Loo
from tests.chatbot.test_attribute_asks_round9 import world as r9world  # noqa: F401 - fixture used by name
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_lane_require import _stock_for


@pytest.fixture()
def world(r9world):
    """Round 9's world (two gunmetal wash basins, Cabana and Sorento, certificates, no
    incoming; a chrome basin with incoming), with the two gunmetal basins given the
    stock the owner's reply showed."""
    db = r9world["db"]
    for product, on_hand in zip(r9world["gunmetal"], (937, 358)):
        _stock_for(db, product_id=product.id, warehouse_id=r9world["warehouse"].id, on_hand=on_hand)
    db.commit()
    return r9world


def _chat(session_factory, monkeypatch, stub_parser, stub_access, world) -> _Loo:
    return _Loo(session_factory, monkeypatch, stub_parser, stub_access, world, "compact")


@pytest.fixture()
def chat(session_factory, monkeypatch, stub_parser, stub_access, world):
    return _chat(session_factory, monkeypatch, stub_parser, stub_access, world)


def _spec(raw: str, key: str, value: Any) -> dict[str, Any]:
    return {**_entity(raw, "specification"), "spec_key": key, "spec_value": value}


def _split() -> list[dict[str, Any]]:
    """The published parser's reading (`SPECIFICATION_ADDENDUM`): "gunmetal basin" ->
    category "basin" + specification finish gunmetal."""
    return [_entity("basin", "category"), _spec("gunmetal", "finish", "gunmetal")]


def _one_token() -> list[dict[str, Any]]:
    """Round 8's trace: the whole phrase one product type; grounding splits it."""
    return [_entity("gunmetal basin")]


_LEG_ASK = {
    "stock": ("check_stock", "inventory"),
    "incoming": ("check_incoming", "incoming"),
}

#: The owner's own list (the 10:55Z ruling): the forms the fix must hold for without an
#: entry of its own. The leg is what the phrase asks for; "still have", "any left" and
#: "on order" carry no registry word at all, so only the parser's intent names their leg.
_OWNER_FORMS: dict[str, str] = {
    "has stock": "stock",
    "have stock": "stock",
    "got stock": "stock",
    "in stock": "stock",
    "still have": "stock",
    "any left": "stock",
    "incoming": "incoming",
    "arriving": "incoming",
    "on order": "incoming",
}

#: The low stock REPORT's own switch words: a different ask (`low_stock_report`), not a
#: stock figure for a described set.
_REPORT_WORDS = frozenset({"low stock", "reorder report", "below level"})


def _registry_forms() -> dict[str, str]:
    """Every stock or incoming word the registry knows, generated, never listed here:
    `predicate._LEG_BY_ATTRIBUTE_WORD` and the `switch_words` of the two legs' domains
    (`turn/policy_rows.py`), plus the owner's forms."""
    from app.services.chatbot.lanes.business.predicate import _LEG_BY_ATTRIBUTE_WORD
    from app.services.chatbot.turn.policy import default_policy, domain_switch_words

    forms = {w: leg for w, leg in _LEG_BY_ATTRIBUTE_WORD.items() if leg in _LEG_ASK}
    leg_by_domain = {domain: leg for leg, (_intent, domain) in _LEG_ASK.items()}
    for word, domain in domain_switch_words(default_policy()).items():
        if domain in leg_by_domain and word not in _REPORT_WORDS:
            forms.setdefault(word, leg_by_domain[domain])
    for form, leg in _OWNER_FORMS.items():
        forms.setdefault(form, leg)
    return forms


def _names_a_leg_by_word(form: str) -> bool:
    from app.services.chatbot.lanes.business.predicate import _leg_in_words

    return _leg_in_words(form) is not None


GUNMETAL_CODES = ("CBWB9GM0", "SRTWB9GM0")

INCOMING_MISS = (
    "Here's what you want: gunmetal wash basins (2)\n"
    "• CBWB9GM0\n"
    "• SRTWB9GM0\n"
    "\n"
    "But no incoming matched these. Would you like me to escalate to purchasing team?"
)


def _check(text: str, leg: str | None) -> list[str]:
    """Every way `text` breaks the one shape for `leg` (None: a product ask naming no leg)."""
    problems: list[str] = []
    if not text.startswith("Here's what you want: gunmetal wash basins"):
        problems.append("does not open with the set")
    for legacy in ("Stock summary for", "Incoming stock found for", "Here are "):
        if legacy in text:
            problems.append(f"legacy opener {legacy!r}")
    if leg == "stock":
        if text.split("\n")[0] != "Here's what you want: gunmetal wash basins with stock (2)":
            problems.append("stock header")
        if "*Total:* 937" not in text or "*Total:* 358" not in text:
            problems.append("no stock figures in the rows")
    elif leg == "incoming":
        if text != INCOMING_MISS:
            problems.append("incoming reply")
    else:
        if text.split("\n")[0] != "Here's what you want: gunmetal wash basins (2)":
            problems.append("product header")
    if not all(code in text for code in GUNMETAL_CODES):
        problems.append("not both gunmetal basins")
    return problems


# --------------------------------------------------------------------------- #
# The generated invariant                                                       #
# --------------------------------------------------------------------------- #


def _verdicts(form: str, leg: str) -> list[tuple[str, dict[str, Any], str | None]]:
    """How a parser can read `any gunmetal basin <form>`: the leg's own ask with the form
    as the requested attribute, the same with no attribute, the same over the one-token
    subject, and a product ask that requests the form (which names a leg only through a
    registry word inside it)."""
    intent, domain = _LEG_ASK[leg]
    message = f"any gunmetal basin {form}"
    by_word = leg if _names_a_leg_by_word(form) else None
    return [
        ("leg ask", _code_ask(message, *_split(), attrs=(form,), intent_hint=intent, domain_hint=domain), leg),
        ("leg ask, no attribute", _code_ask(message, *_split(), intent_hint=intent, domain_hint=domain), leg),
        ("leg ask, one token", _code_ask(message, *_one_token(), attrs=(form,), intent_hint=intent, domain_hint=domain), leg),
        ("product ask", _code_ask(message, *_split(), attrs=(form,)), by_word),
    ]


@pytest.mark.parametrize("leg", sorted(_LEG_ASK))
def test_every_stock_and_incoming_wording_is_the_one_attribute_first_shape(
    session_factory, monkeypatch, stub_parser, stub_access, world, leg
):
    forms = {form: form_leg for form, form_leg in _registry_forms().items() if form_leg == leg}
    # The registry really is where the words came from, and it knows the owner's words.
    assert {"stock", "incoming", "eta", "arriving"} & set(forms), forms
    failures: list[str] = []
    for form in sorted(forms):
        for shape, verdict, expected_leg in _verdicts(form, leg):
            # A fresh contact per phrasing: each is its own first ask.
            text = _chat(session_factory, monkeypatch, stub_parser, stub_access, world).say(
                f"any gunmetal basin {form}", verdict
            )
            problems = _check(text, expected_leg)
            if problems:
                failures.append(f"{form!r} ({shape}): {problems}\n{text}")
    assert not failures, "\n\n".join(failures)


def test_the_generated_phrasings_cover_the_owners_list():
    forms = _registry_forms()
    for form, leg in _OWNER_FORMS.items():
        assert forms[form] == leg, form
    # A registry word inside any wording names the leg, with no entry for the wording.
    for form in ("has stock", "have stock", "got stock", "in stock", "stock level", "still arriving", "incoming stock"):
        assert _names_a_leg_by_word(form), form


def test_the_bare_form_is_the_same_shape(chat):
    text = chat.say("gunmetal basin", _code_ask("gunmetal basin", *_split()))
    print(text)
    assert not _check(text, None), text


# --------------------------------------------------------------------------- #
# Console cases: the owner's exact phrase and the script's, as the harness       #
# replays them (beside round 10's cases)                                         #
# --------------------------------------------------------------------------- #

OWNER = "any gunmetal basin have stock"
SCRIPT_INCOMING = "any gunmetal basin has incoming?"


def test_console_owner_phrase_have_stock(chat):
    """The owner's phrase, read as v46 reads it (the leg's ask, category + finish)."""
    verdict = _code_ask(OWNER, *_split(), attrs=("stock",), intent_hint="check_stock", domain_hint="inventory")
    text = chat.say(OWNER, verdict)
    print(text)
    assert text.split("\n")[0] == "Here's what you want: gunmetal wash basins with stock (2)", text
    assert "Stock summary" not in text, text
    assert re.search(r"1\. \*Product Code:\* CBWB9GM0\n\*Total:\* 937", text), text
    assert re.search(r"2\. \*Product Code:\* SRTWB9GM0\n\*Total:\* 358", text), text


def test_console_script_phrase_incoming(chat):
    verdict = _code_ask(SCRIPT_INCOMING, *_split(), attrs=("incoming",), intent_hint="check_incoming", domain_hint="incoming")
    text = chat.say(SCRIPT_INCOMING, verdict)
    print(text)
    assert text == INCOMING_MISS, text


def test_a_product_ask_requesting_stock_shows_the_stock_figures_and_the_warehouse_team(chat, world):
    """Before round 12 the parser's product intent picked the product tool: product rows
    under a stock header. The leg now picks the rows."""
    text = chat.say(OWNER, _code_ask(OWNER, *_split(), attrs=("in stock",)))
    print(text)
    assert not _check(text, "stock"), text
    assert "*List Price:*" not in text, text


def test_an_incoming_hit_is_the_same_opener_with_incoming_rows(chat, world):
    """The chrome basin has incoming: the incoming leg's hit, in the same shape."""
    message = "any chrome basin arriving"
    verdict = _code_ask(message, _entity("basin", "category"), _spec("chrome", "finish", "chrome"), attrs=("arriving",))
    text = chat.say(message, verdict)
    print(text)
    assert text.split("\n")[0] == "Here's what you want: chrome wash basins with incoming stock (1)", text
    assert "SRTWB9CR0" in text, text
    assert "Incoming stock found" not in text, text
