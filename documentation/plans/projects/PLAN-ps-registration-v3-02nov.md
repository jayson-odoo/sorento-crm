# PLAN: PS-REGISTRATION-V3 (registration selections, party contacts, lead source, customer optional)

Status: Build done, in review (PR #2099). Track: normal (migration). Card: `CARD-ps-registration-v3-02nov.md` (v1.2,
all questions answered). UAC: `ps-registration-v3-acceptance-criteria.md`. Mock: `mockups/ps-registration-v3.html`.

## Journey

A salesperson registers a project from the 2 Nov Project Sales demo flow: they pick, rather than type, who is on
the job (developer, architect, main contractor, subcontractors, trading houses, tender parties, consultant,
interior designer) and the people at each firm, say where the lead came from, and may leave the customer for
later. When a proposal or quotation goes out on WhatsApp, they pick which party to send it to; a missing number is
typed once and kept on the party.

## Slices (one lane, one PR)

1. BE (done, 6831c227 + 764a2492 + deferred delete): models, migration, `project_party_contact_service`, routes,
   lookup-set validation shared with leads, server-side party sort, `project_party_contact.delete`.
2. FE (done): Parties grid on server sort/paging + Contacts column; party page Contacts section; register form;
   WhatsApp "Send to"; project page parties + lead source.
3. Review + browser pass + guide + hand-test script.

## Contract

- `POST /projects/` body adds `lead_source` (required unless a draft), `party_links: [{role, party_id}]`,
  `contact_ids: [id]`. `customer_id` optional.
- `PUT /projects/{id}` adds `lead_source`, `party_links` (present = replace, absent = keep).
- Project response adds `party_links: [{role, party_id, name}]`; `lead_source` = own, else the lead's.
- `GET|POST /parties/{id}/contacts`, `PUT|DELETE /parties/{id}/contacts/{cid}`; pending action
  `project_party_contact.delete`.
- `GET /parties/?sort=&dir=` (name, party_type, is_active, project_count, contact_count, customer_name); rows add
  `contact_count`.
- `GET /projects/{id}/parties` -> `{data: [{party_id, party_type, role, name, phone, contacts: [{stakeholder_id,
  party_contact_id, name, job_title, phone, email}]}]}` (shape shared with PS-PROPOSAL-QUOTATION, #2097).
- `POST /projects/{id}/parties/{party_id}/phone` `{phone, stakeholder_id?}`: fills an empty number only (409
  `project_party_phone_on_file`), party must be on the project (404), needs the edit right on the project.

## Triggers deliberately not built

- A many-per-role consultant or interior designer: build when a real project needs two (owner Q5 said one).
- District sets for a state added later: an admin adds a lookup set `my_district_<state>` in Settings.
