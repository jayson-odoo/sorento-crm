/**
 * M5-02 (`PLAN-ui-motion-round2.md` 3.5) - zero non-demo files render the bare
 * string `Loading...` or `Loading…` as visible content. Baseline (measured on
 * this branch before the fix, `git grep -rlE 'Loading\.\.\.|Loading…' app
 * components --include='*.tsx' | grep -v '\.test\.'`): 50 files.
 *
 * Source scan, not a render test, for the same reason
 * `raw-table.inventory.test.ts` is: this is a property of the whole tree.
 *
 * The regex targets rendered TEXT NODES - a JSX child or a string literal that
 * ends up as visible copy (a placeholder prop counts: it renders inside the
 * control the same as a child would). It does not, and must not, flag an
 * `aria-label`, `data-*` attribute or a code comment, because those are not
 * read by a sighted user watching the page - screen-reader-only copy is the
 * accessible-name mechanism this rule is not trying to replace. None of the
 * 50 baseline hits were of that shape (all were JSX children or values a
 * child/placeholder renders), so the walk below is a plain string search:
 * widening it to parse JSX attribute vs. child position is machinery this
 * codebase has no case for yet.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

/** Roots scanned: everywhere a "Loading..." string was found. */
const ROOTS = ['app', 'components'];

/**
 * Metronic template directories - same three `raw-table.inventory.test.ts`
 * excludes, for the same reason: demo shell, never wired to a real feature.
 */
const EXCLUDED_DIRS = [
  'app/(protected)/public-profile',
  'app/(protected)/account',
  'app/(protected)/network',
];

const LOADING_STRING = /Loading\.\.\.|Loading…/;

/** Every `.tsx`/`.ts` under the scanned roots, tests and excluded dirs skipped. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const rel = full.split(path.sep).join('/');
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        if (EXCLUDED_DIRS.includes(rel)) continue;
        walk(full);
      } else if (/\.(tsx?|jsx?)$/.test(entry.name) && !/\.(test|spec)\./.test(entry.name)) {
        out.push(rel);
      }
    }
  };
  for (const root of ROOTS) walk(root);
  return out;
}

describe('No bare "Loading..." / "Loading…" text (M5-02)', () => {
  it('no file outside the demo dirs renders the bare string', () => {
    const offenders = sourceFiles().filter((file) => LOADING_STRING.test(fs.readFileSync(file, 'utf8')));

    expect(offenders, `${offenders.length} file(s) still render a bare Loading string`).toEqual([]);
  });
});
