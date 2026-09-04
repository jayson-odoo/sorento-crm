/**
 * S7-04 pinned ten by name; M5-01 (`PLAN-ui-motion-round2.md` 3.5) widens that
 * to a walk: every route segment under `app/(protected)` whose directory (or
 * its own `components/` subdir, one level) renders a `<DataGrid` needs a
 * `loading.tsx`, or Next.js holds the LAST page's rows on screen while the
 * next segment's chunk and first page load - the exact gap this slice closes.
 *
 * Source scan, not a render test, for the same reason
 * `raw-table.inventory.test.ts` is: what it asserts is a property of the
 * whole tree, and a render test can only speak for the one page it mounted.
 * The render half below (kept from S7-04) still proves each FOUND loading.tsx
 * actually renders the shared skeleton, content-only, no shell of its own.
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const PROTECTED_ROOT = path.join(process.cwd(), 'app', '(protected)');

/**
 * Metronic template directories - the demo shell this app was built on top
 * of, never wired to a real feature or a permission - excluded the same way
 * `raw-table.inventory.test.ts` excludes them.
 */
const EXCLUDED_DIRS = [
  'app/(protected)/public-profile',
  'app/(protected)/account',
  'app/(protected)/network',
];

/** A JSX open tag for the `DataGrid` component itself, not a sibling like `DataGridPagination`. */
const RENDERS_DATA_GRID = /<DataGrid(?![A-Za-z])/;
const IS_TEST_FILE = /\.(test|spec)\./;

/** Every `.tsx` directly inside `dir`, tests excluded - not recursive. */
function tsxFilesIn(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.tsx') && !IS_TEST_FILE.test(entry.name))
    .map((entry) => path.join(dir, entry.name));
}

/** Every directory under `root` that directly contains a `page.tsx`. */
function pageDirs(root: string): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    const rel = path.relative(process.cwd(), dir).split(path.sep).join('/');
    if (EXCLUDED_DIRS.includes(rel)) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    if (entries.some((entry) => entry.isFile() && entry.name === 'page.tsx')) {
      out.push(dir);
    }
    for (const entry of entries) {
      if (entry.isDirectory() && entry.name !== 'node_modules') {
        walk(path.join(dir, entry.name));
      }
    }
  };
  walk(root);
  return out;
}

/** True when the segment's own files, or its `components/` subdir (one level), render a `<DataGrid`. */
function segmentRendersDataGrid(dir: string): boolean {
  const candidates = [...tsxFilesIn(dir), ...tsxFilesIn(path.join(dir, 'components'))];
  return candidates.some((file) => RENDERS_DATA_GRID.test(fs.readFileSync(file, 'utf8')));
}

const listSegments = pageDirs(PROTECTED_ROOT).filter(segmentRendersDataGrid);
const missingLoading = listSegments.filter((dir) => !fs.existsSync(path.join(dir, 'loading.tsx')));

describe('every DataGrid list segment has a loading.tsx (M5-01)', () => {
  it('no segment that renders a DataGrid is missing its loading.tsx', () => {
    const missingNames = missingLoading
      .map((dir) => path.relative(PROTECTED_ROOT, dir))
      .sort();

    // Failure message names the count AND the segments, so a future addition
    // that forgets its loading.tsx fails loudly with the exact path to fix,
    // not just a number.
    expect(missingNames, `${missingNames.length} of ${listSegments.length} segments missing loading.tsx`).toEqual([]);
  });

  it('renders the shared ListPageSkeleton, content-only, for every segment found', async () => {
    expect(listSegments.length).toBeGreaterThan(100);

    for (const dir of listSegments) {
      const loadingFile = path.join(dir, 'loading.tsx');
      if (!fs.existsSync(loadingFile)) continue; // already failed above; do not double-report here

      const relativeFromTest = './' + path.relative(PROTECTED_ROOT, dir).split(path.sep).join('/') + '/loading';
      const mod = await import(/* @vite-ignore */ relativeFromTest);
      const Loading = mod.default;
      expect(typeof Loading, `${relativeFromTest} has no default export`).toBe('function');

      const { container, unmount } = render(<Loading />);
      // Content-only: no shell wrapper of its own.
      expect(container.querySelector('[role="status"]')).not.toBeInTheDocument();
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
      unmount();
    }
  });
});
