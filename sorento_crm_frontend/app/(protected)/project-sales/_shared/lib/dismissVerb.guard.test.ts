/**
 * S3-2: the only dismiss verb anywhere in project-sales is "Dismiss with a reason" (R3, R20).
 * Enforced by grep rather than by review, the same shape as `scm/lib/format.guard.test.ts`: a
 * verb drifts one screen at a time, and review catches the first drift and misses the fifth.
 *
 * "Override with a reason" and "Clear with a reason" are the two verbs this guards against -
 * both considered and rejected in favour of one shared verb across every finding, on every
 * review screen. The third rejected string, "Dismiss as false signal", is NOT checked here: it
 * is still live on purpose in `DeliveryScheduleReconciliationList.tsx` (S3-2 reviewer note,
 * 25 Sep 2026) - renaming it is S5's job, not this round's.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

/** The `project-sales/` tree, resolved from this file so the guard does not depend on the cwd. */
const PROJECT_SALES_ROOT = join(import.meta.dirname, '..', '..');

const BANNED = ['Override with a reason', 'Clear with a reason'];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__testsupport__') continue;
      out.push(...sourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry.name)) continue;
    if (/\.test\.tsx?$/.test(entry.name)) continue;
    out.push(full);
  }
  return out;
}

describe('project-sales has one dismiss verb', () => {
  it('finds the project-sales tree it is supposed to be policing', () => {
    // A guard that silently walks an empty directory passes forever and proves nothing.
    const files = sourceFiles(PROJECT_SALES_ROOT);
    expect(files.length).toBeGreaterThan(50);
  });

  it('never says "Override with a reason" or "Clear with a reason"', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(PROJECT_SALES_ROOT)) {
      const rel = relative(PROJECT_SALES_ROOT, file);
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line, i) => {
          for (const phrase of BANNED) {
            if (line.includes(phrase)) offenders.push(`${rel}:${i + 1} - "${phrase}": ${line.trim()}`);
          }
        });
    }

    expect(
      offenders,
      `The only dismiss verb is "Dismiss with a reason" (S3-2):\n${offenders.join('\n')}`,
    ).toEqual([]);
  });
});
