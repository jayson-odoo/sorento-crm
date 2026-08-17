# User Management — Data reference for admins

Reference for the **User Management** module: who can log in, what they're allowed to do, how SLA work is routed to them, and how WhatsApp contacts are granted access to AI agents. It maps each entity to its backing table, key fields, date columns, status/enum values, filters, and example questions an admin can answer from the list pages or an export.

> **There are NO MCP tools for User Management.** The AI assistant cannot query users, roles, permissions, teams, agents or access types — those endpoints are deliberately **not** wrapped as MCP tools (the MCP catalog covers products, inventory, promotions, complaints, SLA, etc., never identity/RBAC). This page is therefore an **admin reference for power users** working directly from the list pages and their **Export** buttons, not a prompt-able data source. Treat every "example question" below as "filter the list / export and read it off", not "ask the assistant".

> **Reading notes**
> * **Menu labels are deliberately non-obvious — quote them, don't infer the entity.** Three entries do not name their backing table:
>   * **AI Agents** = `access_agents` (`AccessAgent`) — the access-control *agent* an n8n/Respond.io conversation runs as; owns MCP-tool grants and team routing. **Not** an "admin user".
>   * **Internal Users** = `contact_agent_access` (`ContactAgentAccess`) — grants of a WhatsApp **contact** to an **AI Agent**, time-boxed. **Not** the `users` table.
>   * **Administrative Users** = `users` (`User`) — the people who log in to the CRM.
> * **No UUIDs in answers.** Resolve to email / name / role name / team name / agent code / access-type code.
> * **Dates are stored naive UTC** (`DateTime(timezone=False)`); the UI renders Malaysia time. Be explicit about timezone when quoting timestamps.
> * **Backend table name ≠ class name** — every entity below names its real `__tablename__`.

Menu group **User Management** (verbatim):
[Administrative Users](/user-management/users) · [Roles](/user-management/roles) · [Permissions](/user-management/permissions) · [AI Agents](/user-management/access-agents) · [Teams](/user-management/teams) · [Internal Users](/user-management/contact-access-agents) · [Contact Access Types](/user-management/contact-access-types) · [Account](/user-management/account) · [Logs](/user-management/logs) · [Settings](/user-management/settings)

---

## Administrative Users — `users`

Menu: **Administrative Users** (page title *Administrative Users*). The people who authenticate into the CRM. RBAC permissions reach a user through their **roles** (`user_role_assignments` → `user_roles` → `user_role_permissions`). SLA work reaches a user through **team membership** + **tier**.

**Key fields**

| Field | Meaning |
|-------|---------|
| `email` | Login identity (unique). |
| `name` | Display name (list column **User**). |
| `contact_number` | Phone (unique across users; one phone = one user). |
| `status` | Account status — see enum below (list column **Status**). |
| `country`, `timezone` | Profile locale. |
| `superior_id` → user | Reporting line; response also returns `superior_name` (form label **Superior**). |
| `tier` | **Conversation-SLA policy tier** (1, 2, …). Drives which escalation level the user sits at. Form label **Tier**. |
| `respond_user_id`, `respond_synced` | Respond.io agent linkage + sync state (`pending` / synced). |
| `respond_contact_id` → respond_contact | Linked WhatsApp contact (resolves `respond_io_id`); set by an admin or auto-cached from a unique phone match. Form label **WhatsApp Contact**. |
| `daily_sla_summary_subscribed` | Email daily-SLA-summary opt-in (list column **Conversation Summary**). |
| `is_protected` | System-protected user; cannot be deleted/trashed via normal flows. |
| `is_trashed` | Soft-trash flag (this module uses trash + restore, not hard delete — see note). |
| `invited_by_user_id`, `email_verified_at`, `last_sign_in_at` | Invite + sign-in audit. |
| notify toggles (8) | Per-event × per-channel SLA notification gates — see **Notify toggles** section below. |

**Date columns:** `created_at` (list column **Joined**), `updated_at`, `last_sign_in_at` (list column **Last Sign In**), `email_verified_at`.

**Status enum** (`UserStatus`, stored as the string value):
* `ACTIVE` — UI label **Active**.
* `INACTIVE` — UI label **Inactive** (default for a freshly invited user).
* `BLOCKED` — UI label **Blocked**.

**Available filters** (Administrative Users list / `GET /api/v1/user-management/users`):
* free-text **search** (`query`, matches name or email; placeholder *Search users*).
* **Role** (`roleId` — joins `user_role_assignments`; filter value **All roles** or a specific role).
* **Status** (`status` — **Active** / **Inactive** / **Blocked**, or all).
* **Trashed** (`trashed`): **Active only** (`exclude`, default) / **Trashed only** (`only`) / **All** (`all`).
* `respond_synced` (Respond.io sync state).
* `tier` (comma-separated, e.g. `1,2,3`).
* Sortable: `name`, `status`, `created_at`, `last_sign_in_at`.

**Bulk actions** on the list: **Bulk activate**, **Bulk deactivate**, **Bulk send invitation**, **Trash**, **Permanently delete** (only for already-trashed users).

**Example questions**
* "List active users." (`status=ACTIVE`)
* "Who has the *{role}* role?" (filter **Role**)
* "Show users that have never signed in." (sort by **Last Sign In**, find blanks)
* "Which users sit at escalation tier 2 or 3?" (`tier=2,3`)
* "List users with no linked WhatsApp contact." (`respond_contact_id` empty)
* "Who joined this quarter?" (sort by **Joined** / `created_at` range)
* "Show trashed (deactivated) users." (`trashed=only`)
* "Which users report to *{manager}*?" (filter on `superior_name`)
* "Who is subscribed to the daily SLA summary email?" (**Conversation Summary** column)
* "Which users are still `pending` Respond.io sync?" (`respond_synced=pending`)

> **Delete semantics differ from the rest of the product here.** Administrative Users use **Trash → Restore → Permanently delete** (soft `is_trashed`), not the standard hard-delete-with-confirm. "Trash" sets `is_trashed=true`; "Permanently delete" is only offered for rows already in trash. (Audit TODO: this is intentional for accounts but is an exception to the ADR hard-delete rule.)

---

## Notify toggles (on the User) — SLA notification gates

Eight boolean columns on `users` gate **whether a user is reached** for SLA events, per channel. They live on the **Administrative Users** edit dialog (each is a checkbox; verbatim labels below).

| Column | Form label | Default | Fires when… |
|--------|-----------|---------|-------------|
| `notify_email_on_assignment` | **Email on assignment** | on (`true`) | an SLA stage is assigned to the user |
| `notify_email_on_escalation` | **Email on escalation** | on (`true`) | an SLA escalates to the user |
| `notify_whatsapp_on_assignment` | **WhatsApp on assignment** | off | assignment (needs a linked WhatsApp contact) |
| `notify_whatsapp_on_escalation` | **WhatsApp on escalation** | off | escalation (needs a linked WhatsApp contact) |
| `notify_email_on_deadline_extended` | **Email on deadline extended** | on (`true`) | a lower tier extends a deadline and this user is the next escalation tier |
| `notify_whatsapp_on_deadline_extended` | **WhatsApp on deadline extended** | off | deadline-extended (needs a linked WhatsApp contact) |
| `notify_email_on_product_discontinued` | **Email on products discontinued** | off | products newly discontinued (batched) |
| `notify_whatsapp_on_product_discontinued` | **WhatsApp on products discontinued** | off | product-discontinued (needs a linked WhatsApp contact) |

Two related but separate columns also exist: `notify_whatsapp` (legacy, superseded by the per-event toggles) and `notify_whatsapp_summary` (form label **WhatsApp daily SLA summary**), plus `daily_sla_summary_subscribed` (the **email** daily summary).

**How the matrix works** (see [SLA — notification matrix](../sla/sla-policies.md) and [Form-SLA configuration](../sla/form-sla-configuration.md)):
* **Stage-level booleans gate the event**: a stage's `notify_assignee` (assignment) and `notify_on_escalation` (escalation) decide whether the event is emitted at all.
* **Per-user toggles gate the channel**: even when the stage allows the event, email fires only if the user's `notify_email_on_{assignment,escalation}` is on, and WhatsApp only if `notify_whatsapp_on_{assignment,escalation}` is on **and** the user has a linked `respond_contact_id`.
* **In-app always fires** for the assignee when the stage allows the event — the toggles only govern email/WhatsApp.

> **Code-accuracy note for maintainers.** `GET /users/{id}`, `GET /users/me`, and the update response each build a **manual `UserResponse(**user_dict)`** dict — they do **not** rely on `from_attributes` for these columns. A new User column (any future toggle) must be added to **all three** manual dict builders in `app/api/v1/user_management/users.py` or it silently renders its default and never reaches the FE. The eight toggles above are wired in all three today.

---

## Roles — `user_roles`

Menu: **Roles** (page title *Roles*). A named bundle of permissions; users get permissions only via the roles assigned to them.

**Key fields**

| Field | Meaning |
|-------|---------|
| `name` | Role name (unique; list column **Role**, form label **Role Name**). |
| `slug` | Stable machine slug (unique; list column **Slug**, e.g. `users:delete`). |
| `description` | Free text. |
| `is_protected` | System role; guarded against deletion. |
| `is_default` | Role auto-assigned to a new user when no `role_ids` are passed. |
| `permissions` (→ `user_role_permissions`) | The permission slugs granted by this role (list column **Permissions**). |
| `created_by_user_id` | Creator. |

**Date columns:** `created_at`. (No `updated_at` column on roles.)

**Available filters** (Roles list / `GET /api/v1/user-management/roles`): free-text **search** (`query`, placeholder *Search roles*) + pagination. (No status enum — roles are not active/inactive.) Trashed roles are excluded by default (`is_trashed=false`).

**Example questions**
* "Which roles grant the *{permission slug}* permission?" (open the role, read **Permissions**)
* "What is the default role for new users?" (`is_default = true`)
* "List protected (system) roles." (`is_protected = true`)
* "How many permissions does the *{role}* role grant?"
* "Which role owns the `orders:*` permissions?"
* "List all roles and their slugs."

---

## Permissions — `user_permissions`

Menu: **Permissions** (page title *Permissions*). The atomic RBAC capabilities (view/create/edit/delete per resource). Backend route guards check these slugs; the DataGrid column-preference system keys personalization off the **view** permission slug (`listing_key`).

**Key fields**

| Field | Meaning |
|-------|---------|
| `slug` | The capability string checked by the backend (unique; list column **Slug**, e.g. `order_management.orders.view`). |
| `name` | Human label (list column **Permission**). |
| `description` | Free text (list column **Description**). |
| `created_by_user_id` | Creator. |

**Date columns:** `created_at` (list column **Created At**).

**Available filters** (Permissions list / `GET /api/v1/user-management/permissions`): free-text **search** (`query`, placeholder *Search permissions*); the list also offers a **Filter by role** select (show only permissions granted by a chosen role) + pagination.

**Example questions**
* "List every permission slug for the order-management module." (search `order_management`)
* "Which permissions does role *{X}* include?" (**Filter by role**)
* "Is there a `delete` permission for complaints?" (search `complaints` + `delete`)
* "What does the `*.view` permission control?" (read **Description**)
* "How many permissions exist in total?"

---

## Teams — `teams` (+ members `team_members`)

Menu: **Teams** (page title *Teams*). Groups of users used for **round-robin SLA assignment** and a **team hierarchy** (a parent-team member can see/act on all descendant teams). Teams are the routing target that **AI Agents** point at, per **tier**.

**Key fields (`teams`)**

| Field | Meaning |
|-------|---------|
| `name` | Team name (form label **Name**). |
| `description` | Free text (form label **Description (optional)**). |
| `parent_team_id` → team | Hierarchy parent (form label **Parent team (optional)**; **No parent team** = top-level). `SET NULL` on parent delete (children re-root, not cascade-deleted). |
| `member_count`, `members` (preview) | Computed for the list; members shown as name only (no UUID). |

**Key fields (`team_members`)** — the detail page (`/user-management/teams/{id}`, breadcrumb **Members**):

| Field | Meaning |
|-------|---------|
| `user_id` → user | The member (column **User**). |
| `sort_order` | Round-robin order (column **Order**). |
| `include_in_round_robin` | Per-team auto-assign eligibility (column **Auto-assign (round robin)**, a switch). Default `true`. Governs **AUTO** distribution only — a manual takeover/reassign can still target an excluded member, and they still appear in Team Tasks. **Per-team, not per-user**: a multi-team member can be RR-eligible in one team and excluded in another. |

**Date columns:** `created_at` (teams and team_members).

**Available filters** (Teams list): free-text **search** (placeholder *Search teams…*). The list renders as a **tree** reflecting `parent_team_id`.

> **Team tiers and the team-set code do NOT live on `teams`.** A team becomes "tier 1 / 2 / 3 of a team set" only through an **AI Agent's** `agent_teams` row (`code` = team-set code, `tier` = 1/2/3). The same team can be tier 1 in one set and tier 2 in another. So "what tier is this team?" is only answerable in the context of a specific agent — see **AI Agents** below.

**Example questions**
* "Who is on the *{team}* team, and in what round-robin order?" (open team → **Order** column)
* "Which members are excluded from auto-assignment on *{team}*?" (**Auto-assign (round robin)** off)
* "What is the team hierarchy (which teams sit under *{parent}*)?" (tree view / `parent_team_id`)
* "Which teams are top-level (no parent)?"
* "How many members does each team have?" (`member_count`)
* "Is *{user}* a member of more than one team?"

See [SLA — team-tier routing](../sla/form-sla-configuration.md) for how tier + team-set drives assignment (`resolve_team_with_tier_fallback`: pick the first existing team at-or-above the requested tier, so a missing intermediate tier is skipped, not fatal).

---

## AI Agents — `access_agents` (`AccessAgent`)

Menu: **AI Agents** (page title *AI Agents*). **This is NOT an administrative login.** An "AI Agent" is the **access-control agent** that an n8n / Respond.io conversation runs *as*. It owns two things: a set of **MCP tool grants** (`agent_mcp_tools`) and a set of **team-set routing rows** (`agent_teams`). When a WhatsApp conversation is handled, n8n preflights `(contact_id, space_id, agent_code)` and the agent decides which tools are callable and which team/tier the work routes to.

**Key fields (`access_agents`)**

| Field | Meaning |
|-------|---------|
| `code` | Stable kebab/underscore agent code (unique; list column **Code**). The string n8n passes as `agent`. |
| `name` | Display name (list column **Name**, detail page `<h1>`). |
| `description` | Free text (list column **Description**). |
| `is_active` | Active flag (list column **Status**). |
| `assign_to_new_internal_contacts` | When `true`, every newly created internal contact is auto-granted this agent. |
| `synced_to_excel`, `last_synced_to_excel` | Excel-sync bookkeeping. |

**Team Assignments (`agent_teams`)** — detail page card **Team Assignments**:

| Field | Meaning |
|-------|---------|
| `code` | **Team-set code** (e.g. `marketing_product`, `retail_director`). |
| `team_id` → team | The team handling this tier. |
| `tier` | **1** = initial, **2 / 3** = escalation (detail page shows a **Tier {n}** chip for 1–3). |
| `policy_id` → sla_policy | Conversation-SLA policy bound to this team set (one per `(agent, code)`, cast onto every tier row). |
| `notify_on_extension` | Whether this tier's team is notified when a lower-tier deadline is extended (default `true`). |

**Member brand tags (`team_member_brands`)** - on each member row under a Team Assignment, the **Brands** editor lists the brands that member serves (`brand_code`, lower-case, validated against `brands`). Empty = **All brands**. Routing draws from the members tagged with the conversation's brand plus the untagged ones, and falls back to the whole team when nobody carries it - the same rule as the member's market segments. See [Manage teams](manage-teams.md#how-teams-drive-sla-assignment-tiers).

**MCP tool grants** — detail page card **MCP Tools**: many-to-many via `agent_mcp_tools` (agent × tool × optional team × tier). The catalog rows live in `mcp_tools`. Sync from the code catalog never touches ownership — only admins grant/revoke.

**Date columns:** `created_at`, `updated_at` (agent); `created_at` (agent_teams).

**Available filters** (AI Agents list / `GET /api/v1/user-management/access-agents`): free-text **search** (`query`, placeholder *Search access agents...*) + pagination. Sorted by `code`.

**Preflight decisions** (`evaluate_agent`, used by n8n before a run): `allow`, `deny_no_access`, `deny_unknown_agent`, `deny_unknown_contact`. The per-tool guard (`McpAccessCheckOut`) adds `deny_tool_unlinked`, `deny_unknown_tool`. Decisions are logged to `mcp_access_log`.

**Example questions**
* "Which MCP tools is the *{agent}* agent allowed to call?" (open agent → **MCP Tools**)
* "Which agents auto-attach to new internal contacts?" (`assign_to_new_internal_contacts = true`)
* "For agent *{X}*, which team is tier 1 vs tier 2 of team-set *{code}*?" (**Team Assignments**)
* "List inactive agents." (`is_active = false`)
* "What SLA policy is bound to *{agent}* / *{team-set}*?" (`policy_id`)
* "Which agents share the *{tool}* tool?" (the tool picker lists `current_agent_names`)
* "What is the agent code n8n should pass for *{name}*?" (`code`)

---

## Internal Users — `contact_agent_access` (`ContactAgentAccess`)

Menu: **Internal Users** (page title *Internal Users*). **This is NOT the `users` table.** "Internal Users" is the grant table joining a **WhatsApp contact** (`respond_contacts`) to an **AI Agent** (`access_agents`), optionally time-boxed. A grant here is what lets that contact's conversation run as that agent (and thus reach the agent's tools). The list is usually shown **grouped by contact**.

**Key fields**

| Field | Meaning |
|-------|---------|
| `respond_contact_id` → respond_contact | The internal WhatsApp contact (FK; preferred). |
| `respond_contact_phone` | Phone, kept for back-compat (list column **Respond Contact Phone**). |
| `respond_contact_name` | Name, kept for back-compat (list column **Respond Contact Name**). |
| `agent_id` → access_agent | The granted agent. Response adds `agent_code` (**Agent Code**) + `agent_name` (**Agent Name**). |
| `is_allowed` | Allow/deny flag (list column **Allowed**). |
| `valid_from`, `valid_to` | Time window — a grant only counts while `valid_from ≤ now < valid_to` (NULLs = open-ended). List columns **Valid From** / **Valid To**. |
| `synced_to_excel`, `last_synced_to_excel` | Excel-sync bookkeeping. |

**Date columns:** `valid_from`, `valid_to`, `created_at` (list column **Created At**), `updated_at`.

**Available filters** (Internal Users list / `GET /api/v1/user-management/access-agents/contact-access`): free-text **search** (`query`, placeholder *Search contact access agents...*), `agent_id`, `contact_id`, sort/dir. The grouped view also has a **Select access agent** picker for bulk grants.

**Example questions**
* "Which AI agents can *{contact phone/name}* run as right now?" (`is_allowed=true` and current time within window)
* "List grants for the *{agent}* agent." (`agent_id`)
* "Which grants have expired?" (`valid_to < now`)
* "Which grants are explicitly denied?" (`is_allowed = false`)
* "Show contacts granted access this month." (`created_at` range)
* "Which contacts have more than one agent grant?" (grouped view)

> **Contact id ≠ Respond.io id.** `respond_contact_id` is the internal `respond_contacts.id` (UUID), not the Respond.io `respond_io_id` used for inbox URLs. Resolve via the contact before building any Respond.io link.

---

## Contact Access Types — `contact_access_types` (`ContactAccessType`)

Menu: **Contact Access Types** (page title *Contact Access Types*). The configurable per-tenant **classification catalog** for WhatsApp contacts (e.g. `end_user`, `dealer`, `sorento_dealer`). It is **not** RBAC for staff — it drives **promotion / attachment visibility**: a resource carries an `access_levels` array and a contact sees it when the contact's assigned codes **overlap** that array. A contact's codes live in the many-to-many `respond_contact_access_types`.

**Key fields**

| Field | Meaning |
|-------|---------|
| `code` | Primary key — the canonical code (list column **Code**; placeholder *e.g. dealer*). |
| `name` | Display name (list column **Name**; placeholder *e.g. Dealer*). |
| `description` | Free text (list column **Description**). |
| `keywords` (JSONB array) | Admin-curated synonyms (list column **Keywords**; placeholder *customer, homeowner, b2c*) resolved against free-text AI/user phrasing → the canonical code. |
| `is_active` | Active flag (list column **Status**). Only active types appear in pickers. |
| `sort_order` | Ordering (list column **Sort order**). |

**Date columns:** `created_at`, `updated_at`.

**Available filters** (Contact Access Types admin list): client-side over `code` / `name` / `keywords`; sortable by **Code**, **Name**, **Sort order**, **Status**. Created/edited inline via a modal (this page does use standard hard-delete with confirmation).

**Example questions**
* "List all active contact access types and their codes."
* "What synonyms map to the `end_user` code?" (**Keywords**)
* "Which access type does *'homeowner'* resolve to?" (search **Keywords**)
* "What's the display name for the `sorento_dealer` code?"
* "Which access types are inactive (hidden from pickers)?" (`is_active = false`)
* "In what order do access types appear?" (`sort_order`)

> A contact's **assigned** codes (the M2M) are managed on the contact record, **not** here — this page is the catalog of available types. Default fallback codes when no catalog exists yet: `dealer`, `end_user`.

---

## Cross-entity notes

* **Permission path:** `users` → `user_role_assignments` → `user_roles` → `user_role_permissions` → `user_permissions`. A user has a permission iff one of their assigned roles grants it. There is **no** direct user→permission table.
* **SLA routing path:** `access_agents` → `agent_teams` (team-set `code` + `tier` + `policy_id`) → `teams` → `team_members` (round-robin via `sort_order` + `include_in_round_robin`, pool narrowed by `team_member_brands` / `team_member_market_segments`) → `users` (and the user's `tier` + notify toggles). See [SLA — form-SLA configuration](../sla/form-sla-configuration.md).
* **Access-grant path (conversations):** `respond_contacts` → `contact_agent_access` (Internal Users, time-boxed) → `access_agents` (AI Agents) → `agent_mcp_tools` → `mcp_tools`.
* **Visibility path (content):** `contact_access_types` (catalog) ↔ `respond_contact_access_types` (a contact's codes) overlapped against a resource's `access_levels` array.
* **Tier is overloaded.** `users.tier` = the user's conversation-SLA policy tier; `agent_teams.tier` = which escalation level a team plays *for one agent's team-set*. They are related concepts but different columns — be explicit which one a question is about.

## See also

* [Manage users and roles](manage-users-and-roles.md)
* [Manage teams and round-robin assignment](manage-teams.md)
* [SLA — form-SLA configuration (team tiers)](../sla/form-sla-configuration.md)
* [SLA — policies & notification matrix](../sla/sla-policies.md)
* [SLA — conversation vs form SLA](../sla/conversation-vs-form-sla.md)
</content>
</invoke>
