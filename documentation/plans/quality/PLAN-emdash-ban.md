# PLAN - Emdash Ban

> Status: DRAFT (2026-07-17). Cross-cutting FE + BE. Own branch off main, own PR. Ships independently
> (and first, per the M8 build order). UAC: `emdash-ban-acceptance-criteria.md`.

## Goal

Remove em-dash (`-`) and en-dash (` - `) from human-authored source so the UI stops reading as
LLM-generated, and lock the rule into the governing docs with lint enforcement.

## Approach

### 1. ESLint rule (FE) - ED-1, ED-2

- Add a `no-emdash` rule to `sorento_crm_frontend/` eslint config (custom rule or `no-restricted-syntax`
  matching `Literal` / `TemplateElement` / `JSXText` containing `-` or ` - `), severity
  `error`, message: "No em/en dash in UI strings - use a hyphen (-) or reword."
- Scope: app/component/lib source. Exclude generated files and `node_modules` (ED-5).

### 2. LLM output strip (FE) - ED-4

- Central post-process where assistant/LLM text is rendered (streaming render + final message
  formatter): replace `-` / ` - ` with `-` before display. Single shared helper so every
  surface (AI assistant, generated explanations) uses it.

### 3. Repo sweep - ED-6

- Codemod / scripted replace over in-scope FE UI strings and BE user-facing strings, replacing
  `-`/` - ` with `-` (or rewording where a hyphen reads wrong). Verify with a grep that returns zero
  in-scope hits. Do NOT touch `**/*.md`, comments, `node_modules`, vendored/generated code (ED-5,
  ED-8).
- BE user-facing surfaces to check: toast/message text, WhatsApp templates, PDF copy, notification
  bodies (ED-3).

### 4. Governing docs - ED-7

- Add the canonical rule line to `PRINCIPLES.md` (hard-fail rules list) and `CLAUDE.md` (FE layering
  / code-review hard rules), using the exact wording from the UAC "Rule text" section.

## Sequence

Docs + ESLint rule first (so new code is guarded), then the sweep (so lint passes), then the LLM
strip. Verify `npm run lint` green and grep-zero before PR.

## Risks

- **False positives in the sweep.** Some ` - ` may be intentional (rare). Review the diff; the sweep is
  punctuation-only (ED-8) so review is fast.
- **Rule scope creep.** Keep the ESLint rule off markdown and comments or it fights legitimate prose.
- **Hyphen reads wrong.** Where an em-dash joined a clause, reword rather than a bare hyphen.

## Verification

`npm run lint` fails on a planted em-dash; repo grep for `-`/` - ` in-scope returns zero;
PRINCIPLES.md + CLAUDE.md carry the rule; a sample AI reply containing an em-dash renders with a
hyphen.
