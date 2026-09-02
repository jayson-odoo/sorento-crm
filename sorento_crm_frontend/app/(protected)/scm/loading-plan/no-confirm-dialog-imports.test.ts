/**
 * AC-I1 (`scm-loading-plan-feedback-2sep-acceptance-criteria.md`): destructive record
 * actions on a loading plan (Cancel, Delete) are deferred actions now (D7, S1) - a
 * countdown in the toast or the gear's primary slot, never a confirm dialog. Nothing under
 * `scm/loading-plan/` may import `ConfirmActionDialog` or `ConfirmDeleteDialog` any more, a
 * property of the whole tree a render test cannot speak for (same reasoning as
 * `components/ui/a11y-guardrails.inventory.test.ts`).
 *
 * The remaining DATA-LOSS prompts (Refresh suggestion, a new cut-off, leaving with typed
 * quantities - the D7 carve-out AC-A6 names) are their own local, non-destructive
 * confirmation (`DataLossPrompt` in `LoadingPlanView.tsx`), built on `AlertDialog`
 * directly rather than on the retired component.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOT = path.join(__dirname);
const BANNED = ['ConfirmActionDialog', 'ConfirmDeleteDialog'];

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

describe('scm/loading-plan imports neither ConfirmActionDialog nor ConfirmDeleteDialog (AC-I1)', () => {
  it('no import statement anywhere under this tree names either component', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(ROOT)) {
      const src = fs.readFileSync(file, 'utf8');
      const importLines = src
        .split('\n')
        .filter((line) => /^\s*import\b/.test(line));
      for (const line of importLines) {
        for (const banned of BANNED) {
          if (line.includes(banned)) offenders.push(`${file}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
