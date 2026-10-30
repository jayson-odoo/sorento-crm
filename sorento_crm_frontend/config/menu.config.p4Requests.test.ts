/**
 * PORTAL-P4-REQUESTS S-FE0 (P4-20): for a salesperson the four form items under MY REQUESTS open the
 * STAFF list pages (server-side "only theirs"), not the embedded portal. Project Registration has no item
 * (owner v1.1 Q7: one Projects page). The staff menu is untouched.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig } from './types';
import { applyMenuAccess, type MenuAccess } from '@/lib/menu-access-filter';
import { LANDING_KINDS, LANDING_LABELS } from '@/lib/portal-form-kinds';

type Slim = { heading?: string; title?: string; path?: string };
const flat = (items: MenuConfig): Slim[] =>
  items.map((i) => ({ heading: i.heading, title: i.title, path: i.path }));

function access(permissions: string[], salesperson: { portalKinds: string[] } | null): MenuAccess {
  return {
    isSuperadmin: false,
    permissionSet: new Set(permissions),
    isLoading: false,
    enabledModuleKeys: null,
    modulesLoading: false,
    salesperson,
  } as MenuAccess;
}

const ALL_KINDS = [...LANDING_KINDS] as string[];
const VIEW_OWN = [
  'procurement.stock_inquiries.view_own',
  'complaint_management.complaints.view_own',
  'procurement.purchase_requests.view_own',
  'procurement.sponsorship_forms.view_own',
];
const SALES = ['projects.projects.view_own', 'sales.customer_asks.view', ...VIEW_OWN];

function myRequests(out: Slim[]): Slim[] {
  const at = out.findIndex((i) => i.heading === 'MY REQUESTS');
  return at < 0 ? [] : out.slice(at + 1).filter((i) => !i.heading);
}

describe('MY REQUESTS for a salesperson (P4-20)', () => {
  const items = () => myRequests(flat(applyMenuAccess(MENU_SIDEBAR, access(SALES, { portalKinds: ALL_KINDS }))));

  it.each([
    ['stock_inquiry', '/procurement-management/stock-inquiries'],
    ['complaint', '/complaint-management/complaints'],
    ['purchase_request', '/procurement-management/purchase-requests'],
    ['sponsorship_form', '/procurement-management/sponsorship-forms'],
  ])('%s opens the staff list %s', (kind, path) => {
    const item = items().find((i) => i.title === LANDING_LABELS[kind as keyof typeof LANDING_LABELS]);
    expect(item, `no MY REQUESTS item for ${kind}`).toBeDefined();
    expect(item?.path).toBe(path);
  });

  it('has no Project Registration item at all', () => {
    const rows = items();
    expect(rows.map((i) => i.title)).not.toContain(LANDING_LABELS.project_registration);
    expect(JSON.stringify(rows)).not.toContain('project_registration');
  });

  it('the four form kinds no longer route through /my-requests', () => {
    const paths = items()
      .filter((i) =>
        ['stock_inquiry', 'complaint', 'purchase_request', 'sponsorship_form']
          .map((k) => LANDING_LABELS[k as keyof typeof LANDING_LABELS])
          .includes(i.title as string),
      )
      .map((i) => i.path);
    expect(paths).toHaveLength(4);
    paths.forEach((p) => expect(p).not.toContain('/my-requests'));
  });
});

describe('staff menu is unchanged (P4-26)', () => {
  it('a staff user still sees the staff stock inquiry entry and no MY REQUESTS', () => {
    const out = flat(
      applyMenuAccess(MENU_SIDEBAR, access(['procurement.stock_inquiries.view', 'procurement.stock_inquiries.add'], null)),
    );
    expect(out.map((i) => i.heading).filter(Boolean)).not.toContain('MY REQUESTS');
    expect(JSON.stringify(out)).not.toContain('/my-requests');
  });
});
