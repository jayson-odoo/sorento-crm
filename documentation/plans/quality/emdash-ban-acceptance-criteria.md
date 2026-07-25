# Emdash Ban - Acceptance Criteria

> Status: DRAFT (2026-07-17). Cross-cutting FE + BE quality rule. Own branch off main, own PR.
> Goal: purge em-dash (`—` U+2014) and en-dash (`–` U+2013) from human-authored source so the UI
> stops reading as LLM-generated ("vibe coded"), and lock the rule into the governing docs.

## Criteria

- **ED-1 (FE UI strings clean).**
  GIVEN the frontend source
  WHEN linting runs
  THEN no em-dash or en-dash appears in JSX text, string literals, or template literals that render
  to the UI. An ESLint rule `no-emdash` reports these as `error`.

- **ED-2 (ESLint rule enforced).**
  GIVEN a newly introduced em/en dash in a FE UI string
  WHEN `npm run lint` runs
  THEN it fails with a clear message pointing at the character and suggesting a hyphen.

- **ED-3 (BE user-facing strings clean).**
  GIVEN backend user-facing strings (toast/message text, WhatsApp templates, PDF copy, notification
  bodies)
  WHEN reviewed
  THEN they contain no em/en dash; a hyphen or reworded phrase is used instead.

- **ED-4 (LLM output stripped).**
  GIVEN streamed/returned LLM text rendered in the product (AI assistant replies, generated
  explanations)
  WHEN it is emitted to the client
  THEN em/en dashes are replaced with a hyphen in a post-process step (model tokens cannot be
  linted).

- **ED-5 (Exclusions).**
  Markdown docs (`**/*.md`), code comments, `node_modules`, generated files, and third-party
  vendored code are NOT swept and NOT linted for this rule (em-dash is legitimate prose there).

- **ED-6 (Existing occurrences purged).**
  GIVEN the current codebase
  WHEN the sweep completes
  THEN all pre-existing em/en dashes in in-scope FE UI strings and BE user-facing strings are
  replaced, verified by a repo grep returning zero in-scope hits.

- **ED-7 (Rule in governing docs).**
  `PRINCIPLES.md` (hard-fail rules) and `CLAUDE.md` (code-review + FE layering rules) each carry a
  line banning em/en dash in human-authored source, with the scope and the ESLint enforcement noted.

- **ED-8 (No behaviour change).**
  The sweep changes only punctuation in strings; no logic, no test expectations beyond string
  literals, no snapshot meaning changes.

## Rule text (canonical, for PRINCIPLES.md + CLAUDE.md)

> No em-dash (`—`) or en-dash (`–`) in human-authored source. Use a hyphen (`-`) or reword. Applies
> to FE JSX/TS UI strings, BE user-facing strings, and LLM output (post-process strip). Excludes
> markdown docs and code comments. Enforced by the ESLint `no-emdash` rule on the frontend.
