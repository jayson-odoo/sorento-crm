/**
 * GUARD (owner ruling, 12 Nov 2026): After-sales changes NOTHING in the live Complaints module.
 * The Complaints sidebar sections keep exactly the children origin/main gave them, and no file of the
 * complaint-management pages imports from after-sales.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR_COMPACT, MENU_SIDEBAR } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function find(items: MenuConfig, title: string): MenuItem | undefined {
  for (const item of items) {
    if (item.title === title && item.children) return item;
  }
  return undefined;
}

const slim = (item: MenuItem | undefined) =>
  (item?.children ?? []).map((c) => ({ title: c.title, path: c.path, permission: c.permission }));

describe('Complaints sidebar sections are unchanged', () => {
  it('Complaints (staff sidebar)', () => {
    expect(slim(find(MENU_SIDEBAR, 'Complaints'))).toEqual([
      { title: 'Complaints', path: '/complaint-management/complaints', permission: 'complaint_management.complaints.view' },
      { title: 'Root Causes', path: '/complaint-management/complaint-root-causes', permission: 'master_data.complaint_root_causes.view' },
      { title: 'Resolutions', path: '/complaint-management/complaint-resolutions', permission: 'master_data.complaint_resolutions.view' },
    ]);
  });

  it('Complaint Management (compact sidebar)', () => {
    expect(slim(find(MENU_SIDEBAR_COMPACT, 'Complaint Management'))).toEqual([
      { title: 'Complaints', path: '/complaint-management/complaints', permission: undefined },
      { title: 'Root Causes', path: '/complaint-management/complaint-root-causes', permission: 'master_data.complaint_root_causes.view' },
      { title: 'Resolutions', path: '/complaint-management/complaint-resolutions', permission: 'master_data.complaint_resolutions.view' },
    ]);
  });
});

describe('After-sales is its own sidebar section', () => {
  it('lists its four pages under the after_sales module with its own permissions', () => {
    const section = find(MENU_SIDEBAR, 'After-Sales Service');
    expect(section?.moduleKey).toBe('after_sales');
    expect(slim(section).map((c) => c.path)).toEqual([
      '/after-sales/service-jobs',
      '/after-sales/dispatch-board',
      '/after-sales/technicians',
      '/after-sales/warranty',
    ]);
  });
});

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sources(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

describe('the complaint-management pages never import from after-sales', () => {
  it('no import path names after-sales or its service job code', () => {
    const root = join(__dirname, '..', 'app', '(protected)', 'complaint-management');
    const offenders = sources(root).filter((file) =>
      /from\s+['"][^'"]*(after-sales|service-jobs|serviceJob)[^'"]*['"]/.test(readFileSync(file, 'utf8')),
    );
    expect(offenders).toEqual([]);
  });
});
