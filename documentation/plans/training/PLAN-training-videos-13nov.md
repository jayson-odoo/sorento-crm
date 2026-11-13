# PLAN: training videos for the 16 Nov and 18 Nov meetings

Status: Plan (behaviour card pending owner answer). Track: M, no product code (recordings only).

Lane: TRAINING-VIDEOS. Owner ask 13 Nov: short screen-recorded videos of the real app flows with
captions and a voice-over.

## Videos (one task per video, 1 to 3 minutes each)

Priority 1 (Mon 16 Nov, sales team):
1. Price tag request
2. Managing dealer contacts (Sales > Dealer access > Add people)
3. Filing an issue / complaint
4. Chatbot "did you mean" offers and stock answers (Chatbot Console)

Priority 2 (Wed 18 Nov, Project CS):
5. Split delivery
6. Order inquiry (OI) lines and states
7. Order change notice (only once merged to main)
8. Spare part request (CS requests, CS manager approves)

## Method

- App runs in the lane's cloud sandbox (backend + frontend dev server), Postgres seeded with
  fake-but-realistic records shaped like real cases. No real names, phones or prices.
- Recording scripts (Playwright, 1280x720, slow pacing, visible cursor + click highlight) live
  outside the repo; nothing recorded is committed (public repo).
- Captions as .srt (free baseline); voice-over per the owner's answer to the behaviour card.

## Delivery

Not the public repo. See the behaviour card (crew-ask) on the lane PR.
