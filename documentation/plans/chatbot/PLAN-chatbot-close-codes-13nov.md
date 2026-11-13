# PLAN: CHATBOT-CLOSE-CODES (dealer gets up to 3 close codes)

Status: Plan; card v1 filed as crew-ask 13 Nov, waiting on owner Q1-Q5 and crew data (G5). Track: size M, lead pattern, cloud lane.
Chatbot plan v2, Phase 1 slice 2. Builds on PR #2370 (CHATBOT-CODE-MATCH, merged 13 Nov).

Goal: a dealer who types a code that does not exist (one wrong letter, a missing prefix) gets up to 3 close codes from
his own company as "Did you mean <code>?" instead of "Couldn't find. Please refer to your salesman."

Card: `CARD-chatbot-close-codes-13nov.md`. UAC draft: `chatbot-close-codes-acceptance-criteria.md`.
Slices and the reuse list follow once the answers land.
