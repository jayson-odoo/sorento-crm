# CARD - TAG-UNION: contact tags add up (union merge, live recompute, inactive tags ignored)

Status: Answered 8 Nov ~16:00 (1a, 2 everything adds up, 3a, 4a, 5 keep "Apply settings"); build in `PLAN-tag-union-08nov.md`. Lane TAG-UNION.
Track: full (new column + migration, access rules for every tagged contact, one-off recompute of prod data).

## Owner ask (8 Nov ~15:55)

Answer "A": tags ADD UP, like roles. A Sorento tag plus a Mocha tag gives both companies, not none.

## What exists today (origin/main eeca809d)

| Fact | Where |
| --- | --- |
| Tag settings are computed from all of a contact's tags and COPIED onto the contact row only when someone runs "Apply settings" (per contact, bulk, per tag, or "apply" on bulk tag add). The runtime reads only the contact row | `contact_tag_apply.py:371-462`; `api/v1/user_management/contact_tags.py:205-230`; `contact_tag_service.py:297-321` |
| Merge is MOST RESTRICTIVE: companies, access types, segments, attachment types intersect and an EMPTY result is still written (Sorento tag + Mocha tag = no companies) | `contact_tag_settings.py:572-579, 626`; writer `contact_tag_apply.py:46-79` |
| Brands and allowed item classes intersect; empty = conflict, not written. Regions the same | `contact_tag_settings.py:582-584, 614-615, 624-625` |
| Chatbot switches (AI replies, stock checks, escalation, packing list, notify salesman), portal forms, field reveals, agents, agent fields, messaging, image/voice access: AND (one tag off = off) | `contact_tag_settings.py:58-68, 543-545, 610-611, 616-618` |
| Media limits and clip length: min. Languages: intersect | `contact_tag_settings.py:594-595, 618` |
| Stock: include lists intersect, exclude lists union, strictest mode, "hide empty" OR. Include on one tag + exclude on another = conflict | `contact_tag_settings.py:598-602, 619-621, 914-924`; `stock_visibility.py:39` |
| Specs: shown lists intersect, hidden lists union | `contact_tag_settings.py:622-623` |
| Memory level: min. Tier: dealer wins, dealer + end user = conflict. "Requires registered project": OR | `contact_tag_settings.py:557-569, 612-613` |
| AI model: never copied, read live each turn; all tags must agree or none applies | `contact_llm_choice.py:29-45` |
| Removing a tag (or deleting it) changes no contact value: what it granted stays | `contact_tag_service.py:170-171, 206-225, 281-296` |
| Inactive tags still count in the merge, the apply, the AI model and the Differs count; only the dealer check skips them | `contact_tag_settings.py:848-863` vs `:876` |
| Apply overwrites whatever the contact holds for a key the tags set (manual edits are lost) | `contact_tag_apply.py:64-73, 86, 413-419` |
| Tag membership writers: contact page PUT, bulk tag (UI and the WhatsApp agent, #2247) | `contact_tag_service.py:206, 227`; `chatbot/agent/contact_tags.py:142, 219` |

## Rule table: old -> new

"Set" = the tag sets that setting. A tag that does not set a setting stays NEUTRAL (it neither
grants nor restricts), exactly as today; otherwise a tag that only picks an agent would open every
brand (Q1). Only ACTIVE tags count, everywhere (R4).

Grants (visibility, permission): UNION, "any tag allows". Restrictions (hide lists, off switches,
"required" flags): only when EVERY tag that sets them says so.

| # | Setting | Old merge | New merge |
| --- | --- | --- | --- |
| 1 | Companies | intersect, empty written | union |
| 2 | Access types | intersect, empty written | union |
| 3 | Market segments | intersect, empty written | union |
| 4 | Attachment types | intersect | union |
| 5 | Brands | intersect, "All" neutral, empty = conflict | union; any tag "All" = All |
| 6 | Allowed item classes (include list) | intersect, "All" neutral, empty = conflict | union; any tag "All" = All |
| 7 | Regions | intersect, empty = conflict | union |
| 8 | Portal forms (each form) | AND | OR (any tag shows it) |
| 9 | Field reveals (each DO field) | AND (one tag hides = hidden) | OR (hidden only when every tag that sets it hides it) |
| 10 | Chatbot agents (each agent) | AND | OR |
| 11 | Agent field access (each field) | AND | OR |
| 12 | Image / voice access | AND | OR |
| 13 | Image / voice monthly limit, voice clip length | min | max |
| 14 | Image / voice languages | intersect | union |
| 15 | Stock locations shown (include list) | intersect | union |
| 16 | Stock locations excluded | union | intersect (excluded only when every tag excludes it) |
| 17 | Include list on one tag, exclude list on another (stock, specs) | conflict, not written | resolved: visible = I or (all minus E), stored as the exclude list `E minus I`. No conflict any more |
| 18 | Stock mode | strictest (availability) | loosest (detailed > compact > availability) |
| 19 | Hide empty stock locations | OR | AND |
| 20 | Specs shown | intersect | union |
| 21 | Specs hidden | union | intersect |
| 22 | Stock checks, escalation, packing list | AND | OR |
| 23 | Notify salesman | AND | OR (any tag wants the salesman told) |
| 24 | Messaging (outbound) | AND | OR |
| 25 | Memory level | min | max |
| 26 | Requires registered project (a restriction) | OR | AND |
| 27 | AI replies (`chatbot_allowed`) | AND | OR (owner Q2: everything adds up, no strict exceptions) |
| 28 | ETA buffer days | OR | unchanged (OR) |
| 29 | Skip date-range questions, files as links | must agree, else conflict | OR (owner Q2: every switch, any tag on = on) |
| 30 | Tier | dealer wins, dealer + end user = conflict | unchanged: an identity, not a permission |
| 31 | AI model | read live, all must agree | unchanged rule, but inactive tags no longer count |

Known limit, stated not solved: one contact row holds ONE brand list and ONE class list, so tag A
"Sorento, all classes" plus tag B "Mocha, DIY only" unions to "Sorento + Mocha, DIY only"
(today it is a conflict). Pairing classes per tag would need per-brand class lists on tags; not in
this lane unless the owner says so (Q5 territory, no evidence of a real tag pair like this yet: the
dev counts below will show it).

## Live recompute (R3)

There is no "apply" step any more for access. A contact's tag-driven values are recomputed and
written in the same transaction when:

- a tag is added to or removed from the contact (contact page, bulk tag, the WhatsApp agent);
- a tag's settings change, it is switched active / inactive, or it is deleted (every holder);
- the one-off migration script runs (below).

Same writers as today (`contact_tag_apply._WRITERS`), same audit row per changed contact, now
naming the trigger ("Tag removed: Mocha dealer -> Companies: Sorento"). A tag with more holders
than the current 500 cap is recomputed in batches inside the request; if that proves slow on prod
counts it moves to the worker (trigger named, not built now).

Security consequence (for the security review): adding a tag, or editing a tag's settings, now
WIDENS access for every holder at once, with no preview step. The gates stay as they are: changing
a section on a tag needs that section's right (`contact_tag_settings._GATES`, companies =
superadmin). Adding / removing a tag on a contact today needs only `contacts.edit`; under live
recompute that would let a `contacts.edit` user grant companies or stock via a tag they could not
set by hand. New rule: adding or removing a tag needs, on top of `contacts.edit`, the gate of every
gated section that tag sets (companies -> superadmin, stock -> inventory.stock.edit, agents ->
access_agents.edit, messaging -> respond_workspaces.edit). The WhatsApp agent path checks the same.

## Manual edits and the contact's own overrides (R5)

Model: like roles plus direct grants. One new column `respond_contacts.tag_settings_snapshot`
(JSONB) holds, per setting, the value the tags last wrote. On each recompute, per setting:

- **Lists** (companies, brands, warehouses, ...): own additions = current minus snapshot; own
  removals = snapshot minus current. New value = (new tag union + own additions) minus own
  removals. So a company a person added by hand survives a tag removal, a company a person removed
  by hand stays removed after a tag edit, and a company only a removed tag granted goes away.
- **Switches and single values**: if current equals the snapshot (nobody touched it), take the new
  tag value. If a person changed it, keep the person's value. When no active tag sets the setting
  any more and nobody touched it, go back to the value the contact had before tags first set it
  (kept in the snapshot as `base`).
- A setting no tag ever set is not touched at all (snapshot has no entry).

Visible: the contact's Tag settings section keeps its per-setting rows (expected from tags vs
current), and each setting that differs now reads "Own change: +Sorento, -Mocha" (or "Own value:
Off") instead of "Differs". "Apply settings" keeps its name (owner Q5); its action is "reset this contact to its tags": it drops
the contact's own changes for the chosen settings (same preview first, same per-section rights). The tag list's
"Differs" count becomes "Own changes".

Why not "the contact's own values are just one more tag in the union": then a person could never
take a company away from a tagged contact by hand, only add. The snapshot model keeps both.

## One-off recompute of existing contacts

Script `scripts/recompute_contact_tag_union.py`, reviewed, owner runs it on prod:

1. `--dry-run` (default): per contact, old value -> new value per setting, plus a summary:
   contacts that change, by setting; contacts WIDENED (gain a company, brand, warehouse, agent,
   form, reveal) vs NARROWED; contacts that today hold the empty-companies result (tagged with
   companies-setting tags, zero companies); contacts whose value differs from today's merged tag
   value (counted as own changes and kept, Q3); contacts holding only inactive tags.
2. `--apply --expect N`: refuses unless the dry-run's change count equals N; one savepoint per
   contact, audit row per change ("Tag union recompute").
3. Seeding the snapshot: for each tagged contact and each setting its active tags set, snapshot =
   the value TODAY's rule (intersect / AND) expects. Where the contact holds exactly that, the
   whole value is tag-driven and moves to the union. Where it holds something else (a manual edit,
   or an apply nobody ran) the difference is kept as an own change (Q3).

Dev counts asked for with `crew-data-request` on this PR (masked, counts only): tags by active /
inactive and by section set; tagged contacts; contacts with 2+ active tags; contacts with the
empty-companies result; contacts holding an inactive tag that sets something; tag pairs with a
brand list on one and a class list on the other (the known limit above).

## Tests (red first, Phase 2)

Per row of the rule table one merge test (old value pinned, new value asserted), including the
Sorento + Mocha companies case and the include + exclude resolution; recompute on tag add / remove /
settings edit / deactivate / delete; own addition survives a tag removal; own removal survives a
tag edit; scalar own value kept, untouched scalar reverts to `base`; inactive tag ignored in merge,
AI model and dealer check; the new add-tag gate (403 for a `contacts.edit`-only user adding a
companies tag; agent path too); script dry-run counts and `--expect` refusal. Kill tests by the
reviewer on the merge table. Security review: required (access widening, RBAC gate change).

## Questions (owner), with recommendations

- **Q1 A tag that does not set a setting: neutral or "allows everything"?** (a) neutral, as
  today; (b) counts as All. Recommend (a): with (b) a "VIP" tag that only picks an agent would open
  every company and brand.
- **Q2 AI replies: keep strictest (any tag off = off) or union like the rest?** (a) strictest;
  (b) union. Recommend (a): "AI off" is a safety stop someone put on purpose; every other chatbot
  permission (stock checks, escalation, packing list) unions.
- **Q3 Existing contacts whose value today differs from what their tags say (manual edit, or apply
  never run): keep it as an own change, or let the tags win once in the migration?** (a) keep as
  own change, listed in the dry-run report, "Reset to tags" per contact; (b) tags win once.
  Recommend (a): no silent access change on contacts somebody set by hand; the report shows who
  they are so you can reset in bulk.
- **Q4 Adding a tag that grants companies / stock / agents / messaging: require the same right as
  setting it on the tag?** (a) yes, per gated section the tag sets; (b) `contacts.edit` is enough.
  Recommend (a): under live recompute adding a tag IS granting the access.
- **Q5 "Apply settings" button: rename to "Reset to tags" (drops own changes), or remove?**
  (a) rename, preview kept; (b) remove. Recommend (a): it is the only way to undo a manual edit in
  bulk.
