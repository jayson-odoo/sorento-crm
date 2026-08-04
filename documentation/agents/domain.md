# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root — this repo is multi-context. The map lists
  each glossary and what it covers. Read the one covering your area; read both when
  a change crosses them.
- **`documentation/adr/`** — read ADRs that touch the area you're about to work in.
  All ADRs live here, system-wide and module-scoped alike; there are no per-context
  ADR directories.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The producer skill (`/grill-with-docs`) creates them lazily when terms or decisions actually get resolved.

## File structure

This repo is multi-context (`CONTEXT-MAP.md` present at the root):

```
/
├── CONTEXT-MAP.md                     ← index of the glossaries below
├── CONTEXT.md                         ← Dealer Sales Kit, Authoring, Products and
│                                        selling, Space and design, After-sales,
│                                        Supply and purchasing
├── documentation/
│   ├── CONTEXT.md                     ← Project Sales, Company vs Tenant,
│   │                                    Core vs Module
│   ├── adr/                           ← all architecture decisions
│   │   ├── 0001-status-engine-as-core.md
│   │   └── 0012-change-propagation-by-recompute-and-diff.md
│   └── agents/                        ← this file, plus issue-tracker + triage-labels
├── sorento_crm_frontend/
├── sorento_crm_backend/
└── sorento_crm_mcp/
```

Note this repo uses `documentation/`, not `docs/`. Anything in a skill that says
`docs/adr/` means `documentation/adr/` here.

The four-sibling monorepo layout (frontend / backend / mcp / root compose) is a
deployment boundary, not a context boundary — the glossaries cut across it by
domain, not by service.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in the relevant `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (a dealer is a customer, not a company) — but worth reopening because…_

## Related binding docs

These are not glossaries, but they constrain implementation and are treated as
binding by `CLAUDE.md`:

- `documentation/ADR-PRODUCT-STANDARDS.md` — CRUD UX standard
- `documentation/ARCHITECTURE-RULES.md` — frontend layering rules
- `PRINCIPLES.md` — governing process rules (step 0: guided user experience first)
