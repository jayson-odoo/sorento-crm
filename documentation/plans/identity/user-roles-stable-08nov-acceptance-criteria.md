# UAC: user-roles-stable-08nov

- AC-1: Saving the same role set keeps every assignment row's id and assigned_at, and the primary role.
- AC-2: Adding a role keeps the existing rows untouched and the primary role unchanged.
- AC-3: Removing the primary role makes the next-oldest assignment primary.
- AC-4: Two assignments tied on assigned_at resolve by assignment id ascending, in every primary-role lookup.
- AC-5: Saving the same company set keeps every `user_companies` row id and created_at; adding/removing
  touches only the added/removed rows; last_active_company_id rules are unchanged.
