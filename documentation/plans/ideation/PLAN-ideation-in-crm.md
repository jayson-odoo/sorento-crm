# PLAN: Ideation inside the Sorento CRM portal (one system, one domain)

Status: Scouted, options written, waiting on the owner's choice (lane IDEATION-IN-CRM, 2 Oct 2026).
No product code until the owner picks an option. The track is set by the option chosen: A or C is
the full pipeline (it touches auth/session and adds a public ingest page); B is ops plus ss work.

Repos read: `jayson-odoo/sorento-crm` (this repo, "CRM") and `jayson-odoo/foundryx-shared-service`
("ss", read-only clone at main, 2 Oct 2026). Paths below prefixed `ss:` are in the ss repo;
`FE` = `sorento_crm_frontend/`, `BE` = `sorento_crm_backend/`; `ssFE` = `service_frontend/`,
`ssBE` = `service_backend/`.

## 1. Journey and goal

Owner (2 Oct): customers and staff should use ONE system. Today ideation lives in ss and Sorento
hands out ss links.

- J1. A Sorento staff member opens Ideas from the CRM sidebar, browses, hides columns, captures an
  idea, opens one, votes or changes its status, and it looks and behaves like the rest of the CRM.
- J2. A customer who submitted an idea over WhatsApp taps "Track it here" and lands on a page on the
  Sorento CRM domain, never the ss domain.
- J3. A deep link `/ideas/<id>` pasted into chat opens that idea inside the CRM.

## 2. Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | Ideation is reached inside the CRM portal (sidebar entry, CRM shell, CRM auth). | Lane brief |
| R2 | Every public or shared ideation link uses the Sorento CRM domain, never the ss domain. | Lane brief |
| R3 | Deep links `/ideas` and `/ideas/<id>` open the right view and survive refresh, new tab and ctrl-click. | Lane brief |
| R4 | Hiding columns and resizing column widths in the Ideas list is saved and survives refresh. | Owner feedback (1) |
| R5 | A staff member can capture an idea manually from inside the CRM. | Owner feedback (2) |
| R6 | Ideas follow the CRM theme (light/dark and the CRM tokens), live when the user toggles. | Owner feedback (3) |
| R7 | Ideas show dates in the CRM format (`dd/MM/yyyy`, date-time `dd/MM/yyyy, h:mm AM/PM`). | Owner feedback (4) |
| R8 | Archive and Delete work from the CRM (found while scouting R4, same root cause). | Scout |

## 3. What exists today (measured, not assumed)

### 3.1 CRM side

- Menu entry `Ideas` -> `/ideas`, gated by `ideation.board.view` (`FE/config/menu.config.tsx:71-76`,
  `FE/app/(protected)/ideas/layout.tsx:7`).
- `/ideas` and `/ideas/[id]` render `IdeationEmbed` (`FE/app/(protected)/ideas/page.tsx:10-17`,
  `FE/app/(protected)/ideas/[id]/page.tsx:13-30`). The iframe src is
  `${iframe_url}#token=${token}` (`FE/components/ideas/IdeationEmbed.tsx:93`), sandbox
  `allow-scripts allow-same-origin allow-forms allow-popups` (`:102`).
- The CRM already listens for `ideation-embed:token-refresh-request` with an origin check and posts
  `ideation-embed:token` back (`IdeationEmbed.tsx:40-62`). These are the only two messages; no theme,
  date, locale or navigation is passed.
- Session mint: `POST /api/v1/integrations/ideation/embed-session`
  (`BE/app/api/v1/integrations/ideation_embed.py:34-61`). It signs a 120 s HS256 assertion
  (`aud=ideation-embed`, `iss=sorento`, `sub`, `email`, `name`, `connection_id`) with the
  per-workspace signing secret and exchanges it at ss `POST /embed/session`
  (`BE/app/services/ideation_embed_service.py:190-278`). `iframe_url = fe_base + "/embed/ideas[/id]"`
  (`:273`).
- Config lives on the default `RespondWorkspace` row with `.env` fallback
  (`BE/app/models/respond_workspace.py:38-53`, `BE/app/config.py:293-302`):
  `ideation_shared_service_url`, `ideation_intake_api_key`, `ideation_embed_signing_secret`,
  `ideation_embed_connection_id`, `ideation_embed_fe_base_url`, `ideation_product_id`.
- The CRM already talks to ss server-side for JSON (httpx): products
  (`BE/app/api/v1/system/respond_workspaces.py:46-112`), create-idea
  (`BE/app/services/ideation_turn_service.py:660-669`), status-events
  (`BE/app/services/ideation_status_update_service.py:70-76`).
- **The CRM never builds an ss link; it relays the one ss returns.** The chatbot reply uses
  `result.get("link")` from create-idea (`ideation_turn_service.py:189`) and the composer rejects any
  other URL (`:302-312`). The status-update WhatsApp appends `Track it here: {track_url}`
  (`ideation_status_update_service.py:197-200`).
- Proxying: `FE/next.config.mjs:50-69` rewrites `/api/v1` only in dev. Production is nginx in the FE
  container (`FE/nginx.conf`: `X-Frame-Options SAMEORIGIN` `:17`, `/api/v1/` -> backend `:40-61`,
  `/` -> Next `:85-95`). There is no `middleware.ts` and no CSP. The public host nginx (blue/green)
  is outside this repo (`.github/workflows/deploy.yml:1604-1656`).
- CRM conventions an ideation page would get for free: theme = next-themes, `attribute="class"`,
  `storageKey="nextjs-theme"` (`FE/providers/theme-provider.tsx:10-17`), tokens in
  `FE/css/config.reui.css` (`:root` `:4`, `.dark` `:126`). Dates = `formatDate` `dd/MM/yyyy` and
  `formatDateTime` `dd/MM/yyyy, h:mm AM/PM` (`FE/lib/helpers.ts:128-134`, `:465`). Column prefs =
  `user_list_column_configs` via `/api/v1/list-query/column-config/{listing_key}`
  (`BE/app/api/v1/list_query.py:252-324`, `FE/components/ui/data-grid.tsx:403-417`). Public pages
  already exist under `FE/app/(public)/` (the portal `c/`).

### 3.2 ss side

- Next.js 15 App Router, no `basePath`/`assetPrefix` (`ss:ssFE/next.config.mjs:1-14`). Embed pages
  `ssFE/app/embed/ideas/page.tsx` and `[id]/page.tsx`, mode detected by path
  (`ssFE/.../embed-app.tsx:18-43`). Public track page `ssFE/app/(public)/public/ideas/[token]`.
- Embed auth is cookie-less: the 5-minute embed token (`typ="embed"`, signed with ss `JWT_SECRET`,
  claims `tenant_id, connection_id, product_id, idea_id, email, name, scope`) is held in memory only
  (`ss:ssFE/lib/embed-auth-store.ts:27-56`) and sent as a Bearer header
  (`ss:ssBE/modules/ideation/services/embed.py:228-313`, `routers/embed.py:164-181`).
- **ss's own staff-auth dependency refuses every embed token**:
  `if payload.get("typ") == "embed": raise _CREDENTIALS_EXC` (`ss:ssBE/app/dependencies.py:65-66`).
  Any ss endpoint behind `get_current_user` is therefore unusable from the iframe.
- Public links are minted by the ss backend only:
  `f"{settings.frontend_url.rstrip('/')}/public/ideas/{idea.status_token}"`
  (`ss:ssBE/modules/ideation/services/sinks.py:45-60`), used for intake replies and the
  status-event `track_url` (`services/intake.py:664,713,725`, `services/status_events.py:112,136`).
  `frontend_url` is ONE global setting per ss deployment (`ss:ssBE/app/config.py:121`), not per tenant.
- Frame headers: `ss:ssFE/middleware.ts:18-20` sets `frame-ancestors` only for omnichannel and
  webchat; `/embed/ideas` has no CSP and no `X-Frame-Options`, so any origin can frame it. The stored
  `EmbedConnection.allowed_origins` (`ss:ssBE/modules/ideation/models.py:300-303`) is never enforced.
- The child's token listener accepts `ideation-embed:token` with no `event.origin`/`event.source`
  check (`ss:ssFE/lib/embed-token-refresh.ts:34-40`). The TODO in `ss:ssFE/lib/api-client.ts:64-69`
  saying the Sorento listener is unshipped is stale: it shipped in `IdeationEmbed.tsx:40-62`.

## 4. Root cause of each owner complaint

### R4: column hide/width not saved

**Not third-party storage.** ss stores list prefs on its backend, not in localStorage or cookies:
`useViewPreferences` loads/saves through `GET/PATCH /me/preferences/{viewKey}`
(`ss:ssFE/hooks/use-view-preferences.ts:43,58-70`, `ss:ssFE/services/preferences-service.ts:18,25`),
table `user_view_preferences` (`ss:ssBE/app/models/view_preference.py:16-28`). In embed mode the
view key is `ideation.ideas.embed` (`ss:ssFE/app/(protected)/ideation/ideas/use-ideas-list-config.tsx:305`)
and the request carries the embed token, which `get_current_user` rejects with 401
(`ss:ssBE/app/dependencies.py:65-66`). `preferencesService.save` swallows the error
(`preferences-service.ts:24-32`); the source even says "its best-effort save 401s harmlessly"
(`use-ideas-list-config.tsx:304`). Every load starts from defaults.

Consequence for the options: a same-origin reverse proxy does **not** fix this by itself; the save
would still 401. The fix is either an embed-principal prefs endpoint in ss, or CRM-owned prefs.

### R5: cannot capture an idea manually

The "Capture idea" button is not hidden in embed mode (`use-ideas-list-config.tsx:314-315`,
`ss:ssFE/components/platform/resource-list/resource-list.tsx:441-448`), and the dialog is a normal
Radix portal, so the iframe is not the problem. The blocker is product scope:

- The dialog cannot submit without a product (`ss:ssFE/app/(protected)/ideation/ideas/idea-capture-dialog.tsx:45`).
- In embed mode the product list is synthesised (`ss:ssFE/services/ideation-embed-service.ts:63-89`):
  a product-scoped connection gives one product; an **unscoped** connection derives products from
  existing ideas (empty list, so Submit stays disabled, if there are none).
- Even with a product picked, ss rejects create on an unscoped connection:
  403 `embed_scope_required` "This embed connection is not scoped to a product; create is
  unavailable." (`ss:ssBE/modules/ideation/routers/embed.py:304-309`).

So capture works only if Sorento's `EmbedConnection` row has a `product_id`. Which state production
is in is DB data I cannot read from here; the symptom fits "unscoped". The CRM already knows the
right product (`ideation_product_id` on the workspace, `respond_workspace.py:38-53`), which the
WhatsApp intake path uses.

Second, smaller defect found on the way: attachments dropped into the capture dialog are silently
discarded in both modes (`ideation-embed-service.ts:108-118`, `ss:ssFE/services/ideation-service.real.ts:88-101`).

### R6: theme not aligned

ss uses its own tokens (`ss:ssFE/css/foundryx-tokens.css`), plus a tenant stylesheet chosen by the
**ss Host header** (`ss:ssFE/app/layout.tsx:61,73-75`, `lib/branding-ssr.ts:31-51`), and next-themes
with localStorage key `nextjs-theme` (`ss:ssFE/providers/theme-provider.tsx:13-20`). In a cross-site
iframe that localStorage is partitioned from the CRM's, so the iframe follows the OS theme, not the
CRM toggle. Nothing is passed from the host. The ideation embed has no theme message; the
omnichannel embed in the same repo does (`init/theme {theme, colorScheme}`, origin-checked,
`ss:ssFE/components/platform/omnichannel-embed/embed-protocol.ts:15-60`,
`use-embed-session.ts:60-66,152-168`), so "can the host pass theme dynamically?" is **yes, with a
copyable precedent**.

### R7: date format not aligned

ss formats with `Intl.DateTimeFormat('en-GB', {day:'2-digit', month:'short', year:'numeric'})`,
giving `02 Oct 2026` (`ss:ssFE/lib/datetime.ts:36-47,59-66`), used by the list
(`use-ideas-list-config.tsx:255,297`) and detail (`components/idea-form-fields.tsx:230`). Timezone is
`session.user.timezone` or the browser zone (`ss:ssFE/hooks/use-datetime.ts:27-37`); the iframe has
no session. The CRM standard is `dd/MM/yyyy` (`FE/lib/helpers.ts:128-134`). Two formatters, two
answers.

### R8: Archive and Delete

They are deferred actions that call `POST /api/v1/pending-actions`
(`ss:ssFE/services/pending-actions-service.real.ts:10`), which needs `get_current_user`
(`ss:ssBE/app/api/v1/pending_actions.py:54`) and so 401s on the embed token, same root cause as R4.
Inferred from code, not run.

### R3: deep links

`/ideas/<id>` maps to `/embed/ideas/<id>` on first load only. Navigation inside the iframe is never
reflected in the CRM URL, and ctrl/cmd-click on a row opens `window.open(href,'_blank')`
(`ss:ssFE/components/ui/data-grid-table.tsx:675`): an ss URL with no token and no parent, which
shows "Session expired".

### R2: public links

ss mints `track_url` and the intake `link` from its single global `frontend_url`, so every link
the CRM relays is on the ss domain. No CRM-side page exists for it.

## 5. Options

All three keep ss as the system of record for ideas (ss staff keep their operator UI for BR
promotion and triage). They differ in where the Sorento-facing UI is rendered.

### Option A: keep the iframe on the ss domain, add a host bridge

Fix each complaint inside ss and teach the CRM host to drive it.

| Req | How | Repo |
|---|---|---|
| R4 | New `GET/PATCH /embed/preferences/{viewKey}` behind `require_embed_principal`, keyed `embed-user:{sub}` + connection (reuse `user_view_preferences` with a nullable `user_id` plus a `principal_key` column, or a small sibling table). Point `preferencesService` at it in embed mode. | ss |
| R5 | Set `product_id` on Sorento's `EmbedConnection` (config, zero code) or let the assertion carry `product_id` from the CRM's `ideation_product_id`. Send attachments on create. | ss (+ CRM 2 lines if via assertion) |
| R6 | Add `ideation-embed:theme {colorScheme, tokens}` to the ideation embed, copied from the omnichannel protocol; CRM posts it on load and on every next-themes change. Map the CRM token values onto ss variable names. | both |
| R7 | Add `ideation-embed:locale {dateFormat, timeZone}`; ss `useDatetime` honours it in embed mode. Or hard-set embed mode to `dd/MM/yyyy`. | both |
| R8 | Embed-principal variant of pending actions, or direct `DELETE /embed/ideas/{id}` with the server-deferred window. | ss |
| R3 | `ideation-embed:navigate {path}` child to parent so the CRM URL follows; ctrl-click posts a "open in new tab" message and the CRM opens `/ideas/<id>`. | both |
| R2 | ss gets a per-tenant (or per-connection) `public_link_base_url`; Sorento's points at `https://<crm>/public/ideas`. The CRM serves `FE/app/(public)/public/ideas/[token]/page.tsx`, which calls a new CRM BE route that proxies ss `GET /public/ideas/{token}` (the CRM already proxies ss JSON with httpx). | both |
| Security | `frame-ancestors` from `allowed_origins` on `/embed/ideas`; origin check in `embed-token-refresh.ts`. | ss |

Fixes for free: nothing. Every item is a deliberate change, about half of them cross-repo.
Leaves: two token sets and two formatters that will drift again; a postMessage protocol to version
across two deploys; the ss UI still renders inside a CRM page (inner scrollbars, its own toolbar
style).
Effort: M. Roughly 60% ss, 40% CRM.

### Option B: same-origin reverse proxy (`<crm>/ideation/*` -> ss)

Serve ss under the CRM host so the iframe (or a full page) is same-origin.

| Req | How | Repo |
|---|---|---|
| R1/R2 | CRM nginx `location /ideation/ { proxy_pass <ss-fe>; }` before `location /`, plus the public host nginx (not in this repo). ss needs `basePath: '/ideation'` and its own build, because `basePath` and `NEXT_PUBLIC_BACKEND_API_URL` are baked at build time (`ss:ssFE/next.config.mjs`, `lib/api-client.ts:13-14`) and paths like `'/embed/ideas'` are hard-coded (`embed-app.tsx:23-25`). A dedicated ss frontend container for Sorento. ss `frontend_url` must become per-tenant, or the Sorento container gets its own backend config. | both + ops |
| R4 | **Not fixed for free.** Prefs are server-side and 401 (section 4). Same ss endpoint as A. | ss |
| R5 | Same as A (connection scope). | ss |
| R6 | Partly free: same origin means ss next-themes reads the CRM's `nextjs-theme` localStorage key (both use that key) and the `storage` event syncs a toggle live. Colours still differ (`foundryx-tokens.css` vs `config.reui.css`), and ss tenant branding resolves from the Host header (`ss:ssFE/lib/tenant.ts:75-88`), which is now the CRM host, so a wrong or default tenant brand. | ss |
| R7 | Not fixed. Same as A. | ss |
| R3 | Better: a same-origin parent can read `iframe.contentWindow.location` and mirror it. Ctrl-click still opens an ss page with no token. | CRM |
| R8 | Same as A. | ss |

New risks: both apps run NextAuth v4 with the default cookie name `__Secure-next-auth.session-token`
on path `/` of the same host. ss's root layout mounts a SessionProvider, so ss code would read (and
on sign-out clear) the CRM's session cookie, signed with a different secret. Needs a cookie-name
override in ss before it is safe. Two Next apps on one host also share `/_next/` unless basePath is
set everywhere.
Fixes for free: dark/light mode only, and same-origin storage (which is not what breaks R4).
Effort: M-L, much of it ops (second ss build per host, nginx in two places), and the least
reusable.

### Option C: CRM-native Ideas pages over the ss embed API (CRM backend as the gateway)

The CRM renders Ideas with its own components; the CRM backend calls ss's existing embed API
server-side, so no iframe and no ss domain reaches the browser.

| Req | How | Repo |
|---|---|---|
| R1 | `FE/app/(protected)/ideas/page.tsx` becomes a CRM DataGrid list, `[id]/page.tsx` a CRM detail page (View = Edit layout, `RecordNavigation`), capture as a CRM modal. Layering per PRINCIPLES: UI -> `useIdeasQuery`/mutations -> `services/ideationService.ts` -> `lib/api-client` -> BE. | CRM |
| Gateway | New BE router `/api/v1/ideation/*` (permission `ideation.board.view`, write actions under a new `ideation.ideas.manage` if the owner wants to split). Each call mints a short assertion for the calling user exactly as today (`ideation_embed_service.py:190-209`), exchanges it once for an embed token, caches it per user for its 5-minute life, and forwards to ss `/embed/ideas`, `/embed/ideas/{id}`, `/vote`, `/status`, `/attachments`, `POST /embed/ideas`. Those ss routes already exist with "full parity" and per-id scope checks (`ss:ssBE/modules/ideation/routers/embed.py:198-215`). | CRM |
| R4 | **Free.** The CRM DataGrid persists to `user_list_column_configs` (`list_query.py:252-324`) with listing key `ideation.board.view`. | none |
| R5 | Capture modal posts through the gateway. The CRM sends no product (ss forces the connection's), so the one prerequisite is the connection's `product_id` (config). Attachments: CRM uploads after create via `POST /embed/ideas/{id}/attachments`, which works today. | config |
| R6 | **Free.** CRM components, CRM tokens, CRM next-themes. | none |
| R7 | **Free.** `formatDate`/`formatDateTime` from `FE/lib/helpers.ts`. ss returns ISO timestamps. | none |
| R8 | **Free.** CRM deferred-action delete pattern calling the gateway, which calls ss `DELETE /embed/ideas/{id}` (exists). | none |
| R3 | **Free.** Real CRM routes; ctrl-click, refresh and share all work. | none |
| R2 | Same public-link change as A: ss per-tenant `public_link_base_url` (small ss change) plus a CRM public page `FE/app/(public)/public/ideas/[token]` over a CRM BE proxy of ss `GET /public/ideas/{token}` (keep ss's `no-store`, `noindex`, `no-referrer` headers, `ss:ssBE/modules/ideation/routers/public_ideas.py:45-51`). Stop-gap if ss cannot ship first: the CRM rewrites `link`/`track_url` it relays by swapping the ss origin for its own (it already parses both, `ideation_turn_service.py:189`, `ideation_status_update_service.py:197`). | both |
| Security | The embed token never reaches the browser. The iframe, the fragment token and the postMessage handshake are deleted from the CRM. ss's frame-header and origin-check gaps stop mattering to Sorento (still worth fixing in ss for other tenants). | CRM |

Cost: a second UI for ideas exists (ss operator UI stays for ss staff). Scope decides size: list +
detail + capture + vote + status + archive/delete + attachments is the baseline; board (kanban
reorder), merge/unmerge and promote-to-BR are optional extra slices (all have embed routes:
`PUT /embed/ideas/reorder`, `POST /embed/ideas/merge`, `/unmerge`, `/promote`).
Fixes for free: R3, R4, R6, R7, R8. R5 needs one config value. R2 needs the same small ss change as A.
Effort: L for the baseline (ss changes are only the public-link base). Repo precedent: ADR 0005
already rejected embedding ss by iframe for the page builder, citing this embed's cost
(`documentation/adr/0005-page-builder-built-here-not-the-shared-service-template-engine.md:22-27`).

### Scorecard

| Req | A: iframe + bridge | B: same-origin proxy | C: CRM-native |
|---|---|---|---|
| R1 in portal | yes (iframe) | yes (iframe or page) | yes (native) |
| R2 CRM-domain links | ss + CRM change | ss + CRM + ops | ss + CRM change |
| R3 deep links | protocol work | partial | free |
| R4 column prefs | ss endpoint | ss endpoint (NOT free) | free |
| R5 manual capture | config | config | config |
| R6 theme | protocol + token map | dark mode free, colours not | free |
| R7 dates | protocol | ss change | free |
| R8 archive/delete | ss change | ss change | free |
| New risk | protocol drift | cookie collision, per-host ss build | duplicate UI to keep in step |

## 6. Recommendation

**Option C**, built in this order:

1. **Now, no code, any option:** set `product_id` on Sorento's ss `EmbedConnection` to the same
   product as the CRM workspace's `ideation_product_id`. This unblocks manual capture (R5) in the
   current iframe today, before anything else ships.
2. **Slice 1 (CRM):** gateway router + native list + detail + capture modal + vote/status +
   archive/delete + attachments; delete `IdeationEmbed` and `useIdeationEmbedSession`.
3. **Slice 2 (ss, small):** per-tenant `public_link_base_url` used by `mint_idea_link`.
   **Slice 3 (CRM):** public track page `/public/ideas/[token]` + BE proxy. Until slice 2 lands, the
   CRM rewrites the origin of relayed links (stop-gap).
4. Board / merge / promote only if the owner wants them in the CRM (question 2).

Why: the owner's goal is one system. All four complaints (and archive/delete and deep links) are the
same problem, two apps with two theme systems, two date formatters and two auth models stitched
together by an iframe. A patches each symptom across two repos and two deploys and leaves them free
to drift; B costs ops work and a cookie risk and, measured against the code, fixes only dark mode
for free (the prefs bug is a backend 401, not browser storage). C deletes the stitching: five of the
eight requirements need no extra work at all, and the ss embed API it calls already exists.

If the owner wants the cheapest step now and C later: do step 1, plus Option A's R4 and R7 items,
and treat C as the follow-up. Most of A's protocol work would be thrown away by C, which is why it
is not the recommendation.

## 7. Open questions for the owner (filed as one crew-ask)

1. Which option: A, B or C? Recommendation C.
2. Scope of the CRM Ideas pages: (a) baseline list/detail/capture/vote/status/archive/attachments, or
   (b) also board (kanban reorder), merge/unmerge and promote-to-BR. Recommendation (a), add (b) only
   for what Sorento staff actually use.
3. Every idea captured from the CRM goes to one product, the workspace's `ideation_product_id`
   (scope the ss embed connection to it)? Recommendation yes; it also fixes manual capture today.
4. Public track link shape `https://<crm domain>/public/ideas/<token>`, and links already sent on the
   ss domain keep working there (no redirect)? Recommendation yes to both.
5. May this lane open the small ss PR (per-tenant public link base) in `foundryx-shared-service`, or
   does ss work go to a separate ss lane? Recommendation a separate ss lane, with the CRM rewrite
   stop-gap until it merges.

## 8. Side findings in ss (report, not in this lane's scope)

- `/embed/ideas` has no `frame-ancestors`; `EmbedConnection.allowed_origins` is stored but never
  enforced (`ss:ssFE/middleware.ts:18-20`, `ss:ssBE/modules/ideation/models.py:300-303`).
- `embed-token-refresh.ts:34-40` accepts a token message from any origin.
- Capture-dialog attachments are silently dropped (section 4, R5).
- Stale TODO in `ss:ssFE/lib/api-client.ts:64-69` (the Sorento listener shipped).
