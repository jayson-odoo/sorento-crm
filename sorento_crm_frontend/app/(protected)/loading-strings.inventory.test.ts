/**
 * M5-02 (`PLAN-ui-motion-round2.md` 3.5) - zero non-demo files render the bare
 * string `Loading...` or `Loading…` as visible content. Baseline (measured on
 * this branch before the fix, `git grep -rlE 'Loading\.\.\.|Loading…' app
 * components --include='*.tsx' | grep -v '\.test\.'`): 50 files.
 *
 * Source scan, not a render test, for the same reason
 * `raw-table.inventory.test.ts` is: this is a property of the whole tree.
 *
 * The regex is a plain WHOLE-FILE string search, not a parse of JSX children
 * vs. attributes vs. comments - it would flag an `aria-label`, a `data-*`
 * attribute or a code comment exactly the same as a rendered child, and has
 * done so from the start (an earlier version of this comment claimed the
 * opposite; corrected here against what the code actually does, M5-02 review
 * S4). That is an accepted false-positive risk in trade for staying a plain
 * string search rather than parsing JSX position - none of the baseline hits
 * were in an attribute or a comment, and a future one is a one-line allowlist
 * away rather than a reason to build a parser for it.
 *
 * M5-02 review S4 widened the match beyond `Loading...`/`Loading…` to the
 * BARE word rendered with nothing else - `>Loading<` (a JSX text child that
 * is exactly "Loading", whitespace/newlines around the word tolerated, since
 * Prettier commonly puts a JSX text sibling on its own line after an icon:
 * `<LoaderCircle /> Loading` wraps as `/>\n  Loading\n</>`), `'Loading'`/
 * `"Loading"` (a string literal that is exactly "Loading", which also covers
 * `{'Loading'}`). Still a substring match, still whole-file: `'Loading
 * suppliers'` does not match (more than one word), `loadingMessage` does not
 * match (no quote or `<`/`>` around the word, and no whitespace-only gap
 * either), but `'Loading'` and `>Loading<` do - the same "a raw word with no
 * shape" defect `Loading...` was, just without the ellipsis.
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

const LOADING_STRING = /Loading\.\.\.|Loading…|>\s*Loading\s*<|'Loading'|"Loading"/;

/**
 * `aria-label="Loading"` - a JSX attribute (`aria-label="Loading"`) or the same key in a
 * plain object spread onto one (`'aria-label': 'Loading'`, which `ListPageSkeleton` uses
 * so the same props object can be conditionally spread) - is the sanctioned pattern for
 * an icon-only loading indicator (M5-01 review S5 puts it on
 * `ListPageSkeleton`/`SectionSkeleton`; M5-02 review S4 puts it on every "Load more"
 * spinner that used to show the bare word as its own button text). It is read by
 * assistive tech, never by a sighted user, which is exactly the accessible-name
 * mechanism this rule's own doc comment above says it is not trying to replace - so it
 * is stripped before the scan runs rather than allowlisted file by file, since it is one
 * recurring, correct pattern rather than N one-off exceptions.
 */
const ARIA_LABEL_LOADING = /['"]?aria-label['"]?\s*[:=]\s*(["'])Loading\1/g;

/**
 * Every current false positive, each with a one-line reason - same shape as
 * `raw-table.inventory.test.ts`'s `ALLOWLIST`. Unlike `ARIA_LABEL_LOADING` above (one
 * recurring correct PATTERN), these are one-off: the word "Loading" appearing for a
 * reason that has nothing to do with an async loading state.
 */
const ALLOWLIST: Record<string, string> = {
  'app/(protected)/procurement-management/packing-lists/components/PackingListsList.tsx':
    "column header for the `loading_date` field (a container's physical loading date) - not an async loading state",
};

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
    const offenders = sourceFiles()
      .filter((file) => !(file in ALLOWLIST))
      .filter((file) =>
        LOADING_STRING.test(fs.readFileSync(file, 'utf8').replace(ARIA_LABEL_LOADING, '')),
      );

    expect(offenders, `${offenders.length} file(s) still render a bare Loading string`).toEqual([]);
  });

  it('every allowlist entry is still a real, still-current false positive', () => {
    for (const [file, reason] of Object.entries(ALLOWLIST)) {
      expect(fs.existsSync(file), `${file} no longer exists - drop it (${reason})`).toBe(true);
      const withoutAriaLabels = fs.readFileSync(file, 'utf8').replace(ARIA_LABEL_LOADING, '');
      expect(
        LOADING_STRING.test(withoutAriaLabels),
        `${file} no longer matches - drop it from the allowlist (${reason})`,
      ).toBe(true);
    }
  });
});
