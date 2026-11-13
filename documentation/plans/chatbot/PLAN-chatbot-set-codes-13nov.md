# PLAN: CHATBOT-SET-CODES (a typed set code answers the set and its members)

Status: Plan (discovery; behaviour card to follow as a crew-ask). Track: size M, lead pattern, cloud lane.
Phase 1 slice 3 of chatbot plan v2 (owner approved 12 Nov 17:28). Follows PR #2370 (code matching, merged 13 Nov).

Goal: a registered set code typed in any dash/space/case form resolves to the set and its member products through the
set membership table, instead of a wrong "Did you mean <other code>?". A part's role comes from the membership row,
never from a letter in the code. The "X" letter rule in `product_code_family.py` is replaced by catalogue data.

Out of scope: dealer close-code offers (CHATBOT-CLOSE-CODES), size offers (slice 4), prompt changes, engine stale-typo
path.
