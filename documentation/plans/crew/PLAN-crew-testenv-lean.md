# PLAN: CREW-TESTENV-LEAN (lean test copies)

Status: Built in crew-lean 5e5fa05 (238 OK, review clean, trial done 12 Nov 23:51); swap-in by crew pending (lean.patch). Card answered by crew 12 Nov: Q1 b, Q2 yes, Q3 b, Q4 a; trial on slot 1; cap 6 + drop .next/cache (ruling a98692627). Track: M (crew tool, not the product). Code lives in
a COPY of crew at `foundryx/crew-lean/` (git repo of its own); crew swaps it in after review. This sorento PR carries
the plan only.

## Journey

Owner, 12 Nov ~18:05: test copies are the bottleneck because of RAM; more copies should fit. Evidence
`crew/state/files/TESTENV-CAPACITY/measure-12nov.md`: a copy is 3.6-4.3 GB footprint (`next dev --turbopack`
2.5-2.9 GB, `uvicorn --reload` 1.0-1.4 GB); swap 93% used with 3-4 copies while `memory_pressure` reads 32% free, so
the gate (`crew:1039`, `min_mem_free_pct = 15`) is blind; cap `max_testenvs = 4` (`crew.toml:45`).
Re-measured 12 Nov ~19:00: `vm.swapusage` total 15360M used 14074M free 1286M (the total shrank from 18432M: macOS
grows and shrinks swap files on demand, free stays ~1.3 GB); `memory_pressure` 33%; compressor occupies 482379 x 16 KB
= 7.4 GB.

## Discovery (existing functions, reuse decisions)

| Piece | Existing (crew-lean/crew) | Decision |
|---|---|---|
| free-% probe | `mem_free_pct` :987 | reuse as is |
| admission | `admission_problems` :1028, `admit` :1059 | extend: one swap rule next to the free-% rule |
| failure message | `cmd_testenv` :2361 emits `testenv_failed` with `str(e)` and `mark_testenv_failed` :2356 | reuse as is (message comes from the problem text) |
| service start | `testenv_up` :2770 (one herdr pane per `[[services]]`, `wait-output --match ready --timeout 240000`) | extend: optional `build` step before `cmd`, optional per-service `ready_timeout` |
| copy teardown | `testenv_down` :2223 (no ask change) vs `stop_copy` :2334 (resolves the HAND TEST ask) | park calls `testenv_down` + keeps `last_slot` + keeps the ask |
| daemon rule pattern | `stale_copy(l)` -> `testenv_stale` event + `refresh_testenv` action (:4912) | copy it for park: `park_due(l, asks, now)` -> `testenv_parked` event + `park_testenv` action |
| bring back | `cmd_testenv up` (admit + `testenv_up` + `publish_testenv`); ask text is deduped by text (`add_ask` :1450), so the owner's forwarded ask survives an up on the same slot + sha | reuse as is |
| prod FE recipe | `scripts/never-stuck-smoke.sh:83-90`: `NEVER_STUCK_API_PROXY=1 NEXT_SKIP_TYPECHECK=1 npx next build` then `npx next start` (rewrites baked at build, `next.config.mjs:61`) | copy the recipe and its reason |

## Architecture

- Layer: crew CLI/daemon (`crew-lean/crew`) + `crew-lean/crew.toml`; no product code changes.
- Build once per head: frontend service gains `build` + `build_stamp`; crew computes a build key = head sha + digest
  of the frontend env file crew just wrote (`.env.local`: `FASTAPI_INTERNAL_URL` is baked into the rewrites at build,
  so a slot move changes the key). Key matches the stamp -> pane runs `cmd` only; else
  `build && write stamp && cmd`. Stamp lives in `.next/` (gitignored, dies with the build).
- Swap gate: `swap_used_gb()` from `sysctl vm.swapusage`; admission refuses above `[admission] max_swap_used_gb`.
- Auto-park: pure `park_due(lane, asks, now)`; daemon emits `testenv_parked`, action takes the copy down without
  resolving its ask, lane gets `parked = {ts, slot, sha}`; `crew testenv up` clears it.

## Behaviour card (filed as crew ask; answers decide the build)

Rules (proposed):
1. Copy frontend = production build (`next build`, then `next start` on the same port, same NODE_OPTIONS header size,
   same tailnet serve). Rebuild only when the head sha or the copy's frontend env changes. Backend runs without
   `--reload`.
2. A new copy is refused when swap used >= 8 GB (half of RAM), on top of the existing free-% rule. Message, e.g.
   "refused testenv: swap used 14.1 GB (>= 8 GB, vm.swapusage); park or stop a copy first".
3. Park: a copy goes down when its HAND TEST ask has been the owner's for > 2 h AND the copy has been up > 2 h AND
   (if Q3 = b) nothing requested it for 2 h. The ask stays open; the board shows "parked"; `crew testenv up LANE`
   brings it back (cold start = build time). A crew-owned ask (pass pending) is never parked.

Real examples (crew state 12 Nov ~19:00):
- OI-WHOLE-SO-CANCEL: copy up 2.3 h, ask forwarded to owner 0.1 h ago -> not parked (owner's for < 2 h).
- SAMPLE-REQUEST-V2: up 0.7 h, ask crew's -> never parked (pass pending).
- Same lane, owner forwarded 3 h ago, copy up 3.5 h, owner never opened it -> parked; ask stays.
- Owner brings it back at 4 h -> `testenv up` on the same slot + sha: no rebuild, same ask (deduped), new 2 h grace.
- Head moves while parked -> next up rebuilds (new key), new ask on the new build (existing refresh rule).

Edge cases: build fails (no stamp written, copy fails like any service, `testenv_failed`); two builds at once (both
pass admission seconds apart; no lock unless the trial shows the peak hurts); `.next` removed by worktree-gc (stamp
gone -> rebuild); worker edits uncommitted files on a local lane (not in the build; same as today's sha rule).

## Crew rulings (12 Nov)

- Q1 (b): refuse a test copy when swap used >= `[admission] max_swap_used_gb = 8`; free-% rule kept; unknown swap =
  no refusal; message names swap used and the cap. Applies to `testenv` only (local spawns keep today's rules: the
  brief scopes the gate to copies).
- Q2: crew-owned HAND TEST ask = never park; park only when the ask is the owner's for > 2 h (`ask.fwd`) AND copy up > 2 h.
- Q3 (b): also stay up while the copy's backend pane shows new output (request lines), read each daemon tick.
- Q4 (a): board shows the parked copy and `crew testenv up LANE`; no POST surface.
- Q5: one trial on slot 12 only after crew's GO (one live copy down or swap < 10 GB), stop within 30 min, never --force.

## Interface (what the tests pin)

- `parse_swapusage(text) -> float|None` (used GiB from `sysctl vm.swapusage`), `swap_used_gb()`.
- Service keys: `build` (cmd), `build_stamp` (path in the service dir), `build_inputs` (files in the service dir whose
  content is part of the key), `ready_timeout` (seconds, default 240).
- `build_key(sha, svc, svc_dir) -> str`, `build_step(svc, svc_dir, key) -> str` ("" when the stamp holds the key, else
  `rm -f STAMP && BUILD && printf %s KEY > STAMP && `), prefixed to the service cmd in `testenv_up`.
- `park_due(lane, asks, now) -> str|None`, `note_copy_activity(lane, tail, now)`, `park_copy(lane_id)`;
  `[admission] park_idle_minutes = 120` (0 = off); lane field `parked = {ts, slot, sha, url}`, cleared by `up`/`down`.

## Review round 1 (12 Nov) and decisions

Accepted: park re-checks under the lane's testenv lock before tearing down (R1); no park in a tick that refreshes the
copy (R2); builds serialized crew-wide with `/usr/bin/lockf` (R3; evidence: CLAUDE.md "Frontend dev loop", parallel
builds took the Mac to load 90-190 twice); board shows parked only with an open HAND TEST ask, kill clears it (R4);
failed build fails fast via a sentinel + `herdr pane wait-output --regex` (R5); park reuses `stop_copy` (R6); missing
tests (R8). Pushed back: dirty-worktree digest in the build key (copies serve the PR head by sha; crew restarts on
sha moves only, so uncommitted edits are not what the owner tests).

## Trial (12 Nov 23:46-23:51, slot 1, crew GO; replaced a freed copy, both runs stopped)

Same head f29ed18eb5, same 10 signed-in pages, `footprint -p` summed over each process tree.

| | backend | frontend at ready | frontend after 10 pages | copy total |
|---|---|---|---|---|
| current (`--reload`, `next dev --turbopack`) | 954 MB (3 procs) | 271 MB | 2575 MB (grows per page) | 3.5 GB |
| lean (no reload, `next build` + `next start`) | 906 MB (1 proc) | 1016 MB | 979 MB (flat) | 1.9 GB |

Start: current ready 15 s, first page 5 s; lean cold = build 165 s + start 2 s, same head again 2 s, pages under 1 s.
Build peak 6.6 GB footprint, swap 6.8 -> 9.7 GB while it ran. Worktree clean after the build. `.next` 4.8 GB, of which
`.next/cache/webpack` 4.2 GB (a dev `.next` is ~186 MB). Proposal filed with crew: cap 6, drop `.next/cache` after build.

## UAC

1. Copy frontend is `next start` serving a build of the copy's head; a second `testenv up` on the same head and env
   does not rebuild (pane shows no `next build`).
2. Head change or slot move -> rebuild before start.
3. Backend copy cmd has no `--reload`.
4. Admission refuses a testenv/local spawn with swap used >= `max_swap_used_gb`; `testenv_failed` names swap used
   and the cap. Free-% rule unchanged.
5. Park per rule 3; ask kept; lane shows parked; `testenv up` brings it back and clears parked.
6. Never park a copy whose ask is crew's, or the owner's for < 2 h.
7. RAM before/after measured on one trial copy; new cap proposed from the numbers.

## Tests (crew-lean/tests/test_crew.py, red first)

Swap gate (above/below cap, unknown swap = no refusal, message text); build key + stamp (match -> no build, sha
change -> build, env change -> build, missing stamp -> build, stamp written only after build succeeds); park rules
(crew ask, owner < 2 h, owner > 2 h + up > 2 h, up < 2 h after bring-back, Q3 traffic); park keeps the ask; up clears
parked.

## Standing rules that apply

Owner standing rules are product UI rules; none apply to a crew tool change except "Reuse functions, not only
components" (Discovery table) and "Every background or scheduled job ... last run" (n/a: park runs in the existing
daemon tick, reported as an event).
