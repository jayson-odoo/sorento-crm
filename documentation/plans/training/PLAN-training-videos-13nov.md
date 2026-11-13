# PLAN: training videos for the 16 Nov and 18 Nov meetings

Status: Build (behaviour card answered by crew 13 Nov; drafts on main for pipeline proof, finals after crew says functions are frozen). Track: M, no product code (recordings only).

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

Not the public repo. Crew answers 13 Nov:

- Voice-over: Kokoro (open-source, offline, no key, no cost). English narration; Malay as a
  `.ms.srt` subtitle file that needs a native read before use.
- Chatbot video (#4) needs a live LLM: crew runs its one command on the local test copy.
- Spare part request (#8) waits for PR #2381 (lane SPARE-PART-ORDER-REQUEST) to merge.
- Delivery: a private claude.ai page (drafts and finals); fallback is crew re-recording locally.
- The recorder (specs + fake seeder) is committed under `scripts/training-videos/`; videos never are.

## Re-run contract

One command re-records one video on any head: `scripts/training-videos/record.sh <video-id>`.
Each step of a video spec holds its action, its caption (en), its Malay subtitle (ms) and its
voice line, so an amendment to a screen is an edit to the step and a re-run, not a re-shoot.
