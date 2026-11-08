# PLAN: Dealer access portal (salesperson self-service dealer user access)

Status: Asked (behaviour card `CARD-dealer-access-portal-09nov.md` waits on owner answers). Track: full (new screen, grants data access, RBAC grant, Respond create).
Lane: DEALER-ACCESS-PORTAL

## Journey

A salesperson, in the CRM portal, picks one of THEIR customers (per company: Sorento / Mocha), adds 1..n
people (name, phone, access level), submits, and access works at once: the contact exists (Respond side
too if needed), is linked to that customer, carries the right access, and the bot answers that person with
the right scope. Replaces the Google Form + Excel import + manual tag + manual access-sheet link.

## Pipeline map (today)

See `CARD-dealer-access-portal-09nov.md` sections 2-3 (file:line map).
