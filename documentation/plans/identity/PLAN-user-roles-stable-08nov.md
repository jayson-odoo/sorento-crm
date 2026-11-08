# PLAN: Edit user keeps role/company rows; deterministic primary role

Status: in progress (small fix track: backend only, no migration, no FE change)
Lane: USER-ROLES-STABLE. UAC: `user-roles-stable-08nov-acceptance-criteria.md`.

## Problem

Saving Edit user sends every role id (FE `user-profile-edit-dialog.tsx`). `UserService.set_user_roles`
deleted every `user_role_assignments` row and re-added them; `set_user_companies` did the same for
`user_companies`. `assigned_at` / `created_at` are `server_default=now()`, i.e. the transaction start,
so all re-added rows tie. The primary role is `ORDER BY assigned_at ASC` with no tie-break in five
places, so Postgres may return any of the tied rows: the primary role can flip on any save.

## Fix

1. `set_user_roles` / `set_user_companies` diff against the existing rows: keep rows whose
   role/company stays (same id and timestamp), insert only new ids, delete only removed ones.
2. One helper, `primary_role_order()` in `app/services/user_service.py`, returns
   `(assigned_at ASC, id ASC)`; all five primary-role lookups use it
   (`dependencies.py`, `phone_signin_service.py`, `impersonation.py`, `dev_login.py`).
3. No migration, no backfill. Rows already tied on prod resolve deterministically by `id` after
   this ships (the id is a random uuid, so the pick is stable but arbitrary); a read-only query
   to find them is in the PR body for the owner.
