# PLAN: training videos for the 16 Nov and 18 Nov meetings

Status: Review (14 Nov: drafts of #1 #2 #3 #5 #6 #7 #8 recorded on current main and delivered on the private page; #7 order change notice 1:30 and #8 order request 1:58 recorded in the cloud sandbox from seeder part p3; #4 spec ready, recording deferred by crew until the chatbot PRs #2395 + #2394 are live; finals re-recorded with the same commands after crew says functions are frozen). Track: M, no product code (recordings only).

Lane: TRAINING-VIDEOS. Owner ask 13 Nov: short screen-recorded videos of the real app flows with
captions and a voice-over.

## Videos (one task per video, 1 to 3 minutes each)

Priority 1 (Mon 16 Nov, sales team):
1. Price tag request (`p1-price-tag-request`)
2. Managing dealer contacts, My Work > Dealer access > Add people (`p1-dealer-access`)
3. Filing an issue / complaint (`p1-complaint`)
4. Chatbot "did you mean" offers and stock answers, Chatbot Console (`p1-chatbot-did-you-mean`, spec only)

Priority 2 (Wed 18 Nov, Project CS):
5. Split delivery (`p2-split-delivery`)
6. Order inquiry (OI) lines and states, recorded as CS, view only (`p2-order-inquiry`)
7. Order change notice, recorded as CS: read an approved notice and mark it done (`p2-order-change-notice`, p3 seed)
8. Spare part request (UI name: Order Request), CS raises and the CS manager edits + approves (`p2-order-request`, p3 seed)

## Method

- App runs on the lane's own stack (local since 14 Nov, after the cloud sandbox kept restarting):
  backend + worker + frontend dev server on lane-own ports, a private Redis, and a throwaway
  Postgres DB `sorento_ci_tv` seeded only with invented records shaped like real cases
  (`scripts/training-videos/seed_fake.py`). Never the shared dev DB. No real names, phones or prices.
- Recording scripts (Playwright, 1280x720, slow pacing, visible cursor + click highlight, step
  captions) are committed under `scripts/training-videos/`; the recordings themselves never are
  (public repo; `out/` is gitignored).
- Captions as .srt (free baseline); voice-over per the owner's answer to the behaviour card.

## Delivery

Not the public repo. Crew answers 13 Nov:

- Voice-over: Kokoro (open-source, offline, no key, no cost). English narration; Malay as a
  `.ms.srt` subtitle file that needs a native read before use.
- Chatbot video (#4): crew 14 Nov 09:20 deferred it (answers change with #2395 + #2394, and the dev
  OpenAI key has no credit); the spec is kept ready for crew to re-open.
- Spare part request (#8): PR #2381 merged, recorded 14 Nov.
- Delivery: a private claude.ai page (drafts and finals); fallback is crew re-recording locally.

## Re-run contract

One command re-seeds and re-records one video on any head:
`TV_BASE_URL=<lane frontend> TV_API_URL=<lane backend>/api/v1 scripts/training-videos/record.sh <video-id>`.
`record.sh` runs the seeder part for the video's prefix first (p1 or p2; the seeder resets the rows
earlier takes created), then the recorder. Both URLs are required, with no default, so a take can
never land on another lane's stack. Each step of a video spec holds its action, its caption (en),
its Malay subtitle (ms) and its voice line, so an amendment to a screen is an edit to the step and
a re-run, not a re-shoot.
