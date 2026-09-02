/**
 * M4-01 - every paginated list hook spreads `LIST_QUERY_OPTIONS`.
 *
 * Walks every non-test `.ts`/`.tsx` file under `app/`, `hooks/` and
 * `services/`, extracts each `useQuery({...})` call by brace matching, and
 * for every call whose `queryKey` value mentions page, size, sort, filter or
 * search state asserts the call spreads `...LIST_QUERY_OPTIONS`.
 *
 * Baseline (origin/main e1adad4d2, 2 Sep 2026): all 66 matching calls
 * missed it (a handful already carried their own `placeholderData`, just
 * never through this constant). This is the guardrail that keeps the count
 * at zero.
 *
 * A `queryKey` built through a named function (`ordersListQueryKey(params)`)
 * carries no literal page/sort/filter word, so it will not be flagged here
 * even when it clearly is a list key - the two named in the plan
 * (`useProducts`, `useOrders`) and the ones with a plain `placeholderData`
 * literal are covered by hand, not by this regex. This test is the
 * MECHANICAL floor, not the whole of M4-01.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(__dirname, '../..');
const SCAN_DIRS = ['app', 'hooks', 'services'];
const LIST_KEY_RE = /page|pageIndex|pageSize|sorting|limit|columnFilters|sortBy|sortField/;

function walk(dir: string, out: string[]): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue;
      walk(full, out);
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec)\./.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

/** Balances the bracket at `start` (one of `(`, `{`, `[`), returns the index AFTER its match. */
function matchBalanced(text: string, start: number): number {
  const opener = text[start];
  const closer = ({ '(': ')', '{': '}', '[': ']' } as Record<string, string>)[opener];
  let depth = 0;
  let inStr: string | null = null;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { inStr = c; continue; }
    if (c === opener) depth++;
    else if (c === closer) {
      depth--;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}

/** The `<...>` generic on `useQuery<Foo<Bar>>(`, angle-bracket balanced. Returns index after the closing `>`. */
function matchGeneric(text: string, ltIndex: number): number {
  let depth = 0;
  for (let i = ltIndex; i < text.length; i++) {
    const c = text[i];
    if (c === '<') depth++;
    else if (c === '>') {
      depth--;
      if (depth === 0) return i + 1;
    } else if (c === ';' || c === '{') {
      return -1; // not a generic after all
    }
  }
  return -1;
}

/** Every `useQuery(...)` call's argument text (between the outer parens). */
function findUseQueryBlocks(text: string): string[] {
  const blocks: string[] = [];
  const re = /\buseQuery\b/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    let i = m.index + m[0].length;
    while (/\s/.test(text[i])) i++;
    if (text[i] === '<') {
      const after = matchGeneric(text, i);
      if (after === -1) continue;
      i = after;
      while (/\s/.test(text[i])) i++;
    }
    if (text[i] !== '(') continue;
    const end = matchBalanced(text, i);
    if (end === -1) continue;
    blocks.push(text.slice(i + 1, end - 1));
    re.lastIndex = end;
  }
  return blocks;
}

/** The `queryKey:` property's value text, top-level-comma to top-level-comma. */
function extractQueryKeyValue(block: string): string | null {
  const m = /queryKey\s*:/.exec(block);
  if (!m) return null;
  let i = m.index + m[0].length;
  while (/\s/.test(block[i])) i++;
  const start = i;
  let depth = 0;
  let inStr: string | null = null;
  for (; i < block.length; i++) {
    const c = block[i];
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { inStr = c; continue; }
    if (c === '(' || c === '{' || c === '[') depth++;
    else if (c === ')' || c === '}' || c === ']') {
      if (depth === 0) break;
      depth--;
    } else if (c === ',' && depth === 0) {
      break;
    }
  }
  return block.slice(start, i);
}

function findMisses(): string[] {
  const files = SCAN_DIRS.filter((d) => fs.existsSync(path.join(ROOT, d))).flatMap((d) =>
    walk(path.join(ROOT, d), []),
  );

  const misses: string[] = [];
  for (const file of files) {
    const text = fs.readFileSync(file, 'utf8');
    if (!text.includes('useQuery')) continue;
    for (const block of findUseQueryBlocks(text)) {
      const keyVal = extractQueryKeyValue(block);
      if (!keyVal || !LIST_KEY_RE.test(keyVal)) continue;
      if (block.includes('...LIST_QUERY_OPTIONS')) continue;
      misses.push(`${path.relative(ROOT, file)} :: queryKey ${keyVal.replace(/\s+/g, ' ').slice(0, 80)}`);
    }
  }
  return misses;
}

describe('every paginated list hook spreads LIST_QUERY_OPTIONS (M4-01)', () => {
  it('has no misses', () => {
    const misses = findMisses();
    if (misses.length) {
      console.error(`${misses.length} useQuery call(s) missing ...LIST_QUERY_OPTIONS:\n${misses.join('\n')}`);
    }
    expect(misses).toEqual([]);
  });
});
