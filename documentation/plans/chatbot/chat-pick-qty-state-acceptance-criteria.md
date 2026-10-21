# UAC: CHAT-PICK-QTY-STATE (parity: state path = old path)

Plan: `PLAN-chat-pick-qty-state-22oct.md`. Every criterion holds with the state heading ON and with it OFF; the OFF
result is today's behaviour and must not change.

1. A dealer has a parked stock-quantity task. They ask for an unknown code and get "Did you mean: 1. A 2. B 3. C".
   They reply `1`. The reply is about A (stock / the quantity ask for A). The parked task's question is not asked and
   the parked task stays parked.
2. Same as 1, replying with the code itself (`a` in any case), or quoting the did-you-mean message: same result as 1.
3. The bot asked "How many units of A?" and an older numbered list is still on record. The dealer replies `2`. 2 is
   stored as the quantity of A; the bot does not switch to row 2 of the older list, and does not ask the same question
   again.
4. Same as 3, with a unit word (`2 pcs`, `2 unit`): same result as 3.
5. Same as 3, but the dealer quotes the older list message: the reply picks row 2 of that list (the #1823 quoted-list
   rule is kept).
6. "clear all" (and "start over" / "reset", Malay and Chinese variants as the parser reads them): the state path gives
   the same result as the old path (measured by the v63 replay, recorded in the PR): when the parser marks the turn a
   topic reset, no task, no stored list and no open question survive, on both paths.
7. No reply names an ID or UUID; no contact data in any committed fixture.
8. A multi-product stock answer that numbers its items 1..11 and its did-you-mean 12, 13, 14 and also carries the
   zero-stock escalate offer: the stored question is the numbered did-you-mean (positions 12-14) and the reply shows no
   escalate sentence; `13` next turn answers the 13th option. Both paths. An answer with no question of its own keeps
   today's offer.
