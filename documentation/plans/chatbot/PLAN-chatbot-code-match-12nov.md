# PLAN: CHATBOT-CODE-MATCH (stock code matching, close-code offers)

Status: Plan (behaviour card pending owner answers). Track: size M, lead pattern, cloud lane.

Lane brief: owner 12 Nov 2026. Goal: fewer stock "Couldn't find" replies, no wrong answers.
Code lookup change in the tool/resolver layer only; no parser prompt change.

Scope (from the brief, line numbers to be verified in discovery):
1. Pan/cistern (X / Y) form of a set code in the prefix probe.
2. Registered product set expands to member products on the stock path.
3. Size in the code matched against `trap_length` (250 mm unmarked default).
4. Dealers: up to 3 close codes from their own company instead of "refer to your salesman".
5. Rank candidates containing every typed part first; short token with many matches asks which one.
6. Candidate list in the trace; data list of water closets with no size (list only).

Rule (owner 12 Nov 15:10): answer directly ONLY when the code differs by dashes/spaces, is a
registered set, or is the default 250 mm size. Otherwise offer up to 3 and ask.

Discovery, behaviour card and UAC follow in this file and `chatbot-code-match-acceptance-criteria.md`.
