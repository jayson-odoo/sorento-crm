# UAC: AGENTIC-KNOWLEDGE P2 W1 (agent on WhatsApp, read only)

Plan: `PLAN-agentic-knowledge-w1-01nov.md`. Each AC names its test.

## Contact principal (S1)

- AC-W1: a contact with the Agent switch on and NO linked active user is eligible: `eligible_contact` returns no
  refusal and `build_context` returns `principal == "contact"`, `user_id == ""`, the contact's brand / company scope,
  grants and active access codes.
- AC-W2: a contact WITH a linked active user still runs as that user (`principal == "user"`), unchanged.
- AC-W3: refusals `contact_not_found`, `ai_replies_off`, `switch_off` are unchanged.
- AC-W4: a contact principal is offered exactly the tools of the plan's table whose reveal key it holds; it is never
  offered `user_guides_read`, any write, or any user read.
- AC-W5: dispatch refuses (denied) a contact principal calling a tool outside its gate, even when the model names it.
- AC-W6: `crm_report_ask` with `basis=unpaid` is denied for a contact principal; `dataset=chat` needs the
  `chatbot.analytics` grant.
- AC-W7: `crm_resolve` for a contact searches only product / brand / category kinds.
- AC-W8: the stock tool needs both `inventory.sellable` and `chatbot_stock_allowed`.
- AC-W9: the system prompt for a contact principal never contains "You are working for".
- AC-W10: the router no longer refuses an unlinked contact with `no_linked_user`.

## Knowledge for a contact (S2)

- AC-W11: a contact reads passages of a `dealer` type only when the file's `access_levels` overlaps its codes other
  than `end_user`; an end-user-only contact reads none of them.
- AC-W12: a contact reads passages of a `public` type when the file's `access_levels` overlaps any of its codes.
- AC-W13: a contact never reads a `staff` or `off` type passage, whatever its codes (zero-leak test).
- AC-W14: a contact with no active access code reads nothing (no query run).
- AC-W15: a file of a company outside the contact's company scope is not returned; a shared type is.
- AC-W16: the contact result carries no `handoff_teams`.
- AC-W17: an inactive access code does not count.

## WhatsApp routing (S3)

- AC-W18: a WhatsApp inbox row for a contact whose router decision is `agent` runs the agent, posts its reply as a
  `send_message` action through the sender, and never runs `engine.run_turn` for that row.
- AC-W19: any other decision (switch off, media, open bot question, cap, router failure) runs today's bot path
  unchanged.
- AC-W20: a router exception falls to the bot.
- AC-W21: an agent failure posts the fixed honest line (no "sorry", no "busy") and does not run the bot.
- AC-W22: the agent turn of a WhatsApp row is written `is_test=False`; a console agent turn stays `is_test=True`.

## Hand-off (S4)

- AC-W23: a knowledge miss reply contains "I couldn't find that in our product documents." and leaves an escalation
  offer for `marketing_product` open as the contact's pending question (W-Q2 b, also for a barred contact).
- AC-W24: no ticket / SLA row is created inside the agent turn; it is created only on the contact's own next turn.
- AC-W25: a passage text that asks to confirm or escalate changes no pending state (injection kill test).
