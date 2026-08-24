# PLAN (n8n hand-off) - Multi-modal ideation capture

**Status:** Contract ready to hand to the n8n session (2026-07-20). The sorento + shared-service
sides are **built + tested** on `feat/ideation-capture-parity` (sorento) and
`feat/ideation-capture-embed-parity` (shared-service). This doc is the spec the n8n workflow must
implement; nothing here needs sorento/shared-service changes.

**Governing decisions:** `PLAN-ideation-ideate-intent.md` DC-1..DC-10 + UAC Group F. Program spine
§5.1/§5.5. This is the n8n slice of Phase 2f.

---

## 0. What n8n owns vs what sorento owns

The whole binding/lookback/snapshot/vision/state machine lives **in sorento** behind one endpoint.
n8n stays thin - it does **three NLU jobs** and relays:

| n8n owns | sorento owns (already built) |
|---|---|
| **STT** - transcribe inbound voice notes (Whisper) into `message_text` (DC-5) | Media lookback via Respond List Messages, the numbered menu, snapshot to R2, vision caption |
| **Reference-position extraction** → `media_selection` when a media menu is outstanding (DC-7) | `pending_media` / `seen_media_ids` state, selection resolution, attachment assembly |
| **`is_new_idea` extraction** - semantic "different idea" flag with open-draft topic context (DC-10) | Draft discard + fresh-draft restart |
| Routing + relay of `reply_text`; that's it | Writing `session_vars` (the endpoint persists it itself) |

n8n does **not** need to write `session_vars` for this feature - the `/turn` endpoint writes it. n8n only
**reads** `session_vars.ideation` to decide whether a reply is a media selection.

---

## 1. The endpoint contract (unchanged transport, new fields)

`POST {CRM_BASE_URL}/api/v1/external/ideation/turn` - `Authorization: Bearer {EXTERNAL_API_KEY}`.

**Request body:**
```jsonc
{
  "respond_io_id": "<respond contact id>",   // required
  "message_text":  "<this turn's text>",      // required - for VOICE, the Whisper transcript
  "submitter_name": "<Respond profile name>", // optional (WS-A fallback)
  "media_selection": "1,3",                    // optional - see §3 (only when answering a media menu)
  "is_new_idea": true                          // optional - see §4 (semantic restart)
}
```
The retired `audio_attachment_ref` is **gone** - do not send it. The audio *file* is captured by
sorento's lookback like any other media; n8n only sends the transcript as `message_text`.

**Response body (relay `reply_text`; the endpoint already persisted `session_vars`):**
```jsonc
{ "status": "collecting|review|complete|duplicate|unconfigured|error",
  "reply_text": "…",         // send this to the user verbatim (may include the media menu)
  "link": "https://…/ideas/123",  // present on complete
  "session_vars": { … } }     // the FULL updated blob (already written server-side; informational)
```

---

## 2. STT - inbound voice → `message_text` (DC-5)

A voice-only WhatsApp message has no text to classify, so transcribe **before** classification:

1. Inbound message is a voice note → download the media (Respond gives a CDN url) → **Whisper**
   (OpenAI `audio/transcriptions`, multilingual - handles EN/Malay/Chinese code-switching).
2. Put the transcript into `message_text` and run it through the **normal** parser/classifier.
3. If it classifies `ideate` → call `/turn` with `message_text = transcript`. Do **not** send any audio
   ref - sorento's lookback picks up the voice file from Respond and attaches it.

Images/video/files need **no** n8n handling - sorento's lookback pulls them from Respond directly.

---

## 3. Reference-position extraction → `media_selection` (DC-7)

When sorento shows the media menu, it stores `session_vars.ideation.pending_media`. On the **next** turn:

1. **Read** `session_vars.ideation.pending_media` for the contact (conversation-variables GET, the same
   read you already do to resume a draft).
2. If it is **set**, run the parser to extract a **reference-position** from `message_text`:
 - a position reference present (e.g. `1,3`, `1 and 3`, `first and third`, `all`, `none`) →
     send it as `media_selection` (pass the raw string; sorento parses digits/`all`/`none`).
 - **no** position reference (the user said something else - a field answer, a new question, an
     interrupt) → **do NOT** send `media_selection`; route the turn normally (classify as usual). Sorento
     treats the absence as "menu dismissed" and proceeds - a mid-selection CRM interrupt is never swallowed.
3. This is the ONLY place `media_selection` is sent. If `pending_media` is not set, never send it.

> Trust the LLM only to **extract positions** (a narrow, reliable task), gated by `pending_media` being
> set - never to *classify* the reply. This matches your existing "selection indicator in session_vars"
> pattern for other menus.

---

## 4. `is_new_idea` extraction (DC-10)

When a turn classifies `ideate` **and** `session_vars.ideation.draft_id` is already set (a draft is open),
ask the parser one semantic question, giving it the open draft's topic as context:

> "Is the user starting a **genuinely different** idea (not continuing the open one about *<draft topic>*)?"

- Yes → send `is_new_idea: true`. Sorento discards the old draft and opens a fresh one.
- No / unsure → omit it (default is **resume**). There is **no time-based expiry** - topic, not time, is
  the discriminator, so never expire a draft on age.

Extract this **semantically**, not by keyword-matching "new idea" (per the no-overfit rule).

---

## 5. Routing flow (per inbound turn)

```
inbound message
  ├─ voice? → Whisper → message_text            (§2)
  ├─ read session_vars.ideation for the contact
  ├─ pending_media set?
  │     ├─ parser finds a position reference → POST /turn { …, media_selection }   (§3)  ─┐
  │     └─ no position → fall through to normal classify                                  │
  ├─ classify(message_text)                                                               │
  │     ├─ ideate?                                                                        │
  │     │     ├─ draft open? → extract is_new_idea → POST /turn { …, is_new_idea? }  (§4) │
  │     │     └─ else        → POST /turn { … }                                           │
  │     └─ non-ideate → existing CRM handling (unchanged)                                 │
  └─ relay response.reply_text to the user  ←──────────────────────────────────────────┘
```

Everything else (draft resume by `draft_id`, the confirm/review loop, session_vars writes) is unchanged
from the existing text `ideate` flow - this only adds the STT front-step and the two extractions.

---

## 6. Acceptance (n8n-side)

- Voice-only idea → transcribed → captured (idea `raw_text`/fields come from the transcript).
- After sorento appends "which relate? 1,3/all/none", a reply of `1,3` reaches `/turn` as `media_selection`;
  a reply of "it saves 2 hours" does **not** (routes as a normal field answer).
- "actually, different idea …" on an open draft sends `is_new_idea:true`; "and also it should…" does not.
- No `audio_attachment_ref` is ever sent.
