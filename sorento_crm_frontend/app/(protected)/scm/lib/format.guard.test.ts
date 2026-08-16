/**
 * One place decides how a number is written on the SCM screens, enforced by grep rather
 * than by review.
 *
 * The bug this guards against is not a typo, it is a habit: a figure gets formatted where
 * it is needed, with a local `Intl.NumberFormat`, a `toFixed`, or a bare `toLocaleString`,
 * and the screens end up writing money and quantities several ways at once - `RM 105 MYR`
 * in one popover, `MYR 105.00` in another, `8.00` with no currency at all in a third, and
 * `1980` unseparated in a fourth. Review catches the first one and misses the fifth.
 *
 * `toFixed` earns its place on this list twice over: it drops thousands separators AND it
 * is how a "2 decimal places" price ends up rendered without ever naming its currency.
 *
 * A new formatting need is answered by adding a helper to `lib/format.ts`, never by
 * inlining one at the call site. Genuinely non-display arithmetic goes in ALLOWED below,
 * with a reason.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

/** The `scm/` tree, resolved from this file so the guard does not depend on the cwd. */
const SCM_ROOT = join(import.meta.dirname, '..');

/** The one file allowed to hold a formatter definition. */
const FORMATTER_HOME = 'lib/format.ts';

/** Formatting done by hand, which is what a drifting figure looks like. */
const BANNED: { pattern: RegExp; why: string }[] = [
  { pattern: /new Intl\.NumberFormat/, why: 'a formatter defined outside lib/format.ts' },
  { pattern: /\.toLocaleString\(/, why: 'a hand-rolled number/date string' },
  { pattern: /\.toFixed\(/, why: 'a hand-rolled decimal (no separators, no currency)' },
];

/**
 * `<relative path>:<line>` for the few call sites that are NOT a number being displayed.
 * Each one states why, because an unexplained entry here is how the rule quietly rots.
 */
const ALLOWED: Record<string, string> = {
  // Rounds a score to 4 places as a NUMBER (wrapped in Number()) for a mock payload -
  // arithmetic, never rendered as this string.
  'reorder/lib/reorderCashMock.ts:219': 'numeric rounding, not display',
};

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__snapshots__') continue;
      out.push(...sourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry.name)) continue;
    // A test may assert on the exact bytes a formatter produces, and this file names the
    // banned calls itself.
    if (/\.test\.(ts|tsx)$/.test(entry.name)) continue;
    out.push(full);
  }
  return out;
}

describe('number and money formatting lives in lib/format.ts', () => {
  it('finds the SCM tree it is supposed to be policing', () => {
    // A guard that silently walks an empty directory passes forever and proves nothing.
    const files = sourceFiles(SCM_ROOT);
    expect(files.length).toBeGreaterThan(50);
    expect(files.map((f) => relative(SCM_ROOT, f))).toContain(FORMATTER_HOME);
  });

  it('has no hand-rolled formatter anywhere else in the tree', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SCM_ROOT)) {
      const rel = relative(SCM_ROOT, file);
      if (rel === FORMATTER_HOME) continue;
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line, i) => {
          if (ALLOWED[`${rel}:${i + 1}`]) return;
          for (const { pattern, why } of BANNED) {
            if (pattern.test(line)) offenders.push(`${rel}:${i + 1} - ${why}: ${line.trim()}`);
          }
        });
    }

    expect(
      offenders,
      `Use a helper from ${FORMATTER_HOME} (fmtInt / fmtMoney / fmtMoneyIn / fmtSupplierCost / ` +
        'fmtDecimal / fmtTrimmedDecimal / fmtDate / fmtDateTime), add one there, or list a ' +
        'genuinely non-display call in ALLOWED with its reason:\n' +
        offenders.join('\n'),
    ).toEqual([]);
  });

  it('keeps every allow-list entry pointing at a real banned call', () => {
    // An entry left behind after the line moved would silence a future offender at that
    // line number instead.
    for (const [key, why] of Object.entries(ALLOWED)) {
      const [rel, lineNo] = key.split(':');
      const line = readFileSync(join(SCM_ROOT, rel), 'utf8').split('\n')[Number(lineNo) - 1];
      expect(line, `${key} (${why}) no longer exists`).toBeDefined();
      expect(
        BANNED.some((b) => b.pattern.test(line)),
        `${key} (${why}) no longer contains a banned call: ${line?.trim()}`,
      ).toBe(true);
    }
  });
});
