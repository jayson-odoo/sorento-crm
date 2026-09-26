# PLAN - Chatbot memory: contact profile, episodes and turn context under a token budget

Status: DRAFT 26 Sep 2026, awaiting the owner's answers to the grill questions at the end.
Track: full (migration, parser prompt change, staff screen, expected diff well over 300 lines).
Issue #1282. UAC: `chatbot-memory-acceptance-criteria.md` (AC-MEM001 to AC-MEM099), written
to the recommendations in "Grill questions for the owner"; an answer that differs rewrites the
matching ACs before any code.

Core or module: CORE. This is the existing chatbot's memory shelf, not a new installable
capability. No new module key, no new Postgres schema; the rows stay where they are today
(`public.conversation_frames`, `public.respond_contacts.chatbot_profile`, `chatbot.turns`).

## Contents

1. The owner's words (binding)
2. What exists today (measured 26 Sep 2026 at origin/main 51d30ccc5)
3. What this plan changes, in one paragraph
4. Layer 1: contact profile
5. Layer 2: episodes
6. Layer 3: turn context assembly and the token budget
7. Out-of-boundary replies (with ten example exchanges)
8. How each layer is evaluated
9. Slices S0 to S4
10. Simplest thing, not built (and the trigger that would build it)
11. Risks
12. Relation to "an enterprise version of Claude Code"
13. Grill questions for the owner

## 1. The owner's words (binding)

Issue #1282, 26 Sep 2026 about 13:50Z, verbatim:

> "I believe our chatbot plan includes things like episodes and even user profile. Because I
> think now we are using focus only to survive multiple turns. But I think we have episode as
> well and profile so that, like Claude, you got a user profile that is a memory that stores
> everything about that user, and also episode, for some context management so that it feels
> more human and conversational when you are talking with the chatbot. Because now our chatbot
> fails constantly in a human conversation: when things are asked out of the boundary the
> chatbot struggles to understand because it's a one-dimensional reply chatbot. So I think we
> need to look into that and I'm also interested to discuss how to implement this so that we
> can be an enterprise version of Claude Code."

And the issue's constraint: "Token budget matters: the parser prompt is already ~22.8k tokens
against a 200k tokens/min org limit (#1275)."

Read as requirements:

- R1. A per-contact profile that remembers the person and their business.
- R2. Episodes: context management so the conversation survives beyond the one focus.
- R3. Out-of-boundary messages get a human reply, not a one-dimensional one.
- R4. No token growth that eats the #1275 headroom.
- R5. The "enterprise Claude Code" direction is a discussion, not a deliverable of this plan
  (section 12 maps it; grill question 14 asks where it goes).
