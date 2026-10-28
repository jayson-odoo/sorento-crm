/**
 * PORTAL-P3-ROLE-MENU P3-10, P3-11, P3-12: what the SHIPPED `MENU_SIDEBAR` renders for a
 * salesperson (MY WORK + MY REQUESTS and nothing else) and that staff are untouched.
 * The staff result is pinned by snapshot, taken before the change.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig } from './types';
import { applyMenuAccess, type MenuAccess } from '@/lib/menu-access-filter';
import { LANDING_KINDS, LANDING_LABELS } from '@/lib/portal-form-kinds';

type Slim = { heading?: string; title?: string; path?: string; children?: Slim[] };

function slim(items: MenuConfig): Slim[] {
  return items.map((i) => ({
    ...(i.heading ? { heading: i.heading } : {}),
    ...(i.title ? { title: i.title } : {}),
    ...(i.path ? { path: i.path } : {}),
    ...(i.children?.length ? { children: slim(i.children) } : {}),
  }));
}

function slugsIn(items: MenuConfig, out = new Set<string>()): Set<string> {
  for (const i of items) {
    if (i.permission) out.add(i.permission);
    i.permissionsAny?.forEach((p) => out.add(p));
    if (i.children) slugsIn(i.children, out);
  }
  return out;
}

function access(
  permissions: Iterable<string>,
  salesperson: { portalKinds: string[] } | null,
  isSuperadmin = false,
): MenuAccess {
  return {
    isSuperadmin,
    permissionSet: new Set(permissions),
    isLoading: false,
    enabledModuleKeys: null,
    modulesLoading: false,
    salesperson,
  } as MenuAccess;
}

const SALES_PERMS = [
  'projects.projects.view_own',
  'sla_management.conversations.view_own',
  'sales.customer_asks.view',
  'sales.customer_asks.edit',
  'ideation.board.view',
  // PORTAL-P4-REQUESTS (pp4_0001): the salesperson role holds the four request forms' view_own.
  'procurement.stock_inquiries.view_own',
  'complaint_management.complaints.view_own',
  'procurement.purchase_requests.view_own',
  'procurement.sponsorship_forms.view_own',
  'projects.sample_requests.view_own',
  'sales.opportunities.view_own',
  'procurement.new_product_applications.view_own',
];

const ALL_KINDS = [...LANDING_KINDS] as string[];
// Portal landing order (landingKindsFor): Stock Inquiry first, then LANDING_KINDS order.
// PORTAL-P4-REQUESTS: no Project Registration item (one Projects page), and the four request
// forms open their staff list pages.
const REQUEST_KINDS = [
  'stock_inquiry',
  ...ALL_KINDS.filter(
    (k) =>
      k !== 'stock_inquiry' &&
      k !== 'customer_asks' &&
      k !== 'conversation' &&
      k !== 'project_registration',
  ),
];
const STAFF_LIST: Record<string, string> = {
  stock_inquiry: '/procurement-management/stock-inquiries',
  complaint: '/complaint-management/complaints',
  purchase_request: '/procurement-management/purchase-requests',
  sponsorship_form: '/procurement-management/sponsorship-forms',
  sample_request: '/project-sales/sample-requests',
  sales_opportunity: '/sales/opportunities',
  new_product_application: '/procurement-management/new-product-applications',
};

describe('MENU_SIDEBAR for a salesperson', () => {
  it('is exactly MY WORK then MY REQUESTS, in portal order', () => {
    const out = slim(applyMenuAccess(MENU_SIDEBAR, access(SALES_PERMS, { portalKinds: ALL_KINDS })));
    expect(out).toEqual([
      { heading: 'MY WORK' },
      { title: 'Projects', path: '/project-sales/pipeline' },
      { title: 'Conversations', path: '/sla-management/conversations' },
      { title: 'Customer asks', path: '/sales/customer-asks' },
      { heading: 'MY REQUESTS' },
      ...REQUEST_KINDS.map((k) => ({
        title: LANDING_LABELS[k as keyof typeof LANDING_LABELS],
        path: STAFF_LIST[k] ?? `/my-requests?type=${k}`,
      })),
    ]);
  });

  it('a kind the contact may not use has no item', () => {
    const kinds = ALL_KINDS.filter((k) => k !== 'sample_request' && k !== 'price_tag_request');
    const out = slim(applyMenuAccess(MENU_SIDEBAR, access(SALES_PERMS, { portalKinds: kinds })));
    const paths = out.map((i) => i.path);
    expect(paths).not.toContain('/my-requests?type=sample_request');
    expect(paths).not.toContain('/my-requests?type=price_tag_request');
    expect(paths).toContain('/procurement-management/stock-inquiries');
  });

  it('no MY REQUESTS heading when the contact has no request kind', () => {
    const out = slim(
      applyMenuAccess(MENU_SIDEBAR, access(SALES_PERMS, { portalKinds: ['customer_asks', 'conversation'] })),
    );
    expect(out.map((i) => i.heading).filter(Boolean)).toEqual(['MY WORK']);
  });
});

const everyPermission = [...slugsIn(MENU_SIDEBAR)];

const STAFF_FIXTURES: Array<[string, MenuAccess]> = [
  ['admin with every permission', access(everyPermission, null)],
  ['superadmin', access([], null, true)],
  ['role with projects.projects.view', access(['projects.projects.view'], null)],
  ['role without projects.projects.view', access(['sales.customer_asks.view'], null)],
  ['mixed user (salesperson plus staff role): salesperson null', access([...SALES_PERMS, 'projects.projects.view'], null)],
];

describe('MENU_SIDEBAR for staff is unchanged', () => {
  it.each(STAFF_FIXTURES)('%s: no MY WORK / MY REQUESTS', (_name, acc) => {
    const out = applyMenuAccess(MENU_SIDEBAR, acc);
    const headings = out.map((i) => i.heading).filter(Boolean);
    expect(headings).not.toContain('MY WORK');
    expect(headings).not.toContain('MY REQUESTS');
    expect(JSON.stringify(slim(out))).not.toContain('/my-requests');
  });

  it.each(STAFF_FIXTURES)('%s: filtered menu matches the pre-change snapshot', (name, acc) => {
    expect(slim(applyMenuAccess(MENU_SIDEBAR, acc))).toMatchSnapshot(name);
  });
});
