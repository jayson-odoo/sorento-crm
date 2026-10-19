# UAC: CHAT-STATE round 7 - LAST-REFERENT

Plan: `PLAN-chat-state-last-referent-r7-20oct.md`. Owner rule 20 Oct 07:04; crew a51605376 (a). All criteria on the
state path unless marked; parser verdicts are fixtures (the prompt template is CHAT-CODE-LOOKUP's).

- **AC-R7-1** (audit row 6). The bot asks how many units of MKS9505-GM-HC; the next reply lists two promotion files;
  the dealer sends "1" (parser: reference_positions [1] or demand_qty 1). The turn picks promotion file 1 (the first
  listed file). The MKS9505-GM-HC stock task is NOT answered with 1 and stays held.
- **AC-R7-2** (26 Sep picker-not-sticky ruling holds). The bot lists products, the customer picks one, the bot asks
  how many units; "2" is that product's quantity, never item 2 of the list.
- **AC-R7-3**. A pending question (which-one roster, clarify, company pick) asked after a list: a number answers the
  pending question. A list shown after a pending question: the number picks from the list.
- **AC-R7-4**. A newer list replaces the older one and its stamp. A turn that shows nothing keeps the list and its
  original stamp. A question with no options asked after a list makes the question the referent; the list stays
  stored but is not the open referent.
- **AC-R7-5**. Every row kind of a shown list is pickable: product, file / attachment, promotion, order. A pick writes
  the row's key into the matching Subject axis. A row with no key fails the pick (the bot asks), never a guess.
- **AC-R7-6**. The State block shows exactly one open referent (`open_referent`). An older stock task under a newer
  list prints as a held task, not as the open question.
- **AC-R7-7** (state off). Byte-identical: no list recorded, the legacy bare-number rule unchanged.
- **AC-R7-8**. The two code pins of the old rule (test_chat_state_apply.py:488, test_stock_ask_ht26_r5_picker_not_sticky.py
  :101) change with the owner-rule cite; no other existing test changes. The prompt-text pin (same file :127) moves
  with CHAT-CODE-LOOKUP's template change (P1), not here.
- **AC-R7-9**. A harness proves the state path ran (apply_changes counter); every new test uses the real list shape
  the tail writer receives (fixtures carry the real data shape).
