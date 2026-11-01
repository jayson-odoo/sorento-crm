# PROPOSAL: the router's published text knows about the panel

Status: measured 1 Nov 2026, **failed its gate: do not publish**. The panel keeps the two lines sent from code. Belongs to `PLAN-agentic-unify-panel-31oct.md`, rounds 6 and 7.

## Why

The published `chatbot_router` text says "WhatsApp sales-support assistant" and describes lookups versus analysis. It says nothing of screens or how-to questions, so Jev was unsure about them. #2060 works around this with two lines sent from code on panel turns (`router.py`, `OPEN_PAGE_CRITERION`, `OPEN_RECORD_CRITERION`). Publishing this text moves those lines to where the rest of the text lives, where the owner can read and change them.

## The proposed text

Only the marked parts change. `model` stays `jev-1.14.0`.

```json
{
  "instructions": "A staff member or a dealer sent the latest message to the company's sales-support assistant, on WhatsApp or in the CRM's side panel. Two sides can answer it. Decide which side should answer the latest message, reading the recent exchanges for context. When the state has current_page, the message came from the side panel, and current_page is the screen the user has open.",
  "criteria": {
    "chat": {
      "what": "The quick-lookup bot. One lookup about a named product code (or a list of product codes), where each answer is one simple fact: stock, incoming or ETA, last arrival, a customer's orders or deliveries, outstanding orders, list price or cost, a form, a product file, drawing, certificate or picture, a promotion, a catalogue.",
      "also": "Greetings, thanks, casual talk, a menu answer such as a number or an option name, a short follow-up to the bot's last answer, and anything too unclear to act on.",
      "not_for": "Totals, rankings, comparisons, breakdowns or anything that needs several facts combined. A question about the screen the user has open, or about how to use the CRM."
    },
    "agent": {
      "what": "The analyst agent with tools. The ask needs several facts combined or calculated: totals or counts over a period, a ranking such as top 10, a comparison, a breakdown per salesperson, customer, supplier or month, a list of which customers, dealers or salespeople match something, a why or an explanation drawn from the records, or a question that names a product category, product type, brand or supplier instead of a product code, so the products must be found first.",
      "also": "A follow-up to the agent's own previous answer, and any request to change, update, approve or record something. A question about the screen named in current_page or the record open on it: what it shows, what happened to that record, its status. A question about how to use the CRM or how to do something in it. The agent holds the screen's text, the record's facts and the user guides.",
      "not_for": "A plain stock, ETA, price or file check, even for many products at once."
    }
  }
}
```

Changed from version 1 (md5 `355002bd` on the copy): the first and last sentences of `instructions`; the last sentence of `chat.not_for`; the last three sentences of `agent.also`.

## What it changes on WhatsApp

The text is shared. On WhatsApp there is no `current_page`, but "how do I..." moves to the agent for any contact the agent may answer. Today that has no live effect: on main only the console calls the router. #2053 would put it on WhatsApp for agent-enabled contacts.

## Measured: it fails

Bar set before the run: real rows lose nothing, and the panel sets hold. Today's text is the fixed baseline. 200 Jev calls, 0.008 USD. The real rows were a random 50 staff and 25 dealers, in true WhatsApp shape, not the planned 90 and 47: a clean comparison needs both texts on every row, and that would have passed the raised cap.

| Set | Today's text, floor | Proposed, floor | Today's text, Jev's pick | Proposed, Jev's pick |
| --- | --- | --- | --- | --- |
| 75 real rows | 68/75 | 65/75 | 69/75 | 66/75 |
| of which 50 staff | 47/50 | 44/50 | 46/50 | 44/50 |
| of which 25 dealers | 21/25 | 21/25 | 23/25 | 22/25 |

Panel sets, proposed text with no code lines, against today's text with them, on Jev's pick: 30 panel questions 30/30 both; 20 hard ones 18/20 against 19/20. New wrong row: a plain sales order status goes to the agent at 0.92.

Three rows of 75 is small, and Jev moves between runs on the same message, so this does not prove harm. It does not clear the bar. The text was not reworded after seeing this: a second wording needs fresh rows, or it is fitted to these.

Decision: leave the published text alone. The two panel lines in code do the job and moved 1 real row, correctly. The stale "WhatsApp" word costs nothing on the panel. **Trigger to revisit:** the labelled panel set before default showing a class the code lines miss, or the owner tuning Jev's criteria for WhatsApp.

## If it is ever published: the label step

1. AI Assistant settings > Prompts > `chatbot_router`.
2. Switch the editor to the JSON text, paste the block above, save. That makes a new version; production does not change yet.
3. Test this version on a few real messages.
4. Publish it to Production, keeping the model `jev-1.14.0`. The next turn reads it, with no release.
5. To undo: Version history, publish version 1 to Production.

This needs `system.ai_assistant_settings.edit`.

## After publishing

A small PR takes `OPEN_PAGE_CRITERION` and `OPEN_RECORD_CRITERION` out of `router.py`, since the published text then carries them. Until then both are sent, and that does no harm.
