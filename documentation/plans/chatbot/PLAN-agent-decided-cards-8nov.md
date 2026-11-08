# PLAN: decided Confirm cards must not come back on later cards (AGENT-DECIDED-CARDS)

Status: built, in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Problem

After the user Cancels (or Confirms) a Confirm card in the panel, the next message in the same thread
produces a card that re-includes the decided rows (crew live check of #2247, 6/6 runs).

Cause: the model's history holds only each turn's user text and reply (`agent/memory.py` `_turn_messages`);
a panel Cancel/Confirm is saved only as a panel message (`panel_service._append_outcome`), so the model never
learns the card was decided; and the batch tool told it to re-send the WHOLE table (`agent/batch.py`).

## Fix

1. History: after the turn that proposed a card, the model sees a fact line naming the decision
   (confirmed / cancelled / expired) and the decided rows, built by code from `chatbot.agent_actions`.
2. Batch tool description: propose only rows still open in the CURRENT request; never rows from a decided card
   unless the user asks for them again.
3. Code guard in `batch.propose_rows`: a row whose step is identical (tool + args) to a step of a card cancelled
   in this conversation is skipped, with the reason "from your earlier cancelled table", unless the latest user
   message re-requests it (says the row's customer/contact values, or "again"). Same guard for steps already
   done by a confirmed card ("already done").

## Tests (red first)

`tests/test_agent_decided_cards.py`: cancel -> follow-up and confirm -> follow-up for the grant tool;
history carries the decision line.
