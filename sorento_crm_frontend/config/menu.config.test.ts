/**
 * Sidebar wiring tests for MENU_SIDEBAR reorganisation (Slice 5 of
 * PLAN-module-access-gates.md).
 *
 * Validates that the reorganised sidebar preserves every existing path, places
 * moved entries in their new groups, and applies the correct gates.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import { filterOrphanHeadings } from '@/app/components/layouts/demo1/components/sidebar-menu';
import type { MenuConfig, MenuItem } from './types';

/** Recursively collect all `path` values from a menu tree. */
function collectPaths(items: MenuConfig): Set<string> {
  const paths = new Set<string>();
  for (const item of items) {
    if (item.path) paths.add(item.path);
    if (item.children) {
      for (const p of collectPaths(item.children)) {
        paths.add(p);
      }
    }
  }
  return paths;
}

/** Find a top-level group (non-heading) by title in a menu. */
function findGroup(menu: MenuConfig, title: string): MenuItem | undefined {
  return menu.find((item) => !item.heading && item.title === title);
}

/** Find a sub-group (child without a path) by title under a parent group. */
function findSubGroup(parent: MenuItem, title: string): MenuItem | undefined {
  return parent.children?.find((item) => item.title === title && !item.path && item.children);
}

/** Find a leaf by title within a menu array (non-recursive). */
function findLeaf(items: MenuConfig, title: string): MenuItem | undefined {
  return items.find((item) => item.title === title && item.path);
}

// ---------------------------------------------------------------------------
// Path preservation
// ---------------------------------------------------------------------------

/**
 * The old MENU_SIDEBAR paths that must appear in the new one. The only
 * intentional removal is `/system-management/outgoing-mails`, which was
 * converted from a leaf into a sub-group container (Outgoing Mails) with
 * Email Outbox and Respond Outbox as children.
 */
const INTENTIONALLY_REMOVED_PATHS = new Set<string>([]);

/** Snapshot of every leaf path from the pre-reorganisation MENU_SIDEBAR. */
const OLD_PATHS: string[] = [
  '/',
  '/ideas',
  '/user-management/users',
  '/user-management/onboarding-requests',
  '/user-management/roles',
  '/user-management/permissions',
  '/user-management/access-agents',
  '/user-management/teams',
  '/user-management/contact-access-agents',
  '/user-management/contact-access-types',
  '/user-management/market-segments',
  '/master-data-management/sales-agents',
  '/user-management/account',
  '/user-management/logs',
  '/user-management/settings',
  '/scm',
  '/scm/reorder',
  '/scm/loading-plan',
  '/scm/incoming',
  '/scm/proforma-invoices',
  '/scm/policies',
  '/scm/sales-orders',
  '/scm/purchase-orders',
  '/scm/market-signals',
  '/scm/simulation',
  '/dealer-kit',
  '/dealer-kit/collections',
  '/dealer-kit/tile-designs',
  '/dealer-kit/brochure-images',
  '/dealer-kit/flyer-readings',
  '/dealer-kit/editions',
  '/dealer-kit/bundles',
  '/dealer-kit/design',
  '/dealer-kit/design/summary',
  '/order-management/orders',
  '/order-management/order-statuses',
  '/order-management/customers',
  '/complaint-management/complaints',
  '/complaint-management/complaint-root-causes',
  '/complaint-management/complaint-resolutions',
  '/sla-management/sla-policies',
  '/sla-management/conversations',
  '/sla-management/conversation-sla-tracking',
  '/sla-management/form-sla-tracking',
  '/sla-management/team-pending',
  '/sla-management/form-sla-config',
  '/sla-management/escalation-logs',
  '/sla-management/message-snippets',
  '/sla-management/kpi-dashboard',
  '/master-data-management/products',
  '/master-data-management/product-attachments',
  '/master-data-management/certificates',
  '/master-data-management/product-categories',
  '/master-data-management/product-specifications',
  '/master-data-management/spec-verification',
  '/master-data-management/flyer-spec-proposals',
  '/master-data-management/brands',
  '/master-data-management/units-of-measure',
  '/procurement-management/suppliers',
  '/procurement-management/product-suppliers',
  '/procurement-management/packing-lists',
  '/procurement-management/spo-allocations',
  '/procurement-management/grn',
  '/procurement-management/picking-lines',
  '/procurement-management/stock-inquiries',
  '/procurement-management/purchase-requests',
  '/procurement-management/sponsorship-forms',
  '/inventory-management/warehouses',
  '/inventory-management/storage-zones',
  '/inventory-management/stock',
  '/inventory-management/stock-batches',
  '/inventory-management/stock-ledger',
  '/project-sales/pipeline',
  '/project-sales/leads',
  '/project-sales/lead-acceptance',
  '/project-sales/my-tasks',
  '/project-sales/stock-claims',
  '/project-sales/divergences',
  '/project-sales/fulfilment-planning',
  '/project-sales/plans',
  '/project-sales/order-inquiries',
  '/project-sales/planning-changes',
  '/project-sales/reports',
  '/project-sales/parties',
  '/project-sales/setup',
  '/project-sales/series',
  '/project-sales/price-floors',
  '/marketing-management/promotions',
  '/marketing-management/promotion-attachments',
  '/marketing-management/promotion-types',
  '/marketing-management/promotion-products',
  '/marketing-management/campaigns',
  '/forms-management/forms',
  '/workflow-forms-management/definitions',
  '/resource-management/attachment-directories',
  '/resource-management/trash',
  '/resource-management/attachment-types',
  '/system-management/companies',
  '/system-management/app-store',
  '/system-management/app-store/bundles',
  '/system-management/import-jobs',
  '/system-management/import-logs',
  '/system-management/tracking-validation',
  '/system-management/audit-logs',
  '/system-management/health',
  '/system-management/activity',
  '/integration-management/integrations',
  '/integration-management/integration-logs',
  '/integration-management/whatsapp-templates',
  '/system-management/scheduled-tasks',
  '/system-management/outgoing-mails',
  '/system-management/email-outbox',
  '/system-management/respond-outbox',
  '/system-management/chat-history',
  '/system-management/api-call-logs',
  '/system-management/email-event-configs',
  '/system-management/email-templates',
  '/system-management/automation',
  '/system-management/work-calendar',
  '/system-management/numbering-rules',
  '/system-management/status-graphs',
  '/master-data-management/lookup-sets',
  '/system-management/respond-workspaces',
  '/system-management/respond-contacts',
  '/system-management/ai-assistant',
  '/system-management/ai-assistant/prompts',
  '/system-management/ai-assistant/usage',
  '/system-management/ai-assistant/wishlist',
  '/system-management/mcp-tools',
];

describe('menu.config - path preservation', () => {
  it('every old leaf path exists in the new MENU_SIDEBAR (minus intentional removals)', () => {
    const newPaths = collectPaths(MENU_SIDEBAR);
    const missing: string[] = [];
    for (const p of OLD_PATHS) {
      if (!INTENTIONALLY_REMOVED_PATHS.has(p) && !newPaths.has(p)) {
        missing.push(p);
      }
    }
    expect(missing).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Planning changes - moved to Supply Chain > Project Demand
// ---------------------------------------------------------------------------

describe('menu.config - Planning changes entry', () => {
  it('is present under Supply Chain > Project Demand in MENU_SIDEBAR', () => {
    const scm = findGroup(MENU_SIDEBAR, 'Supply Chain');
    expect(scm).toBeDefined();
    const projectDemand = findSubGroup(scm!, 'Project Demand');
    expect(projectDemand).toBeDefined();
    const entry = findLeaf(projectDemand!.children!, 'Planning changes');
    expect(entry).toBeDefined();
    expect(entry).toMatchObject({
      title: 'Planning changes',
      path: '/project-sales/planning-changes',
      permission: 'projects.projects.view',
    });
  });

  it('sits right after Order Inquiries in Project Demand', () => {
    const scm = findGroup(MENU_SIDEBAR, 'Supply Chain');
    const projectDemand = findSubGroup(scm!, 'Project Demand');
    const titles = projectDemand!.children!.map((item) => item.title);
    const orderInquiriesAt = titles.indexOf('Order Inquiries');
    expect(orderInquiriesAt).toBeGreaterThanOrEqual(0);
    expect(titles[orderInquiriesAt + 1]).toBe('Planning changes');
  });

  it('is still present under Project Sales in MENU_SIDEBAR_COMPACT', () => {
    const ps = MENU_SIDEBAR_COMPACT.find((item) => item.title === 'Project Sales');
    expect(ps).toBeDefined();
    const entry = ps!.children!.find((item) => item.title === 'Planning changes');
    expect(entry).toBeDefined();
    expect(entry).toMatchObject({
      title: 'Planning changes',
      path: '/project-sales/planning-changes',
      permission: 'projects.projects.view',
    });
  });
});

// ---------------------------------------------------------------------------
// New gates
// ---------------------------------------------------------------------------

describe('menu.config - Ideas', () => {
  it('has permission ideation.board.view', () => {
    const ideas = findGroup(MENU_SIDEBAR, 'Ideas');
    expect(ideas).toBeDefined();
    expect(ideas!.permission).toBe('ideation.board.view');
  });
});

describe('menu.config - Dealer Kit', () => {
  it('has moduleKey dealer_kit', () => {
    const dk = findGroup(MENU_SIDEBAR, 'Dealer Kit');
    expect(dk).toBeDefined();
    expect(dk!.moduleKey).toBe('dealer_kit');
  });

  it('every leaf has permission dealer_kit.page.view', () => {
    const dk = findGroup(MENU_SIDEBAR, 'Dealer Kit');
    const leafPerms: string[] = [];
    function walk(items: MenuConfig) {
      for (const item of items) {
        if (item.path) leafPerms.push(item.permission ?? '');
        if (item.children) walk(item.children);
      }
    }
    walk(dk!.children!);
    expect(leafPerms.length).toBeGreaterThan(0);
    expect(leafPerms.every((p) => p === 'dealer_kit.page.view')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Orphan heading filter
// ---------------------------------------------------------------------------

describe('filterOrphanHeadings', () => {
  it('drops a heading with no following groups', () => {
    const input: MenuConfig = [
      { heading: 'OVERVIEW' },
      { title: 'Dashboard', path: '/' },
      { heading: 'EMPTY' },
      { heading: 'TOOLS' },
      { title: 'Settings', path: '/settings' },
    ];
    const result = filterOrphanHeadings(input);
    const headings = result.filter((i) => i.heading).map((i) => i.heading);
    expect(headings).toEqual(['OVERVIEW', 'TOOLS']);
    expect(headings).not.toContain('EMPTY');
  });

  it('drops a trailing heading at the end of the list', () => {
    const input: MenuConfig = [
      { heading: 'FIRST' },
      { title: 'Item', path: '/item' },
      { heading: 'ORPHAN' },
    ];
    const result = filterOrphanHeadings(input);
    expect(result.filter((i) => i.heading)).toHaveLength(1);
    expect(result[0].heading).toBe('FIRST');
  });

  it('keeps all headings when each has at least one group', () => {
    const input: MenuConfig = [
      { heading: 'A' },
      { title: 'X', path: '/x' },
      { heading: 'B' },
      { title: 'Y', path: '/y' },
    ];
    const result = filterOrphanHeadings(input);
    expect(result).toHaveLength(4);
  });
});

// ---------------------------------------------------------------------------
// Section structure
// ---------------------------------------------------------------------------

describe('menu.config - section headings', () => {
  it('has exactly 6 headings in order', () => {
    const headings = MENU_SIDEBAR.filter((i) => i.heading).map((i) => i.heading);
    expect(headings).toEqual([
      'OVERVIEW',
      'SALES',
      'SUPPLY CHAIN',
      'CATALOGUE',
      'OPERATIONS',
      'ADMINISTRATION',
    ]);
  });
});

describe('menu.config - Complaint Management', () => {
  it('is a standalone group with moduleKey complaints', () => {
    const complaints = findGroup(MENU_SIDEBAR, 'Complaint Management');
    expect(complaints).toBeDefined();
    expect(complaints!.moduleKey).toBe('complaints');
  });
});

describe('menu.config - SLA Management', () => {
  it('is a standalone group with moduleKey sla', () => {
    const sla = findGroup(MENU_SIDEBAR, 'SLA Management');
    expect(sla).toBeDefined();
    expect(sla!.moduleKey).toBe('sla');
  });
});

describe('menu.config - Project Sales Admin', () => {
  it('is a standalone group with moduleKey procurement', () => {
    const psa = findGroup(MENU_SIDEBAR, 'Project Sales Admin');
    expect(psa).toBeDefined();
    expect(psa!.moduleKey).toBe('procurement');
  });
});
