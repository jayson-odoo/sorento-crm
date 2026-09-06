/**
 * Guardrail: no grid builds its `data` array inside its own render.
 *
 * TanStack reads `data` by IDENTITY, and `autoResetPageIndex` defaults to on
 * whenever `manualPagination` is off. A grid written `data: [...rows]` therefore
 * loops forever: render, new array, auto page reset, `useReactTable`'s own state
 * setter, render, new array. Nothing is thrown and nothing is logged - the tab
 * just pegs a core.
 *
 * That is what Settings > Notifications did (M5 run 2 evidence, finding 1). It
 * was reported as "clicking a checkbox hangs the tab", but measured in the
 * browser the page was already at ~400 renders and ~6,000 DOM mutations a second
 * on load, with no interaction at all and a clean console. Hoisting the array to
 * a module constant took it to zero.
 *
 * A literal is the shape that makes it unconditional, so a literal is what this
 * bans. Hoist it to a module constant when it never changes, `useMemo` it when
 * it does.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(__dirname, '..', '..');

function gridFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue;
      gridFiles(full, out);
    } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
      out.push(full);
    }
  }
  return out;
}

describe('useReactTable data identity', () => {
  it('no grid passes a freshly built array as its `data`', () => {
    const offenders: string[] = [];

    for (const dir of [path.join(ROOT, 'app'), path.join(ROOT, 'components')]) {
      for (const file of gridFiles(dir)) {
        const source = fs.readFileSync(file, 'utf8');
        if (!source.includes('useReactTable')) continue;
        const lines = source.split('\n');
        lines.forEach((line, index) => {
          if (/^\s*data:\s*\[/.test(line)) {
            offenders.push(`${path.relative(ROOT, file)}:${index + 1} ${line.trim()}`);
          }
        });
      }
    }

    expect(offenders).toEqual([]);
  });
});
