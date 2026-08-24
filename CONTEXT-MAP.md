# CONTEXT-MAP

This repo's ubiquitous language is split across two glossaries. Read the one
covering the area you're working in; read both when a change crosses them.

| Glossary                   | Covers                                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------ |
| `CONTEXT.md`               | Dealer Sales Kit, Authoring, Products and selling, Space and design, After-sales, Supply and purchasing |
| `documentation/CONTEXT.md` | Project Sales (module `projects`), Company vs Tenant, Core vs Module                                    |

Architecture decisions for both live in `documentation/adr/`.

Terms are meant to be non-overlapping. If the same term appears in both with
different meanings, that's a defect - fix it rather than picking a winner.

The split is historical, not designed: `documentation/CONTEXT.md` came out of the
Project Sales work, `CONTEXT.md` out of the Dealer Sales Kit work. Collapsing them
into one file is fine and would reduce this map to a single row.
