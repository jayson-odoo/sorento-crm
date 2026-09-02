/**
 * M4-01 - every paginated list hook spreads `LIST_QUERY_OPTIONS`.
 *
 * Walks every non-test `.ts`/`.tsx` file under `app/`, `components/`, `hooks/`
 * and `services/`, extracts each `useQuery({...})` call by brace matching, and
 * asserts the call spreads `...LIST_QUERY_OPTIONS` whenever its `queryKey`
 * looks like a list key. Two triggers, because list keys are written two ways:
 *
 *  1. an INLINE key whose text names page, size, sort, filter or search state
 *     (`[key, params.page, sorting]`), and
 *  2. a key built through a NAMED builder (`ordersListQueryKey(params)`,
 *     `projectsListKey(params)`, `[...wfKeys.definitions, params]`). The first
 *     pass of this test had only trigger 1, so all 33 builder-keyed lists -
 *     Products, Orders, Contacts, Users, Suppliers and the rest - passed it
 *     while keeping none of their rows. Trigger 2 is what makes this a
 *     guardrail rather than a regex that agrees with itself.
 *
 * A DETAIL query (`productKey(id)`) names no list and is not flagged; the
 * builder trigger is deliberately narrow enough to leave those alone.
 *
 * Comments are blanked before the scan: an apostrophe inside a comment
 * ("the row's page") otherwise opens a string in the brace matcher and every
 * `useQuery` after it in that file is silently skipped.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(__dirname, '../..');
const SCAN_DIRS = ['app', 'components', 'hooks', 'services'];

/** Trigger 1: an inline `queryKey` naming page, size, sort, filter or search state. */
const LIST_KEY_LITERAL_RE = /page|pageIndex|pageSize|sorting|limit|columnFilters|sortBy|sortField/;

/**
 * Trigger 2: a `queryKey` built by a named list-key builder. Covers
 * `xxxListQueryKey(...)`, `xxxListKey(...)`, `poWorklistKey(...)` (lower-case
 * `list`) and the workflow-forms `wfKeys.definitions` / `wfKeys.submissions`
 * namespaces.
 */
const LIST_KEY_BUILDER_RE = /[Ll]ist(Query)?Key\s*\(|Keys\.(definitions|submissions)/;

/**
 * The one query that names a list key and must NOT keep previous data.
 *
 * `useListPager` re-runs the LIST query in the background from a detail page,
 * purely to find the current record's neighbours - it renders no rows. With
 * `keepPreviousData` it would answer from the previous page's items while a
 * new page loads, so prev/next would step through neighbours the user is not
 * on. It is the absence of rows on screen that makes this different from every
 * other entry here.
 */
const ALLOWLIST: Record<string, string> = {
  'hooks/useListPager.ts': 'background neighbour lookup, renders no rows',
};

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

/**
 * `//` and block comments replaced by spaces, newlines kept so offsets and line
 * counts still line up. Quotes inside a comment can then no longer desync the
 * string tracking the brace matchers below rely on.
 */
function stripComments(text: string): string {
  let out = '';
  let inStr: string | null = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      out += c;
      if (c === '\\') { out += text[i + 1] ?? ''; i++; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    // An escape outside a string is a regex literal's `\/`; taking it whole
    // stops `/https?:\/\//` from reading as a line comment.
    if (c === '\\') { out += c + (text[i + 1] ?? ''); i++; continue; }
    if (c === '"' || c === "'" || c === '`') { inStr = c; out += c; continue; }
    if (c === '/' && text[i + 1] === '/') {
      while (i < text.length && text[i] !== '\n') { out += ' '; i++; }
      out += '\n';
      continue;
    }
    if (c === '/' && text[i + 1] === '*') {
      out += '  ';
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) {
        out += text[i] === '\n' ? '\n' : ' ';
        i++;
      }
      out += '  ';
      i++;
      continue;
    }
    out += c;
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

/** Every `useQuery(...)` call's argument text (between the outer parens), with its line number. */
function findUseQueryBlocks(text: string): { block: string; line: number }[] {
  const blocks: { block: string; line: number }[] = [];
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
    blocks.push({
      block: text.slice(i + 1, end - 1),
      line: text.slice(0, m.index).split('\n').length,
    });
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
    const rel = path.relative(ROOT, file);
    if (ALLOWLIST[rel]) continue;
    const raw = fs.readFileSync(file, 'utf8');
    if (!raw.includes('useQuery')) continue;
    const text = stripComments(raw);
    for (const { block, line } of findUseQueryBlocks(text)) {
      const keyVal = extractQueryKeyValue(block);
      if (!keyVal) continue;
      if (!LIST_KEY_LITERAL_RE.test(keyVal) && !LIST_KEY_BUILDER_RE.test(keyVal)) continue;
      if (block.includes('...LIST_QUERY_OPTIONS')) continue;
      misses.push(`${rel}:${line} :: queryKey ${keyVal.replace(/\s+/g, ' ').slice(0, 80)}`);
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

  it('leaves a detail query alone - only list keys are flagged', () => {
    expect(LIST_KEY_BUILDER_RE.test('productKey(id)')).toBe(false);
    expect(LIST_KEY_BUILDER_RE.test("['product', id]")).toBe(false);
    expect(LIST_KEY_BUILDER_RE.test('productsListQueryKey(params)')).toBe(true);
    expect(LIST_KEY_BUILDER_RE.test('poWorklistKey(q)')).toBe(true);
    expect(LIST_KEY_BUILDER_RE.test('[...wfKeys.definitions, params]')).toBe(true);
  });

  it('blanks comments before matching, so an apostrophe in one cannot hide a hook', () => {
    const src = [
      "// the row's page",
      "useQuery({ queryKey: ordersListQueryKey(params), queryFn: fn });",
    ].join('\n');
    const blocks = findUseQueryBlocks(stripComments(src));

    expect(blocks).toHaveLength(1);
    expect(extractQueryKeyValue(blocks[0].block)).toBe('ordersListQueryKey(params)');
  });
});
