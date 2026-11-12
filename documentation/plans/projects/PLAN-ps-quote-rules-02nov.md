# PLAN: PS-QUOTE-RULES (off-series line needs approval; discount request moves project to Final Negotiation)

Status: Review done (reviewer + security fixed), awaiting owner hand test and CI. Track: standard, size L (migration + security review), per crew 2 Nov.

## Scope

- B1: a project quotation/proposal line whose product is outside the project's series needs approval
  before the document can be sent (today: flag only).
- B2: a discount request on a project's proposal/quotation moves the project to Final Negotiation
  automatically (today: manual).

Out of scope: proposal vs quotation split, PO checks, approval tiers.

Rules, routing and decisions: `CARD-ps-quote-rules-02nov.md` (revisions 1-3).
