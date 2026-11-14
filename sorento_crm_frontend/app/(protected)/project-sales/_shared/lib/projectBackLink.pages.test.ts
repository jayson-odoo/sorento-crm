/**
 * RELATED-RECORDS-B (owner, 14 Nov): every record opened from a project tab shows "Back to
 * project" and returns to the tab it came from.
 *
 * - A record that lives outside the project (sample request, and every Related type) reads the
 *   `back=` origin its project tab put on the URL: its BackToList passes `originLabel`, so with
 *   no origin (opened from its own list) it keeps its list Back.
 * - PO and SO live under the project route, so their Back names the project tab directly, the way
 *   a proposal's header already does.
 *
 * Source scan, as the pages are server components with no logic of their own; BackToList's own
 * behaviour is pinned in components/common/BackToList.origin.test.tsx.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const APP = join(__dirname, '../../..');
const read = (path: string) => readFileSync(join(APP, path), 'utf8');

const ORIGIN_PAGES = [
  'project-sales/sample-requests/[id]/page.tsx',
  'procurement-management/stock-inquiries/[id]/page.tsx',
  'complaint-management/complaints/[id]/page.tsx',
  'procurement-management/purchase-requests/[id]/page.tsx',
  'procurement-management/sponsorship-forms/[id]/page.tsx',
  'procurement-management/new-product-applications/[id]/page.tsx',
  'procurement-management/order-change-notices/[id]/page.tsx',
];

describe('records opened from a project tab say Back to project', () => {
  it.each(ORIGIN_PAGES)('%s honours the project origin', (path) => {
    expect(read(path)).toMatch(/<BackToList[^>]*originLabel="Back to project"/s);
  });

  it.each([
    ['project-sales/[projectId]/pos/[poId]/page.tsx', 'orders'],
    ['project-sales/[projectId]/sales-orders/[psoId]/page.tsx', 'sales-orders'],
  ])('%s goes back to the project %s tab', (path, tab) => {
    const source = read(path);
    expect(source).toMatch(
      new RegExp(`<BackToList[^>]*listPath=\\{\`/project-sales/\\$\\{projectId\\}\\?tab=${tab}\`\\}[^>]*label="Back to project"`, 's'),
    );
    expect(source).toContain(`projectCrumbs(projectId, { tab: '${tab}' }`);
  });
});
