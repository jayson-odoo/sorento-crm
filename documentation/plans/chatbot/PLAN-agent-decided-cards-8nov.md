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
   (cancelled, or confirmed with each row's outcome) built by code from `chatbot.agent_actions`
   (`actions.decision_note`, `memory.decision_notes`). An expired card is not a decision (a newer card replaced
   it) and gets no line. Compaction folds the line in with its turn.
2. Batch tool description: propose only rows still open in the CURRENT request; never rows from a decided card
   unless the user asks for them again.
3. Code guard in `batch.propose_rows` (`actions.closed_rows`, `batch._closed_reason`): a row identical to a step
   of a card cancelled in this conversation (same write, same phone, same arguments compared without case,
   spacing or list order) is skipped as "From your earlier cancelled table", and one a confirmed card already did
   as "Already done on your earlier confirmed table", unless the latest user message names the row by phone
   (last 9 digits, any formatting) or by name. The newest card holding a row decides, so a row asked for again
   stays open; a step that failed or did not run stays open.

## Tests (red first)

`sorento_crm_backend/tests/chatbot/agent/test_agent_decided_cards.py`: cancel -> follow-up and confirm ->
follow-up for the grant tool; the history line; asking again by phone, name or a pasted list; the same person
asked for something else; a failed row of a partial confirm; compaction.
