/**
 * S1 (#1267), AC-R2-5 / AC-S1-12: the Yearly comparison sits in the Sales group under the
 * SALES heading, gated by the `sales` module and `sales.reports.view`, and its route maps
 * to the `sales` module. AC-R2-1: the only new report files are the route wrapper, the
 * chart and the chart's number helper - the page, filter bar and table are the kernel's.
 */
import { existsSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import { moduleKeyForPath } from '@/lib/route-module-map';

describe('Sales menu', () => {
  it('lists Yearly comparison in the Sales group after the SALES heading', () => {
    const heading = MENU_SIDEBAR.findIndex((i) => i.heading === 'SALES');
    const next = MENU_SIDEBAR.findIndex(
      (i, idx) => idx > heading && Boolean(i.heading),
    );
    const group = MENU_SIDEBAR.findIndex(
      (i) => !i.heading && i.title === 'Sales',
    );
    expect(group).toBeGreaterThan(heading);
    expect(group).toBeLessThan(next);
    const sales = MENU_SIDEBAR[group];
    // One Sales group, shared with #1260: the group has no moduleKey, each child carries
    // the module that owns its route.
    expect(MENU_SIDEBAR.filter((i) => !i.heading && i.title === 'Sales')).toHaveLength(1);
    const item = sales.children?.find((c) => c.title === 'Yearly comparison');
    expect(item?.path).toBe('/sales/yearly-comparison');
    expect(item?.permission).toBe('sales.reports.view');
    expect(item?.moduleKey).toBe('sales');
  });

  it('maps /sales to the sales module', () => {
    expect(moduleKeyForPath('/sales/yearly-comparison')).toBe('sales');
  });

  it('AC-R2-1: the page is the kernel ReportPage with key sales_yearly; the reports folder gains only the chart', () => {
    const root = path.resolve(__dirname, '..');
    const page = path.join(
      root,
      'app/(protected)/sales/yearly-comparison/page.tsx',
    );
    expect(existsSync(page)).toBe(true);
    const files = readdirSync(path.join(root, 'components/reports')).filter(
      (f) => !f.includes('.test.'),
    );
    expect(files.sort()).toEqual(
      [
        'ConfigureSummaryDialog.tsx',
        'ReportFilterBar.tsx',
        'ReportPage.tsx',
        'ReportPivotChart.tsx',
        'ReportPivotTable.tsx',
        'ReportViewsMenu.tsx',
        'reportFormat.ts',
      ].sort(),
    );
  });
});
