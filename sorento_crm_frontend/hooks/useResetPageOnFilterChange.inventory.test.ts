/**
 * Guardrail: no list resets its own page from a bare effect.
 *
 * A `useEffect` that sets `pageIndex: 0` runs once on mount, which is exactly
 * when `useListStateFromUrl` has just restored `page=` from the URL. Every list
 * that carried one silently threw its restored page away and opened on page 1
 * (M5 run 2 evidence, finding 3). Nineteen lists carried one; two more carried a
 * hand-rolled "have I mounted" ref, which StrictMode's double invoke defeats.
 *
 * `useResetPageOnFilterChange` is the one place that knows the difference
 * between mounting and changing. This test is what stops the twentieth copy.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(__dirname, '..');
const APP = path.join(ROOT, 'app');

function tsxFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue;
      tsxFiles(full, out);
    } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Effect bodies (`useEffect(() => { ... }, [...])`) that write `pageIndex: 0`.
 * Deliberately textual: the point is to catch the SHAPE before it is written,
 * and every copy in the codebase is written this same way.
 */
function pageResettingEffects(source: string): string[] {
  const lines = source.split('\n');
  const found: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    if (!/(React\.)?useEffect\(\(\) => \{/.test(lines[i])) continue;
    const block: string[] = [];
    let j = i;
    for (; j < lines.length; j += 1) {
      block.push(lines[j]);
      if (j > i && /^\s*\}, \[/.test(lines[j])) break;
    }
    const body = block.join('\n');
    if (body.includes('pageIndex: 0') && body.includes('setPagination')) {
      found.push(`${i + 1}`);
    }
    i = j;
  }
  return found;
}

describe('page resets go through the shared hook', () => {
  it('no list that reads its state from the URL resets its page from a bare effect', () => {
    const offenders: string[] = [];

    for (const file of tsxFiles(APP)) {
      const source = fs.readFileSync(file, 'utf8');
      if (!source.includes('useListStateFromUrl')) continue;
      const hits = pageResettingEffects(source);
      if (hits.length > 0) {
        offenders.push(`${path.relative(ROOT, file)}:${hits.join(',')}`);
      }
    }

    expect(offenders).toEqual([]);
  });

  it('the hand-rolled "have I mounted yet" refs are gone', () => {
    const offenders: string[] = [];

    for (const file of tsxFiles(APP)) {
      const source = fs.readFileSync(file, 'utf8');
      if (!source.includes('useListStateFromUrl')) continue;
      if (/filtersMounted|searchMounted/.test(source)) {
        offenders.push(path.relative(ROOT, file));
      }
    }

    expect(offenders).toEqual([]);
  });
});
