# A generic project skeleton and the Sorento sales extension ship together, never apart

`dreamz_ems` already models an event as a **Project** created from a **Project Template**
belonging to a **Project Type**, with participants carrying template-configured roles. Sorento
needs the same skeleton, so the `projects` module is split in two layers that are built and
merged in the same release:

- **Generic** (shaped to mirror EMS so it ports by copy): `project_types`,
  `project_templates` + template roles, `projects`, `project_stakeholders`,
  `project_parties`, and an activities-feed adapter.
- **Sorento sales extension** (explicitly named, no pretence of generality):
  `project_sales_profile` (developer party, SPV, location, launch date, GDV estimate, brands),
  `project_quotations` + versions + lines, `project_samples`, `project_purchase_orders`, and
  the sponsorship link.

Stakeholder roles — decision maker, influencer, info provider, architect — are **template
configuration**, not an enum, exactly as EMS models participant roles.

The pairing rule is the point of this ADR. A `commercial_core` / `commercial_activity` module
(~5,000 LOC: leads, master quotations, pipeline, process config, project tasks) was built in
`c77560009` and deleted as unused in `7f0eb94f1`. It died because it was a generic CRM
skeleton with nothing fitted to how Sorento actually sells — no registration lock, no sample
submission, no sponsorship, no brand or architect intelligence. This is attempt #2. The
skeleton is permitted only because the specific guts land with it.

## Rejected

- **Fully generic with per-type JSONB custom fields** — developer, launch date, brands and GDV
  become untyped JSON: no FKs, no fuzzy dedup on developer, no forecast SQL, no brand
  intelligence. This is the failure mode above, repeated.
- **Sorento-specific now, generalise later** — fastest to the client's value, but retrofitting
  types and templates onto a live pipeline is a migration on production data, and the EMS
  convergence is near.
