# UAC: CHAT-STATE round 7 - LAST-REFERENT v2 (owner confirmed 20 Oct ~07:55)

Plan: `PLAN-chat-state-last-referent-r7-20oct.md`. Owner r40 case-12 ruling (a quoted reply follows the quoted
message); owner 20 Oct ~07:40 ("how many outranks a newer list"). Parser verdicts are fixtures. The quote enters as
the real respond.io `replyTo` shape the engine reads (engine.py:1186-1190, 1236-1238).

Audit row 6 shape for every case below: the bot asks how many units of MKS9505-GM-HC; the dealer asks about
promotions; the bot lists two promotion flyers; the dealer sends "1".

- **AC-R7-1** (no quote; today's rule, guard). "1" is MKS9505-GM-HC x 1. No flyer is picked.
- **AC-R7-2** (quote of the flyer list). "1" quoting the flyer-list message picks flyer 1: the reply sends that
  promotion's flyer, fetched by its id (promotion_ids), and the MKS9505-GM-HC task is not answered with 1.
- **AC-R7-3** (quote of the how-many). "1" quoting the how-many message is MKS9505-GM-HC x 1, even though the flyer
  list is newer.
- **AC-R7-4** (nothing open). The bot lists promotion flyers with no question open; "2" picks flyer 2 and sends it,
  fetched by id. Same for a list of files ("2" sends file 2 by its attachment id) and a list of orders ("2" answers about order 2 by its id).
- **AC-R7-5** (question open, no quote). With any question open (how-many, which-one roster, clarify, company pick),
  a promo / file / order row is not pickable: the number goes to the open question exactly as today.
- **AC-R7-6** (keys). A promo row in `last_list` carries kind "promotion" and the promotion id; a file row carries
  its attachment id; an order row carries its order id; neither id is ever printed in a reply. A row with no id is never picked (the bot asks).
- **AC-R7-7** (stamp). `last_list` records the turn that showed it; a turn that shows nothing keeps the list and its
  stamp; a question's options keep the question's turn (same input, same focus on every pass).
- **AC-R7-8** (state off). Byte-identical except the presenter's extra top-level row id, which no state-off reader uses.
- **AC-R7-9**. The v1 pins return to today's rule (test_chat_state_apply.py:488, test_stock_ask_ht26_r5_picker_not_sticky.py
  :101); a harness proves the state path ran (apply_changes counter); fixtures carry the real presenter / replyTo shapes.
