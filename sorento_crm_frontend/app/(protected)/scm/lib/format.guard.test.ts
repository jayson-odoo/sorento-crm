/**
 * One money format on the SCM screens, enforced by grep rather than by review.
 *
 * The bug this guards against is not a typo, it is a habit: a figure gets rendered where
 * it is needed with a local `Intl.NumberFormat` and a literal "RM", and the screen ends up
 * writing money three ways at once - `RM 105 MYR` in one popover, `MYR 105.00` in another,
 * `1,980` bare in a third. Review catches the first one and misses the fifth, so the rule
 * lives here: every formatter is defined in `lib/format.ts`, and nothing else in the tree
 * builds its own.
 *
 * A new formatting need is answered by adding a helper to `format.ts`, never by inlining
 * one here.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

// Vitest runs with the frontend package as its root, so the tree is found from there
// rather than from `import.meta.url` (which is not a file URL under the jsdom environment).
const SCM_ROOT = join(process.cwd(), 'app', '(protected)', 'scm');

/** The one file allowed to hold a formatter definition. */
const FORMATTER_HOME = 'lib/format.ts';

/** Locale-pinned formatting, which is what a hand-rolled figure looks like. */
const BANNED: { pattern: RegExp; why: string }[] = [
  { pattern: /new Intl\.NumberFormat/, why: 'a formatter defined outside lib/format.ts' },
  { pattern: /toLocaleString\('en-MY'/, why: "a hand-rolled 'en-MY' figure" },
];

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
    // Tests may assert on the exact bytes a formatter produces, including this file.
    if (/\.test\.(ts|tsx)$/.test(entry.name)) continue;
    out.push(full);
  }
  return out;
}

describe('money and number formatting live in lib/format.ts', () => {
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
      const text = readFileSync(file, 'utf8');
      for (const { pattern, why } of BANNED) {
        text.split('\n').forEach((line, i) => {
          if (pattern.test(line)) offenders.push(`${rel}:${i + 1} - ${why}: ${line.trim()}`);
        });
      }
    }

    expect(
      offenders,
      `Use a helper from ${FORMATTER_HOME} (fmtInt / fmtMoney / fmtMoneyIn / fmtSupplierCost / ` +
        'fmtDecimal / fmtTrimmedDecimal), or add one there:\n' +
        offenders.join('\n'),
    ).toEqual([]);
  });
});
