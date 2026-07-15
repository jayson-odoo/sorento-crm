# Manage users and roles

Use this when you need to add someone to the CRM, control what they can do (via a **role**), or change the individual capabilities a role grants (via **permissions**). Permissions never attach to a person directly — they attach to a **role**, and you assign roles to the **user**.

## Add a user

1. Go to **[User Management → Administrative Users](/user-management/users)**.
2. Click **Add user** (top-right).
3. In the **Add User** dialog, fill:
   * **Name**
   * **Email** — the login identity (must be unique).
   * **Contact Number** — optional; unique across users (one phone = one user). Required if you later want WhatsApp SLA notifications.
   * **Roles** — pick one or more roles. If you leave it empty, the **default role** is assigned automatically.
   * **Superior** — optional reporting line (searchable by name or email).
4. Click the submit button to create the user.

**What gets created:** a row in `users` (status defaults to **Inactive**) plus a row per role in `user_role_assignments`. The user is emailed an invitation to set a password and verify their email; until they do, **Last Sign In** stays blank.

## Activate / deactivate / re-invite

On the **Administrative Users** list, select one or more rows and use the bulk actions: **Bulk activate**, **Bulk deactivate**, **Bulk send invitation**. A user must be **Active** to sign in. (Single-row equivalents are on each row's menu.)

## Change a user's roles

1. Open the user (or use the edit dialog from the list).
2. Edit the **Roles** field — adding/removing roles immediately changes which permissions the user has.
3. Save.

**What gets updated:** the user's `user_role_assignments` are replaced with the chosen set (`PUT /api/v1/user-management/users/{id}/roles`). Permission changes take effect on the user's next request — no re-login needed for most checks.

## Set notification & SLA fields on a user

The user edit dialog also controls how SLA work reaches them:

* **Tier** — the user's conversation-SLA escalation tier (1, 2, …).
* **Superior** — reporting line.
* **WhatsApp Contact** — link the WhatsApp contact this user is reachable on (required for any WhatsApp notification).
* Notification checkboxes (each fires only when the SLA **stage** also allows the event):
  * **Email on assignment** / **Email on escalation** (both default on)
  * **WhatsApp on assignment** / **WhatsApp on escalation** (need a linked WhatsApp contact)
  * **Email on deadline extended** / **WhatsApp on deadline extended**
  * **Email on products discontinued** / **WhatsApp on products discontinued**
  * **WhatsApp daily SLA summary**

In-app notifications always fire for an assignee when the stage allows the event; these toggles only gate the email/WhatsApp channels. See [SLA — policies & notification matrix](../sla/sla-policies.md).

## Create or edit a role (and choose its permissions)

1. Go to **[User Management → Roles](/user-management/roles)**.
2. Click **Add Role** (or edit an existing one — the dialog title reads **Edit Role**).
3. Fill:
   * **Role Name** — unique display name.
   * **Slug** — stable machine slug (e.g. `users:delete`). Used internally; doesn't change with the name.
   * **Description** — optional.
4. Choose the role's **permissions** by ticking them in the permission list. You can also **Copy permissions from role** (a picker) to clone another role's grants as a starting point, then adjust.
5. Optionally assign users to the role directly via **Assigned Users**.
6. Save.

**What gets created/updated:** a `user_roles` row plus one `user_role_permissions` row per ticked permission. Saving a role **replaces** its permission set with your selection. Protected/system roles (`is_protected`) are guarded against deletion.

## What permissions a role grants

A **permission** (slug like `order_management.orders.view`) is the atomic capability the backend checks on each route. Browse them at **[User Management → Permissions](/user-management/permissions)**; use **Filter by role** to see exactly which permissions a given role includes. A user can do something iff one of their assigned roles grants the matching permission slug — there is no per-user permission override.

## Delete a user

Administrative Users use **trash → restore → permanently delete** (not the standard one-step hard delete). From the list, **Trash** a user to deactivate/soft-remove them; trashed users can be **Restored**, and only then offered **Permanently delete**. Use the **Trashed** filter (**Active only** / **Trashed only** / **All**) to find trashed accounts.

## See also

* [User Management — Data reference for admins](data-analysis.md)
* [Manage teams and round-robin assignment](manage-teams.md)
* [SLA — policies & notification matrix](../sla/sla-policies.md)
</content>
