# S0 pre-flight query 6: readers of `users.email` that break on NULL

Plan 4.1 and 9.1 Q6. Measured by grep over `sorento_crm_backend/app` on the S0 lane (26 Sep 2026):
every `.email`, `["email"]`, `get("email")`, `EmailStr` and `email: str` hit, with other models
(customers, suppliers, contacts, onboarding, leads) excluded. About 220 readers are already
null-safe (`or ""`, Optional schema fields, filtered recipient lists, SQL comparisons, the
notification email channel marking "User has no email address"). The ones that are not, each
guarded in S0 with a test:

| Reader | Failure on NULL | Guard |
| --- | --- | --- |
| `app/schemas/user.py` `UserBase.email: str` (inherited by `UserResponse`) | response validation error on `GET /users/`, `/users/me`, `/users/{id}`, `PUT /users/{id}`, `PUT /me/profile`, create and invite: one phone-only user breaks the whole Users list | `UserResponse.email: Optional[str]` (create input keeps requiring email until S3) |
| `app/schemas/user.py` `UserSelectResponse.email: str` | `GET /users/select` (every user dropdown) 500s | `Optional[str]` |
| `app/schemas/sla.py` `UserSimple.email: str` | every SLA tracking list, detail, extend, resolve and event log response fails when the assignee has no email | `Optional[str]` |
| `app/services/user_service.py` Respond agent sync, `email.strip().lower() == user.email.strip().lower()` | `AttributeError` for a phone-only user | compare `(user.email or "")`; with no email mark the sync failed with "User has no email" instead of raising |
| `app/api/v1/user_management/users.py` `_send_invitation_link_for_user` | answers "Invitation link sent to None." while nothing is sent | refuse with 400 "User has no email" before writing a token; bulk resend skips it |
| `app/services/user_service.py` role-conflict label `f"{u['name']} ({u['email']})"` | cosmetic "Name ()" | label is name, else email, else phone |
| `app/schemas/auth.py` `LoginResponse.email: EmailStr` | safe today (login is by email); a phone login would 500 | `Optional[EmailStr]` (S1 relies on it) |

Display fallbacks of the form `user.name or user.email` (about 80 sites) yield an empty label for
a user with neither name nor email; none of them raise. Left as is in S0: every user the owner
creates in S3 has a name (the Add user modal requires it).
