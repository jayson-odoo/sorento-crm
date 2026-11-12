# PLAN: CHATBOT-CODE-MATCH (stock code matching, close-code offers)

Status: Parked by the owner 12 Nov ~16:15 (full chatbot plan first); card v2 committed, no build. Track: size M, lead pattern, cloud lane.

Lane brief: owner 12 Nov 2026. Goal: fewer stock "Couldn't find" replies, no wrong answers.
Code lookup change in the tool/resolver layer only; no parser prompt change.

Scope (from the brief, line numbers to be verified in discovery):
1. Pan/cistern (X / Y) form of a set code in the prefix probe.
2. Registered product set expands to member products on the stock path.
3. Size in the code matched against `trap_length`; no default size (owner ~16:05).
4. Dealers: up to 3 close codes from their own company instead of "refer to your salesman".
5. Rank candidates containing every typed part first; short token with many matches asks which one.
6. Candidate list in the trace; data list of water closets with no size (list only).

Rule: answer directly ONLY when the code differs by dashes/spaces or is a registered set. Otherwise offer
up to 3 (with real sizes when sizes differ) and ask. Never assume a size (owner 12 Nov ~16:05).

Discovery, behaviour card and UAC follow in this file and `chatbot-code-match-acceptance-criteria.md`.
