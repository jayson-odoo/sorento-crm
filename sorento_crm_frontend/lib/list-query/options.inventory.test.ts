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
 *
 * **This walk is the hook-side FLOOR, not the whole rule.** It reads queryKeys,
 * so a list hook that keys on a bare `filters` or `query` identifier names
 * nothing any of the three triggers can see, and widening the regex to catch
 * those two words flags the report and detail queries that legitimately key on
 * the same words. The grid-side CEILING is the third walk at the bottom of this
 * file: it starts from `manualPagination: true`, which is the code declaring
 * that the server owns the page, and that is the check a new list actually has
 * to get past. A hook missed here is caught there the moment its grid renders.
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
 * Trigger 3: a `queryKey` that carries a `params` (or `listParams`) OBJECT.
 *
 * `salesOrdersKey(projectId, params)`, `orderInquiryRowsKey(projectId, params)`
 * and `awaitingAcceptanceKey(params)` name no list and use no list-key builder,
 * so triggers 1 and 2 both walked past them while all three paged a grid. What
 * they have in common is the bag of page/sort/filter state in the key, which is
 * the thing `keepPreviousData` exists for.
 *
 * Deliberately `params`, not any identifier: a detail or report query keys on
 * its id or its own named arguments (`coverageKey(projectId)`,
 * `orderSummaryKey(orderId)`), so it stays unflagged.
 */
const LIST_KEY_PARAMS_RE = /\b(params|listParams)\b/;

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
  // The MCP tools catalogue reads all 500 rows in one go, so its key never
  // changes for a page - only for the Active-only toggle. Keeping the previous
  // answer across THAT change shows inactive rows to a reader who just asked
  // for active ones, which reads as a toggle that does not work.
  'app/(protected)/system-management/mcp-tools/hooks/useMcpAdmin.ts':
    'unpaginated 500-row catalogue whose only key change is a filter toggle',
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
      if (
        !LIST_KEY_LITERAL_RE.test(keyVal) &&
        !LIST_KEY_BUILDER_RE.test(keyVal) &&
        !LIST_KEY_PARAMS_RE.test(keyVal)
      )
        continue;
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

  it('trigger 3 reads a params BAG, and leaves a named-argument key alone', () => {
    // The three the first two triggers walked past: no "list" in the builder
    // name, no page/sort word in the key, but a whole bag of list state in it.
    expect(LIST_KEY_PARAMS_RE.test("salesOrdersKey(projectId ?? '', params)")).toBe(true);
    expect(LIST_KEY_PARAMS_RE.test("orderInquiryRowsKey(projectId ?? '', params)")).toBe(true);
    expect(LIST_KEY_PARAMS_RE.test('awaitingAcceptanceKey(params)')).toBe(true);
    expect(LIST_KEY_PARAMS_RE.test('[PARTIES_KEY, listParams]')).toBe(true);

    // The reorder screens' report queries and the conversations inbox key on
    // named arguments, not a params bag, and must stay unflagged - keeping the
    // previous answer on a report is a decision those hooks make for
    // themselves, and a detail key must never answer from the last record.
    expect(LIST_KEY_PARAMS_RE.test('coverageKey(q)')).toBe(false);
    expect(LIST_KEY_PARAMS_RE.test('orderSummaryKey(q)')).toBe(false);
    expect(LIST_KEY_PARAMS_RE.test('planExceptionsKey(q)')).toBe(false);
    expect(LIST_KEY_PARAMS_RE.test('conversationsInboxKey(tab, q)')).toBe(false);
    expect(LIST_KEY_PARAMS_RE.test("['product', id]")).toBe(false);
    expect(LIST_KEY_PARAMS_RE.test('taskHistoryKey(projectId, taskId)')).toBe(false);
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

/**
 * M4-02 - every grid fed by a `LIST_QUERY_OPTIONS` hook forwards
 * `isPlaceholderData` to `DataGrid`.
 *
 * The spread alone keeps the previous page's ROWS in the query cache; it does
 * not dim them. TanStack reports a placeholder window as
 * `isLoading: false, isFetching: true, isPlaceholderData: true`, so
 * `DataGridTableBody`'s `isLoading && rows.length > 0` clause is false
 * throughout it and the body never dims. The flag has to travel from the list
 * query to the grid, at the call site, one list at a time - which is exactly
 * the kind of per-file wiring that rots, so it is inventoried here.
 *
 * The walk:
 *
 *  1. a file that spreads `...LIST_QUERY_OPTIONS` OWNS the top-level
 *     declaration the spread sits in (`useOrders`, or the component itself
 *     when the `useQuery` is inline);
 *  2. a CONSUMER is any file that renders a `<DataGrid>` and either imports one
 *     of those owner names or owns a spread of its own;
 *  3. every `<DataGrid>` opening tag in a consumer must pass
 *     `isPlaceholderData`.
 *
 * Comments are blanked before step 1 for the same reason as above, and because
 * `options.ts`'s own docstring shows the spread - reading a doc example as a
 * hook is how a phantom owner gets into the inventory.
 */

/**
 * A grid a consumer renders that is NOT fed by the list query, so forwarding
 * the flag would dim rows that are not placeholders. Each entry says why.
 */
const GRID_ALLOWLIST: Record<string, string> = {};

/** Top-level `function`/`const`/`let`/`class` declarations, with the span each covers. */
function topLevelDeclSpans(text: string): { name: string; start: number; end: number }[] {
  const re = /^(?:export\s+)?(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z0-9_$]+)/gm;
  const marks: { name: string; start: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) marks.push({ name: m[1], start: m.index });
  return marks.map((mark, i) => ({
    name: mark.name,
    start: mark.start,
    end: i + 1 < marks.length ? marks[i + 1].start : text.length,
  }));
}

/** Every `<DataGrid ...>` opening tag (not `<DataGridTable>` and friends), brace-aware. */
function findDataGridTags(text: string): { text: string; line: number }[] {
  const tags: { text: string; line: number }[] = [];
  const re = /<DataGrid(?![A-Za-z])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    let i = m.index;
    let depth = 0;
    let inStr: string | null = null;
    for (; i < text.length; i++) {
      const c = text[i];
      if (inStr) {
        if (c === '\\') { i++; continue; }
        if (c === inStr) inStr = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') { inStr = c; continue; }
      if (c === '{') depth++;
      else if (c === '}') depth--;
      else if (c === '>' && depth === 0) break;
    }
    tags.push({ text: text.slice(m.index, i + 1), line: text.slice(0, m.index).split('\n').length });
  }
  return tags;
}

function findForwardingMisses(): string[] {
  const files = SCAN_DIRS.filter((d) => fs.existsSync(path.join(ROOT, d))).flatMap((d) =>
    walk(path.join(ROOT, d), []),
  );

  // 1. owner declarations, per file.
  const owners = new Map<string, Set<string>>();
  for (const file of files) {
    const raw = fs.readFileSync(file, 'utf8');
    if (!raw.includes('LIST_QUERY_OPTIONS')) continue;
    const text = stripComments(raw);
    if (!text.includes('...LIST_QUERY_OPTIONS')) continue;
    const spans = topLevelDeclSpans(text);
    const names = new Set<string>();
    const re = /\.\.\.LIST_QUERY_OPTIONS/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text))) {
      const owning = spans.filter((s) => s.start <= m!.index && m!.index < s.end).pop();
      names.add(owning ? owning.name : '<module>');
    }
    owners.set(path.relative(ROOT, file), names);
  }

  const ownerNames = new Set<string>();
  for (const names of owners.values()) for (const n of names) if (!n.startsWith('<')) ownerNames.add(n);

  // 2 + 3. consumers, and the tags inside them.
  const misses: string[] = [];
  for (const file of files) {
    const rel = path.relative(ROOT, file);
    const raw = fs.readFileSync(file, 'utf8');
    if (!/<DataGrid(?![A-Za-z])/.test(raw)) continue;

    const fed = new Set<string>(owners.get(rel) ?? []);
    const importRe = /import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['"][^'"]+['"]/g;
    let m: RegExpExecArray | null;
    while ((m = importRe.exec(raw))) {
      for (const part of m[1].split(',')) {
        const name = part.trim().split(/\s+as\s+/)[0].trim();
        if (ownerNames.has(name)) fed.add(name);
      }
    }
    if (!fed.size) continue;

    for (const tag of findDataGridTags(raw)) {
      const key = `${rel}:${tag.line}`;
      if (GRID_ALLOWLIST[key] || GRID_ALLOWLIST[rel]) continue;
      if (/\bisPlaceholderData\b/.test(tag.text)) continue;
      misses.push(`${key} :: fed by ${[...fed].join(', ')}`);
    }
  }
  return misses;
}

describe('every grid fed by a LIST_QUERY_OPTIONS hook forwards isPlaceholderData (M4-02)', () => {
  it('has no misses', () => {
    const misses = findForwardingMisses();
    if (misses.length) {
      console.error(
        `${misses.length} <DataGrid> call(s) not forwarding isPlaceholderData:\n${misses.join('\n')}`,
      );
    }
    expect(misses).toEqual([]);
  });

  it('reads the tag, not the file - a sibling DataGridTable is not a DataGrid', () => {
    const tags = findDataGridTags(
      '<DataGridTable />\n<DataGrid table={t} isLoading={x}>\n<DataGridPagination />',
    );

    expect(tags).toHaveLength(1);
    expect(tags[0].text).toContain('isLoading={x}');
  });

  it('does not let a `>` inside an attribute end the tag early', () => {
    const tags = findDataGridTags('<DataGrid rowHref={(r) => `/x/${r.id}`} isPlaceholderData={p}>');

    expect(tags[0].text).toContain('isPlaceholderData={p}');
  });
});

/**
 * M4-01b (grid side) - every grid that pages on the SERVER forwards
 * `isPlaceholderData`, whatever route its rows arrived by.
 *
 * The M4-02 walk above starts from the hooks and follows imports, so it only
 * ever reaches a grid whose owner name is imported into the same file. Three
 * shapes escape it and all three ship today: a grid that takes its rows as
 * PROPS from a parent that owns the hook (`LeadsGrid`, `ProjectsGrid`), a page
 * that declares its `useQuery` inline without the spread, and a component whose
 * list hook lives two files away. This walk starts from the honest population
 * instead: a file that sets `manualPagination: true` has told TanStack the
 * server owns the page, so every `<DataGrid>` in it must be able to dim while
 * the next page is in flight.
 */

/**
 * A server-paged grid that must NOT forward the flag, with the reason. An entry
 * here is a claim that the grid's rows do not come from a react-query list
 * query, so there is no placeholder window for it to report.
 */
const MANUAL_PAGINATION_ALLOWLIST: Record<string, string> = {
  'app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestsList.tsx':
    'fetches in a useEffect, not react-query, so no query reports isPlaceholderData',
  'components/spec-table/SpecTable.tsx':
    'manualPagination with pageCount 1 turns paging OFF on prop-fed rows; there is no page to turn',
  'components/spec-proposals/SpecProposalReview.tsx':
    'manualPagination with pageCount 1 turns paging OFF on prop-fed rows; there is no page to turn',
};

function findManualPaginationMisses(): string[] {
  const files = ['app', 'components']
    .filter((d) => fs.existsSync(path.join(ROOT, d)))
    .flatMap((d) => walk(path.join(ROOT, d), []));

  const misses: string[] = [];
  for (const file of files) {
    const rel = path.relative(ROOT, file);
    if (MANUAL_PAGINATION_ALLOWLIST[rel]) continue;
    const raw = fs.readFileSync(file, 'utf8');
    if (!raw.includes('manualPagination: true')) continue;
    if (!/<DataGrid(?![A-Za-z])/.test(raw)) continue;

    for (const tag of findDataGridTags(raw)) {
      if (/\bisPlaceholderData\b/.test(tag.text)) continue;
      misses.push(`${rel}:${tag.line} :: manualPagination grid, no isPlaceholderData`);
    }
  }
  return misses;
}

describe('every server-paged grid forwards isPlaceholderData (M4-01b)', () => {
  it('has no misses', () => {
    const misses = findManualPaginationMisses();
    if (misses.length) {
      console.error(
        `${misses.length} manualPagination <DataGrid> call(s) not forwarding isPlaceholderData:\n${misses.join('\n')}`,
      );
    }
    expect(misses).toEqual([]);
  });

  it('every allowlist entry still exists and still sets manualPagination', () => {
    for (const rel of Object.keys(MANUAL_PAGINATION_ALLOWLIST)) {
      const full = path.join(ROOT, rel);

      expect(fs.existsSync(full), `${rel} is allowlisted but gone`).toBe(true);
      expect(fs.readFileSync(full, 'utf8')).toContain('manualPagination: true');
    }
  });

  it('the two spec grids are allowlisted on a claim the code still makes', () => {
    // `pageCount: 1` is the whole reason they are here: manualPagination is how
    // they turn client paging OFF on a handful of prop-fed rows. Drop that and
    // they are a server-paged grid like any other, and this test says so.
    for (const rel of [
      'components/spec-table/SpecTable.tsx',
      'components/spec-proposals/SpecProposalReview.tsx',
    ]) {
      expect(fs.readFileSync(path.join(ROOT, rel), 'utf8')).toContain('pageCount: 1');
    }
  });
});
