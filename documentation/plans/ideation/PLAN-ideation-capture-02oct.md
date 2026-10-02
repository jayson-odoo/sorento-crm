# PLAN: Ideation capture from one message (IDEATION-CAPTURE)

Status: Plan. Behaviour card posted to the owner (crew-ask on PR #1444), waiting on answers before
any code. Track: full (L). Base `claude/ideation-crm-scout-k1b2e7` (PR #1438, IDEATION-IN-CRM).
Lane branch `claude/ideation-capture-0hctm7` (the sandbox only pushes this name).

## 0. Owner intent (2 Oct 2026, verbatim summary)

- Capture the idea from ONE message. Do not try to link other photos or messages to it.
- When a user states an idea: first find similar EXISTING ideas of their own. If similar ones
  exist, list them with their links and ask: edit one of these (link), or create a new idea from
  what was just said. If none are similar, create it directly.
- On create: create it up front with what was captured, give the link, and say the user can open
  it to fill the other fields that were not captured, LISTING those missing fields.
- A bare "want to submit idea" with no content: ask back for the minimal required information only.
- Link target: the CRM ideation page (#1438), NOT the public portal. The ideation page gets a
  "My ideas | All ideas" toggle.
- No auto name-matching of people or records.

## 1. What exists today (measured)

Paths: `BE` = `sorento_crm_backend/`, `FE` = `sorento_crm_frontend/`, `ss:` = the shared-service
repo (not readable from this sandbox; facts about ss below are quoted from the CRM plans that read
it, never re-verified here).

### 1.1 The chatbot ideate turn is a multi-turn draft today

- One entry: `handle_turn` (`BE/app/services/ideation_turn_service.py:761`), reached from the
  chatbot `ideate` lane through the MCP tool `crm_ideation_turn`
  (`BE/app/services/chatbot/lanes/ideate.py:33-71`).
- Each turn POSTs ss `/ideation/intake/create-idea` (`ideation_turn_service.py:66,660-689`) with a
  `draft_id` carried on `respond_contacts.session_vars.ideation` (`:800-838`, `:1041-1093`). ss
  answers `collecting` -> `review` -> (`confirm: true`) `complete`, plus `duplicate_candidate` /
  `voted` / `cancelled` (contract table, `PLAN-ideation-intake-redesign-24sep.md:88-101`).
- Even a first message carrying every field goes through `review`; there is no auto-complete
  (`ideation-ideate-turn-simulation-transcript.md:208`).
- Media lookback: every turn without an open menu pulls the contact's last 50 Respond messages and
  offers a "which of these files relate?" menu (`ideation_turn_service.py:890-931`, `:1036-1039`).
  This is exactly the "link other photos/messages" the owner wants gone.
- A 24h idle reminder + close sweep exists only because drafts exist (`:1106-1380`).
- The only required field is `problem`; `proposed_solution`, `impact`, `department` are optional;
  department is never asked (R1, R15, `PLAN-ideation-intake-redesign-24sep.md:186-200`). The
  extractor also produces a 1-8 word `title` (`ideation_turn_service.py:958`).
- Similarity today: ss runs a pg_trgm check against ALL non-test ideas of the product (not the
  submitter's own) and returns ONE `duplicate_candidate {idea_number, title}`
  (`PLAN-ideation-intake-redesign-24sep.md:201-204`). The threshold value lives in ss.
- The link ss returns is the public track page `{frontend_url}/public/ideas/{status_token}`
  (`PLAN-ideation-intake-redesign-24sep.md:101`), being moved to `/portal/ideas/{token}` on the
  CRM domain by SS-PUBLIC-LINK-BASE (`PLAN-ideation-in-crm.md:459-466`). ss does NOT return the
  idea's id on the intake response (`ideation_turn_service.py:174-190` reads every field it gets).

### 1.2 The CRM ideation page (#1438)

- Native list `/ideas` and detail `/ideas/{id}` over the gateway `/api/v1/ideation/*`
  (`BE/app/api/v1/ideation/ideas.py`). The list forwards only `filter` and `search` to ss
  `GET /embed/ideas` (`ideas.py:72`). There is no "mine" filter.
- `Idea` carries `submitterName` only, no submitter id, phone or email (`FE/types/ideas.ts:38-71`),
  so the CRM cannot tell whose idea it is without name-matching, which is ruled out.
- Edit (`PATCH /ideas/{id}`) needs `ideation.ideas.manage` (`ideas.py:162-163`, PLAN-ideation-in-crm
  section 0, 2nd ask Q2). A submitter with only `ideation.board.view` cannot fill the missing
  fields on their own idea today.
- The embed assertion identifies the CRM user by `sub`, `email`, `name` only
  (`BE/app/services/ideation_embed_service.py:138-149`); no phone.

### 1.3 Who the WhatsApp sender is in CRM terms

- A CRM user is linked to a WhatsApp contact by `users.respond_contact_id`
  (`BE/app/services/user_contact_link.py:109`, identity S3). That link is the only identity join;
  no name-matching. A contact with no linked user has no CRM login.

### 1.4 Toggle component

- `FE/components/ui/toggle-group.tsx`, already used as an "All | ..." segmented filter in
  `FE/app/(protected)/procurement-management/spo-allocations/components/SPOAllocationsList.tsx:472`.
  #1438's own `FE/components/ideas/IdeasViewToggle.tsx` is the List | Board twin. The page is
  #1438's, so the My | All toggle needs no Lavish mock (owner exception).

## 2. Behaviour card (posted as the crew-ask; answers land in section 3)

### 2.1 Conversation flow (examples)

The examples use messages from the 24 Sep ideation UX review
(`REVIEW-ideation-flow-ux-24sep.md:75-166`). This sandbox cannot read the dev chat or idea data
(no shared DB access), so these are the closest real messages on record, not a fresh pull.

E1, no similar idea of their own: create at once.
```
User: i have an idea, the price tag should show promo price in red
Bot:  Idea IDEA-0184 is in: Promo price in red on price tags
      Open it to add what I didn't catch: Proposed solution, Impact, Department, Photos or files.
      https://<crm>/ideas/<id>
```

E2, similar ideas of their own exist: ask first, nothing is created yet.
```
User: chatbot should remember what the dealer already asked before
Bot:  You already have ideas like this:
      1. IDEA-0151 Chatbot remembers past dealer questions - https://<crm>/ideas/<id>
      2. IDEA-0097 Dealer chat history in replies - https://<crm>/ideas/<id>
      Reply 1 or 2 to edit that one, or NEW to log this as a new idea.
User: new
Bot:  (E1's created reply, built from the ORIGINAL message, not from "new")
User: 1   (instead of new)
Bot:  Open IDEA-0151 to add this: https://<crm>/ideas/<id>
```

E3, no content.
```
User: want to submit idea
Bot:  Sure - what's your idea? Tell me what you'd like changed, in one message.
User: sales team keeps getting asked why the price is different from the sticker
Bot:  (E1 or E2, from this message)
```

E4, everything in one message: nothing is missing, so no missing-field line.
```
User: idea for sales team: show promo price in red so customers stop asking why the sticker
      is different, saves the sales team repeating themselves
Bot:  Idea IDEA-0185 is in: Promo price in red on price tags
      Open it to add what I didn't catch: Photos or files.
      https://<crm>/ideas/<id>
```

### 2.2 What "similar" means (proposal)

- Matched by ss's existing pg_trgm check (the one behind `duplicate_candidate` today) on the
  extracted title + problem, at ss's current threshold, so no new tuning knob.
- Own ideas only: ss ideas whose submitter is this sender (WhatsApp phone = the contact's phone,
  or captured in the CRM by the CRM user linked to this contact). Never by name.
- Live ideas only: not test, not archived, not merged into another.
- At most 3, most similar first. More than 3: the top 3 plus "See all your ideas:
  https://<crm>/ideas?view=mine".

### 2.3 Minimal required fields

- Only the idea itself (ss `problem`). The title is generated, never asked.
- A message with no idea content (E3) gets the one ask-back; a second content-free reply gets the
  same ask-back (no loop counter, no draft).

### 2.4 Missing-field list

The fields the one message did not give, in this order: Proposed solution, Impact, Department,
Photos or files (always listed, since photos are no longer picked up from the chat).

### 2.5 Edge cases

| Case | Proposal |
|---|---|
| Sender has no CRM login (contact not linked to a user) | Idea still created; reply gives the idea number and the portal track link instead of the CRM link (Q2). |
| Linked user lacks `ideation.board.view` | Same as no login (Q2). |
| Many similar | Top 3 + "See all your ideas" (2.2). |
| User replies to the similar-list with something else (not 1-3 / NEW) | Treated as a fresh idea message: the flow runs again on it; the held message is dropped. |
| User never answers the similar-list | The held message is dropped after 24h; no reminder, no close call (nothing was created). |
| ss down | Same graceful reply as today; nothing held. |
| Open old-style drafts at deploy | Left to the existing 24h sweep to remind and close; no new draft is ever opened. |

### 2.6 Defaults this lane takes without asking (simplest thing that works)

- Replies are fixed templates (the owner's wording from Q5), not the LLM composer: one message,
  one create, so there is no recap or review step left for the composer to phrase.
- The media lookback and media menu are removed from the ideate turn.
- No CRM-side copy of ideas: ss stays the system of record.

### 2.7 Questions (the crew-ask)

1. Where do "own ideas", the one-shot create and the idea id come from? (a) A small ss lane
   (SS-IDEATION-OWN, like SS-PUBLIC-LINK-BASE): intake gains a one-shot create that returns the
   idea `id`, plus a "similar own ideas" lookup by submitter (2.2); the embed API gains a
   `mine=true` list filter and an `isMine` flag; the CRM assertion gains a `phone` claim (the
   linked contact's phone) so ss can match WhatsApp-submitted ideas to the CRM user. This lane
   builds the CRM half against that contract and ships after ss merges. (b) CRM-only: the CRM
   keeps its own ledger of ideas it created and does the similarity search in CRM Postgres.
   Recommendation (a): ss already holds the submitter and the pg_trgm check; (b) misses every
   idea from before today and anything captured in ss, and adds a table and a migration.
2. Sender with no CRM login, or no Ideas permission? (a) Still create; reply with the idea number
   and the portal track link, (b) do not create; tell them to ask for a CRM login. Recommendation
   (a): the idea is not lost, and the track page is the only page they can open.
3. May a submitter edit their OWN idea's fields (problem, solution, impact, department,
   attachments) with only `ideation.board.view`? Today edit needs `ideation.ideas.manage`, so
   "open it to fill the other fields" fails for most dealers. (a) Yes, own ideas only (ss decides
   ownership via `isMine`, the CRM never guesses), status/merge/archive stay manage-only, (b) no.
   Recommendation (a).
4. Similar-list reply: (a) as E2 (numbered, up to 3, "Reply 1 or 2 to edit that one, or NEW to
   log this as a new idea"; a number replies with that idea's link), (b) links only, "Reply NEW
   to log this as a new idea" (editing is just opening a link). Recommendation (b): one fewer
   branch, and the link already is the edit path.
5. Customer-visible wording (owner's call), please approve or rewrite:
   - created: "Idea {IDEA-0184} is in: {title}" / "Open it to add what I didn't catch:
     {missing list}." / "{link}"
   - nothing missing: the middle line is dropped except "Photos or files" (E4).
   - ask-back: "Sure - what's your idea? Tell me what you'd like changed, in one message."
   - similar: "You already have ideas like this:" ... "Reply NEW to log this as a new idea."
   - no CRM login: "Idea {IDEA-0184} is in: {title}" / "Track it here: {portal link}".
   Recommendation: as written, English only (the LLM composer's language-matching is dropped
   with the composer, 2.6).

## 3. Owner answers

| Q | Answer |
|---|---|
| Q1 | **(a)**, crew 2 Oct: crew spawned ss lane SS-IDEATION-OWN (one-shot create returning id + idea number, own-similar lookup by phone / CRM user id and never by name, embed `mine=true` + `isMine`, assertion `phone` claim). This lane builds the CRM side against that contract; SS-IDEATION-OWN posts the final API contract and crew relays it. |
| Q2-Q5 | (with the owner) |

## 4. CRM side of the SS-IDEATION-OWN contract (provisional until ss posts the final one)

- Assertion: `mint_embed_assertion` gains a `phone` claim = `respond_contacts.phone_number` of the
  contact linked by `users.respond_contact_id`; the claim is absent when the user has no linked
  contact or the contact has no phone. That is the same value the chatbot sends ss as
  `submitter_contact_id` (`ideation_turn_service.py:980`), so the join is exact, never by name.
- Gateway list: `GET /api/v1/ideation/ideas?mine=true` forwards `mine=true` to ss
  `GET /embed/ideas`; any other `mine` value is dropped. `isMine` on each idea is relayed as ss
  sends it (the gateway already relays bodies unchanged).
- FE: `IdeaListParams.mine`, `Idea.isMine`; the list toolbar gets a My ideas | All ideas toggle
  (`components/ui/toggle-group.tsx`), default All ideas (today's behaviour), state in the URL as
  `?view=mine` so the chatbot's "See all your ideas" link opens the right view.

## 5. Slices

| # | Slice | Depends on | State |
|---|---|---|---|
| P1 | Plumbing: phone claim, `mine` forward, My/All toggle (section 4) | Q1 | red tests in progress |
| C1 | Chatbot one-message flow (section 2.1-2.5) | Q2-Q5 + SS-IDEATION-OWN contract | held |
| E1 | Own-idea edit with `ideation.board.view` | Q3 | held |
