# Browser verification (agent-browser)

Extracted from `CLAUDE.md` on 2026-08-23 so the reference doc stays short. This is the full
policy; `CLAUDE.md` keeps only the rule and the command table.

Frontend changes are not done until verified in a real browser. Type-check + Vitest = code correctness, not feature correctness. UI/flow changes MUST be exercised end-to-end before reporting complete.

**Use `agent-browser` (headless). Playwright MCP is retired for verification - do not use the `mcp__plugin_playwright_playwright__*` tools.** The committed specs under `e2e/` are unchanged and still run, but no NEW one is added - see "Persisted Playwright spec" below.

Two paths, pick one:

## 1. Interactive verification via agent-browser (preferred during a task)

`npx -y agent-browser@0.27.0 <command>` drives a headless Chromium-family browser against the running
dev server. It picks whatever it finds installed (Chrome, Brave, ...), so do not assume a specific
one. Headless is the default; `--headed` opts into a visible window. The browser persists between
invocations via a daemon, so each command is a separate shell call and `&&` chaining works:

```bash
npx -y agent-browser@0.27.0 open http://localhost:3000 && npx -y agent-browser@0.27.0 snapshot -i
```

**Read `agent-browser skills get core --full` before driving it.** That is the version-matched command
reference and workflow guide; it is the source of truth, not this section. What follows is only the
repo-specific policy plus the handful of commands that map onto our old MCP flow.

| Need | Command |
| --- | --- |
| Navigate | `open <url>` |
| See the page (accessibility tree with `@ref`s) | `snapshot`, or `snapshot -i` for interactive elements only |
| Click | `click <sel>` or `click @e2` (ref from the snapshot) |
| Find by role/text | `find role button click --name Submit` |
| Enter text | `fill <sel> <text>` (clear + fill), `type <sel> <text>` |
| Console output | `console` |
| Uncaught page errors | `errors` |
| Network calls | `network requests [--filter <pattern>]` |
| Screenshot | `screenshot [path]`, `--full`, `--annotate` for a labelled shot |
| Responsive check | `set viewport 375 812` / `set viewport 1280 800` |
| Finish | `close` |

Policy, unchanged from the MCP era:

- Ensure the FE dev server runs at `http://localhost:3000` (`npm run dev` in `sorento_crm_frontend/`, HMR) and BE at `http://localhost:8000`. For a final pre-handoff verification, do it against a prod build (`npm run build && npm start`) - see "Frontend dev loop".
- **Login for browser verification reads `E2E_EMAIL` / `E2E_PASSWORD` from `sorento_crm_frontend/.env.local` (gitignored).** The per-spec `*_E2E_EMAIL` / `*_E2E_PASSWORD` names used by the older `e2e/` specs (`REQUEST_BATCH_E2E_*`, `STOCK_E2E_*`, ...) are legacy aliases of the same pair. Names and path only ever appear in commits / status lines - never the values.
- **Always navigate to a feature by clicking through the sidebar / top nav from the home page - never `open` a deep URL directly.** Direct URL navigation hides nav-config bugs (missing entries, wrong `moduleKey`, broken permission gating, hidden behind a collapsed group). The first verification step for any new page is "open the sidebar group it belongs to and confirm the entry renders, then click it."
- Command flow: `open http://localhost:3000`, `snapshot -i` to find the relevant sidebar group button, `click @ref` to expand, `click @ref` the leaf entry, `snapshot` the destination, then `click` / `fill` / `select` and re-snapshot to assert state.
- Always check `console` (and `errors`) after the interaction. Treat unexpected error / warning output as a regression.
- Use `screenshot` for visual confirmation of CRUD flows (list → modal create → row appears → row edit → confirm-delete dialog → row gone).
- Use `network requests --filter /api/v1/` to verify the FE hit the expected endpoint with the right method/payload - confirms the hook → service → api-client chain wired correctly.
- Test the golden path AND edge cases: empty states (every section per CRUD UX standard), validation errors, delete confirmation copy, RBAC denial.
- `close` when done. Never `close --all` - it closes every session, including other agents' browsers on the same machine.

**The daemon's browser is SHARED across every agent on this machine, and it is one tab list.**
Another agent's `open` navigates the page out from under you, and nothing warns you: your next
`snapshot` / `console` / `network requests` silently describes *their* app. This is the worst
failure mode available here, because it looks like a bug in your feature rather than a mix-up -
you read a missing sidebar entry or a stack of console errors off a screen that was never yours.
Proven the hard way: an `open https://example.com` came back fine, and minutes later `get url`
reported `http://localhost:3090/signin`, another lane's dev server, in the only tab.

- `--session-name` does NOT isolate you. It is cookie/storage persistence, not a separate browser.
- `--session <name>` (env `AGENT_BROWSER_SESSION`) DOES isolate you: a separate browser that another lane's `open` cannot navigate. Use it whenever another agent is driving the daemon (26 Aug: four consecutive reads on the default session were hijacked by the :3080 lane). Close only that session by name when done.
- **`get url` before you trust any read.** Confirm you are on the page you think you are on, at the
  start of a verification run and again after any gap between commands.
- `tab new` gives you your own tab, which helps, but tab focus is still global - re-check with
  `get url` rather than assuming the tab you made is the tab you are on.
- Verifying at a non-default port (`PORT=3090 npm run dev`) makes a stray page obvious on sight.

If unable to reach a browser (server down, sandboxed, daemon unresponsive), state that explicitly. Never claim a UI change works without browser verification.

## 2. Persisted Playwright spec (when the flow deserves regression coverage)

- **Do NOT add a new spec.** A standing order is that no project carries a playwright trace, and a new spec is a new trace. The ~40 pre-existing specs, `playwright.config.ts` and the dependency are untouched and still run; what replaces them repo-wide is an open decision. A flow that would have earned a spec is covered instead by a reproducible **agent-browser evidence run** (the exact steps, the network calls and the outcome written into the plan and the commit, so it can be re-walked), and the missing regression guard is logged in `documentation/backlogs/backlog.md`. The trade is spelled out in `documentation/plans/dealer-kit/PLAN-flyer-read-hardening.md` ("The e2e spec, and why it is not here").
- Specs live in `sorento_crm_frontend/e2e/`, config in `sorento_crm_frontend/playwright.config.ts` (chromium only, `baseURL` from `PORTAL_E2E_BASE_URL` ?? `http://localhost:3000`, viewport 1400x1600, single worker, no retries).
- Run all: `npm run test:e2e`. Run one: `npx playwright test e2e/foo.spec.ts`. Headed debug: `npx playwright test --headed --project=chromium`.
- Fixtures in `e2e/fixtures/` are real committed sample files (per memory rule: AI/file features test against real fixtures, not stubbed mocks). Add new fixtures alongside, do not gitignore them.
- Trace retained on failure (`trace: 'retain-on-failure'`); inspect via `npx playwright show-trace`.

## When to use which

- New CRUD page / modal / detail page → agent-browser interactive verification minimum.
- AI / file-extraction / portal flows → a recorded agent-browser evidence run, against a real fixture, is what a spec would have been. No new spec (see above).
- Pure visual / Tailwind tweak → an agent-browser `screenshot` is sufficient.


## End states over frames (added 2026-08-31, lesson 89)

Any interaction check (dialog, sheet, collapse, drawer, drag) is verified as a full round-trip -
open then close then open again, collapse then expand then collapse - and the assertion is the
MEASURED final state (element rects, computed transform/overflow, no overlap with the content
pane), not a mid-animation screenshot. Animated UIs park stale content in exit phases; a pass
recorded mid-flight has repeatedly hidden broken end states.
