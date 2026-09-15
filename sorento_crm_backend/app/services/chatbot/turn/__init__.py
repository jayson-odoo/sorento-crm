# The turn re-architecture's pure core (PLAN-chatbot-turn-rearch.md, S2, AC-1520).
# state.py, policy.py, pending.py, narrow.py, reconcile.py, plan.py, apply.py, route.py.
# No I/O anywhere in this package; no imports from chatbot.head / chatbot.dialogue /
# chatbot.tail / chatbot.engine (AC-1520's import-boundary guard).
