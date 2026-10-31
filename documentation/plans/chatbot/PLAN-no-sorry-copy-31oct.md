# PLAN: NO-SORRY-COPY (31 Oct 2026)

Status: in progress. Small fix track by size and scope (copy only, no auth/RBAC, no new ingest),
but it carries ONE data-only migration because four of the lines are DB-published prompt
registry keys (see "Why a migration").

## Owner rule

30 Oct 2026 (feedback-chatbot-no-sorry-replies): the bot never says "sorry" or "busy". Each line
is an honest, plain statement in the shape of #2054's read-failed line ("I couldn't read that
just now. Please send it again.").

## Scope

Every customer-facing (and console) reply line in backend `app/` and the MCP presenter that
says sorry / maaf / 抱歉 / 对不起 / busy, in en, ms and zh. Meaning kept, no new behaviour.

Out of scope:
- `IDEATION_CAPTURE_ERROR` (`chatbot_reply_copy.py`): owned by AGENTIC-IDEATE (#2038), owner
  ruling 31 Oct.
- `llm_call.RATE_LIMITED_REPLY`: already retired from every reply path; kept only as the banned
  text the fail-triage tests check replies against.
- LLM prompt instructions in `ai_prompt_registry.py` ("apologise plainly", "Do not apologise more
  than once"): they are instructions, not hard-coded replies. Listed in the PR as a follow-up.
- Recorded replay transcripts under `tests/chatbot/replay_turns/` and node fixtures: history, not
  copy.

## Why a migration

`chatbot_reply_not_supported`, `chatbot_reply_escalate_offer`, `chatbot_reply_escalate_offer_no_team`
and `chatbot_reply_access_denied` are prompt registry keys. `render()` reads the published DB row,
so editing the Python fallback never reaches a live turn (`ideation_reply_fmt_prompts.py` names the
same mechanism). The migration publishes the new fallback ONLY where production still carries the
old default text, so an owner edit made in Settings > AI Prompts is left alone.

## Tests

`tests/chatbot/test_no_sorry_copy.py`: no string in the reply copy (every `chatbot_reply_copy`
value except the out-of-scope key, every `label_catalog` key and translation, and the named
refusal constants) contains sorry / maaf / 抱歉 / 对不起 / busy, case-insensitive. Plus a unit test of
the guarded publish.
