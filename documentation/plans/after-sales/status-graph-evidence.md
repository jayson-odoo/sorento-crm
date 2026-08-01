# Complaint status graph - evidence, and four corrections

Derived from live code and the live database on 2026-08-01, to satisfy AC-A3: the engine-managed graph must
reproduce today's status strings **verbatim**, because `complaints.status` is a bare `VARCHAR(50)` with no FK
and no CHECK constraint, and services branch on the spelling by name.

## The vocabulary is 12 strings, not 11

Live data (`SELECT status, count(*) FROM complaints GROUP BY status`, 51 rows total):

| status | rows | | status | rows |
|---|---|---|---|---|
| approved | 12 | | rejected | 4 |
| submitted | 10 | | fulfilled | 3 |
| responded | 7 | | closed | 1 |
| processed_by_cs | 7 | | updated | 1 |
| draft | 5 | | new | 1 |

Plus two that hold no rows today but are live comparison targets:

- **`voided`** - assigned at `complaints_service.py:2346`, also spelled at `:2304` and `:2368`. Confirmed
  never reached: `voided_at` and `void_reason` are NULL on all 51 rows, and `voided` appears nowhere in
  `audit_logs.new_values->>'status'` across 1.87M complaint audit rows.
- **`resolved`** - **the one the first pass missed.** It is a live member of
  `_VOID_BLOCKED_STATUSES = ("voided","rejected","resolved","closed","processed_by_cs")`
  (`complaints_service.py:2306`), and it is in **both** frontend pill maps
  (`lib/complaint-status.ts:16`, `lib/status-pill.ts:21`). It was the original name for what is now
  `processed_by_cs`; migration `227_complaint_resolved_status` introduced it and **no migration ever renamed
  it** (zero hits for `processed_by_cs` across all 332 migrations outside docstrings). It reached data once:
  one `audit_logs` row, 2026-06-09, entity `89a69d10-388f-461e-a40a-a46048990211`, `approved -> resolved`.

A graph omitting `resolved` leaves the string spelled in three places the registry claims to be the only
place a status is spelled.

## Transition edges, with the code that performs each

```
draft            -> submitted        portal_service.py:874-879 (guard, then assign)
rejected         -> submitted        portal_service.py:874-879 (resubmission)
new              -> responded        complaints_service.py:1686 (_RESPONSE_STAGE_STATUSES) + :1881
submitted        -> responded        same
updated          -> responded        same
responded        -> approved         :1974-1977 (_DECIDE_ALLOWED_*) + :2045
responded        -> rejected         same
approved         -> processed_by_cs  :2133-2134 (_RESOLVE_ALLOWED_FROM / _FINALIZE_STATUSES) + :2252
approved         -> closed           same
processed_by_cs  -> fulfilled        complaint_fulfilment_service.py:313-316 (all linked DOs delivered)
fulfilled        -> processed_by_cs  complaint_fulfilment_service.py:317-322 (auto-reopen)
{draft,new,submitted,updated,responded,approved,fulfilled} -> voided
                                     complement of _VOID_BLOCKED_STATUSES (:2303) + :2339 guard + :2346
```

`fulfilled` really is voidable: it is absent from the blocked list. `rejected` and `processed_by_cs` are not.

**Sinks:** `closed` and `voided` are true sinks. `rejected` exits only via portal resubmit - note the n8n
resubmit path (`complaints.py:1057-1097`) *requires* `rejected` but never changes the status, so an n8n
resubmit leaves it there. `processed_by_cs` exits only via auto-fulfilment.

**Dead on the write side:** `updated` (1 live row, zero audit writes ever) and `resolved`.

## Correction 1 - there are two entry points, not one

`draft` is the portal entry (`portal_service.py:1064`). `new` is the in-system and n8n entry, from the column
default `Column(String(50), default="new")` (`models/complaints.py:43`); `create_complaint` never sets a
status. Both have no incoming edge.

The first port's test asserted **exactly one** `is_initial` per entity and pinned it to `draft`. That
invariant is wrong for complaints, and it forced an invented `draft -> new` edge ("Log in system") purely to
give `new` a parent. Nothing in the codebase moves a complaint from draft to new. **The invariant must allow
multiple entry points, or `new` must be modelled as the default with `draft` as portal-only.**

**RESOLVED 2026-08-01: only the second option is reachable, and the first would have broken the admin UI.**
Two `is_initial` rows are not merely ambiguous on the adopted engine, they are rejected:
`status_service.validate_graph` (`:308-321`) raises `status_graph_multiple_initial` on a second flagged row,
and `api/v1/system/statuses.py` calls it after **every** status and transition write. A graph seeded with two
starting states would therefore 422 the first edit an admin made to any complaint status. Allowing multiple
entry points would mean changing engine semantics that project-sales already depends on, which this slice does
not do.

So: `is_initial` and `is_default` both go to **`new`**, because `initial_status()` is documented as "the status
a new record starts in" and a bare create lands on `new` via the column default. A test pins
`initial_status(...).key == Complaint.__table__.c.status.default.arg` so the engine and the column cannot
drift. `draft` is declared in `COMPLAINT_ENTRY_POINT_KEYS` instead.

Note that entry points cannot be derived structurally as "no incoming edge": `updated` has none either, now
that the invented `submitted -> updated` edge is correctly absent, so that rule would return three.

## Correction 2 - one invented edge resurrects deleted behaviour

`submitted -> updated` was also invented. `update_complaint` used to auto-flip to `updated`, and that was
deliberately removed - the comment at `complaints_service.py:1707-1711` records it: "a plain save must NOT
auto-transition the status ... The old auto-'updated' flip was unwanted." The single live `updated` row is a
relic of the removed behaviour. Declaring the edge re-legitimises what was taken out on purpose.

## Correction 3 - `voided` must be neutral grey, not red

The first port coloured `voided` rose. `lib/status-pill.ts:23-25` states the opposite explicitly: "Neutral
gray (muted), deliberately NOT red - voiding is administrative, not an error/rejection." Note also that the
two frontend maps have **drifted in opposite directions**: `complaint-status.ts` has `resolved` and lacks
`voided`; `status-pill.ts` has `voided` and lacks `fulfilled`, while its header claims to mirror the other.
A voided complaint currently renders neutral grey by *fallback*, visually identical to draft and new.

## Correction 4 - the write path is unguarded, so the graph is advisory

`ComplaintUpdate.status` is a bare `Optional[str]` (`schemas/complaints.py:158`, `:211`) applied by a blind
setattr loop:

```python
# complaints_service.py:1713
for key, value in update_data.items():
    setattr(complaint, key, value)
```

reached from `PUT /api/v1/complaints/{complaint_id}` (`complaints.py:1242`). Any authenticated caller or
`X-API-Key` client can set any status from any state. The FE never sends `status` in a write payload, so this
is an API-surface hole rather than a UI one - but **an engine that guards only the dedicated action routes
(`/approve`, `/reject`, `/process`, `/close`, `/void`) changes nothing about what is reachable.** Guarding
this path is what converts the graph from documentation into enforcement, and it belongs in the slice that
registers the entity.

**There are TWO such holes, not one.** `update_complaint_and_reply` has its own blind setattr loop
(`complaints_service.py:1839`), takes the same `ComplaintUpdate`, and is reached from
`POST /{complaint_id}/update-and-reply`. Guarding only the `PUT` would leave the graph advisory one route
over. Both are now guarded by one shared helper.

**RESOLVED 2026-08-01, guard implemented, with the evidence that made it safe.** Every complaint status change
in `audit_logs` was aggregated across 1.87M complaint audit rows: **11** distinct `from -> to` pairs exist, and
every one is a declared edge except the single `approved -> resolved` from 2026-06-09 documented above
(`processed_by_cs->fulfilled` 199,957; `approved->closed` 40,563; `fulfilled->processed_by_cs` 33,268;
`approved->processed_by_cs` 23,929; `responded->approved` 11,524; `responded->rejected` 11,480;
`new->responded` 768; `draft->submitted` 21; `submitted->responded` 21; `rejected->submitted` 5;
`approved->resolved` 1). So no out-of-graph jump has ever occurred, and the guard rejects only a class of call
with no history.

Two deliberate **fail-open** escapes keep registration a no-op:

1. **A write repeating the status the record already holds is skipped** - it is not a transition. This matters
   specifically because such a write leaves **no audit diff**, so it is exactly the case the historical
   evidence above is blind to. A caller PUTting a whole record back unchanged must keep working.
2. **An unseeded graph makes the guard a no-op**, because failing closed would reject every status write on a
   deploy where the code lands before the seed migration.

## Two defects found while gathering this, unrelated to the engine

- **Voiding a complaint leaks its SLA tracker.** `voided` is not in either live `form_sla_configs` stage's
  `resolve_event` (`main` resolves on `approved,rejected`; `customer_service` on `resolved`), so
  `emit_form_event(..., "voided")` at `:2368` resolves nothing and the clock keeps running. Current state:
  232 unresolved trackers against 34 resolved for `source_entity_type='complaint'`.
- **The FE status filter offers 5 of the 10 live values.** `ComplaintsList.tsx:404-411` lists only `new`,
  `updated`, `responded`, `approved`, `rejected` - so `draft`, `submitted`, `processed_by_cs`, `fulfilled`,
  `closed` and `voided` are unreachable from the UI filter, including the two most common after `approved`.

## `workflow_stages` - safe to drop, and the adopted migration already drops it

The table **does not exist in the live database** (verified), while its three siblings from the same migration
`150_base_workflow_respond_entity_conv` all do. Why it is absent could not be determined and is not guessed
here. Nothing references `WorkflowStage` outside `models/__init__.py` and one lookup-eligibility denylist
string; the `commercial_core/_base_patches.py` back-references its docstring describes **do not exist** - that
module was removed by `296_drop_commercial_modules` and the orphan model was left behind.

No `upgrade` path breaks: migration 150 is an ancestor of the current head, so Alembic never re-runs its
`create_table`. Only a `downgrade` past 150 would fail, on `drop_table`. One asymmetry worth knowing: because
the model is in `Base.metadata`, `Base.metadata.create_all` **does** create `workflow_stages` in a fresh
pytest scratch schema, so it exists in test environments and not in production.
