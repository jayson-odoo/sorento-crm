"""Dialogue state: what the conversation is about, and what it is waiting for.

Growth r1 slice B. Three modules, one job each, and the split is the point:

* `decay.py` ages the state at INTAKE, before the parser is asked anything, so a slot the
  customer stopped talking about three turns ago cannot influence this turn's parse;
* `focus.py` is the ONE writer of what the conversation is about, replacing the two the
  plan measured (the parser prompt's "always continue the previous turn" plus ten
  deterministic carry rules in `head/output_exchange.py`);
* `open_question.py` is the ONE thing the bot can be waiting for, replacing the five
  `pending` kinds, the eight-rule `dym_offer` ladder, `selection_context`, the `picker_*`
  keys and `_offer_carry`.

Nothing here calls a model and nothing here reads the customer's words: the parser is the
only step that does that (D11), and everything below works on the structured state it
emitted. Nothing here opens a database session either - each function is pure over the
values it is handed, which is what lets the whole of slice B be unit-tested without a
turn.
"""
