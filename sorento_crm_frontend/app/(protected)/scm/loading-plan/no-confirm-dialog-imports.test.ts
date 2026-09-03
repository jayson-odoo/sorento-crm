/**
 * AC-I1 (`scm-loading-plan-feedback-2sep-acceptance-criteria.md`): destructive record
 * actions on a loading plan (Cancel, Delete) are deferred actions now (D7, S1) - a
 * countdown in the toast or the gear's primary slot, never a confirm dialog. That is a
 * property of the whole tree, which a render test cannot speak for (same reasoning as
 * `components/ui/a11y-guardrails.inventory.test.ts`).
 *
 * What is banned under `scm/loading-plan/` is `ConfirmDeleteDialog` and a raw
 * `AlertDialog` - the two ways a destructive dialog gets built. `ConfirmActionDialog` is
 * ALLOWED and is the vehicle for the three DATA-LOSS prompts (Refresh suggestion, a new
 * cut-off, leaving with typed quantities - the D7 carve-out AC-A6 names): those ask because
 * something TYPED would vanish, not because a record is on its way out. A local copy of it
 * was worse than the import, because a second copy of a dialog is a second place for its
 * behaviour to drift (SF-2).
 *
 * The scan reads whole import STATEMENTS, not lines: a multi-line `import { ... } from` is
 * exactly how the banned components arrive, and a line-by-line match never saw them (SF-7).
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOT = path.join(__dirname);
/** Matched against the text of each import statement: a component name or a module path. */
const BANNED = ['ConfirmDeleteDialog', '@/components/ui/alert-dialog'];
const IMPORT_STATEMENT = /import[\s\S]*?from\s+['"][^'"]+['"]/g;

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (
        (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) &&
        !entry.name.includes('.test.')
      ) {
        out.push(full);
      }
    }
  };
  walk(dir);
  return out;
}

describe('scm/loading-plan imports no destructive confirmation dialog (AC-I1)', () => {
  it('no import anywhere under this tree names ConfirmDeleteDialog or a raw AlertDialog', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(ROOT)) {
      const src = fs.readFileSync(file, 'utf8');
      for (const statement of src.match(IMPORT_STATEMENT) ?? []) {
        for (const banned of BANNED) {
          if (statement.includes(banned)) offenders.push(`${file}: ${banned}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
