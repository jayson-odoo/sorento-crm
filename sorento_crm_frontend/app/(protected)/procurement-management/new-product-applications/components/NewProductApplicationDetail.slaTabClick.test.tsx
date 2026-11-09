/**
 * NPA-FORM-SLA crew pass 9 Nov: clicking the SLA Tracking tab froze the page (a render loop).
 * The REAL FormSLATrackingTab renders here (only its fetch is mocked).
 * NEW-PRODUCT-APP staff detail: which button each viewer sees on each status, and the Link
 * product search (it only lists; a person picks). Hooks, the pager and the shell are mocked;
 * the page's own rules run.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type {
  NewProductApplicationDetail as Detail,
  NewProductApplicationLine,
} from '@/types/newProductApplication';

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  userId: 'u-owner',
  data: undefined as unknown,
  link: vi.fn(),
  purchasing: vi.fn(),
  purchasingReject: vi.fn(),
  purchasingReply: vi.fn(),
  closeCode: vi.fn(),
  undoCode: vi.fn(),
  undoLine: vi.fn(),
  search: vi.fn(),
  feedback: vi.fn(),
  download: vi.fn(),
  linkAtt: vi.fn(),
  unlinkRun: vi.fn(),
  unlinkInputs: [] as Record<string, unknown>[],
}));

// Next's app router syncs a `history.replaceState` into `useSearchParams` (useUrlTab relies on
// it). The click-loop only shows with that sync, so this stand-in does the same: replaceState
// notifies, and useSearchParams re-reads the live URL.
vi.mock('next/navigation', async () => {
  const React = await import('react');
  const listeners = new Set<() => void>();
  const original = window.history.replaceState.bind(window.history);
  window.history.replaceState = (data: unknown, unused: string, url?: string | URL | null) => {
    original(data, unused, url);
    listeners.forEach((l) => l());
  };
  const subscribe = (l: () => void) => {
    listeners.add(l);
    return () => listeners.delete(l);
  };
  return {
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
    usePathname: () => window.location.pathname,
    useSearchParams: () => {
      const search = React.useSyncExternalStore(subscribe, () => window.location.search);
      return React.useMemo(() => new URLSearchParams(search), [search]);
    },
  };
});
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({
  useEffectiveUserId: () => state.userId,
}));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({
    countdown: null,
    isBlocked: false,
    start: vi.fn(),
  }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/audit/AuditTrail', () => ({
  default: () => <div data-testid="audit-trail" />,
}));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({
    gear,
    primary,
  }: {
    gear?: React.ReactNode;
    primary?: React.ReactNode;
  }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', async (orig) => ({
  ...(await orig<typeof import('@/components/ui/dropdown-menu')>()),
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: () => void;
  }) => <button onClick={() => onSelect?.()}>{children}</button>,
}));
vi.mock('../hooks/useNewProductApplications', () => ({
  newProductApplicationsPagerQuery: {},
  useNewProductApplicationListingKey: (suffix?: string) =>
    suffix ? `procurement.new_product_applications.view::${suffix}` : 'procurement.new_product_applications.view',
  useNewProductApplicationQuery: () => ({
    data: state.data,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useNewProductApplicationMutations: () => {
    const idle = () => ({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
    });
    return {
      submit: idle(),
      approve: idle(),
      reject: idle(),
      revise: idle(),
      cancel: idle(),
      linkNewCode: { mutate: state.link, mutateAsync: state.link, isPending: false },
      closeNewCode: {
        mutate: state.closeCode,
        mutateAsync: state.closeCode,
        isPending: false,
      },
      undo: { mutate: state.undoLine, mutateAsync: state.undoLine, isPending: false },
      undoNewCode: { mutate: state.undoCode, mutateAsync: state.undoCode, isPending: false },
      purchasingReply: {
        mutate: state.purchasingReply,
        mutateAsync: state.purchasingReply,
        isPending: false,
      },
      purchasingReject: {
        mutate: state.purchasingReject,
        mutateAsync: state.purchasingReject,
        isPending: false,
      },
      purchasingResponse: {
        mutate: state.purchasing,
        mutateAsync: state.purchasing,
        isPending: false,
      },
      feedback: {
        mutate: state.feedback,
        mutateAsync: state.feedback,
        isPending: false,
      },
    };
  },
}));
vi.mock('../services/newProductApplicationService', () => ({
  searchNewProductApplicationProducts: (q: string) => state.search(q),
  exportNewProductApplicationXlsx: (...a: unknown[]) => state.download(...a),
  linkNewProductApplicationAttachment: (...a: unknown[]) => state.linkAtt(...a),
}));

vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({
  __esModule: true,
  default: (props: {
    open: boolean;
    entityId?: string;
    linkAttachment?: (e: string, a: string) => Promise<unknown>;
  }) =>
    props.open ? (
      <div role="dialog" aria-label="Link attachment library">
        <button onClick={() => void props.linkAttachment?.(props.entityId!, 'at-5')}>
          Pick library file
        </button>
      </div>
    ) : null,
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    state.unlinkInputs.push(input);
    return { run: state.unlinkRun, targetId: null, isPending: false, countdown: null };
  },
}));

// NPA-FORM-SLA: the SI's handling lock and SLA tab, mocked so each test sets the lock state.
const lock = vi.hoisted(() => ({
  enabled: true,
  input: null as null | Record<string, unknown>,
}));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: (input: Record<string, unknown>) => {
    lock.input = input;
    return {
      state: lock.enabled ? 'not_escalated' : 'other_holds',
      businessCtasEnabled: lock.enabled,
      tracker: lock.enabled ? null : { handled_by_name: 'Purchasing Manager' },
      banner: null,
      claim: vi.fn(),
      takeOver: vi.fn(),
      release: vi.fn(),
      refresh: vi.fn(),
      isMutating: false,
    };
  },
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({
  HandlingLockBanner: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({
  HandlingLockReleaseMenuItem: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', async (orig) => ({
  ...(await orig<typeof import('@/app/(protected)/sla-management/_shared/formSLAService')>()),
  getFormSLATrackers: vi.fn(async () => []),
}));

import NewProductApplicationDetail from './NewProductApplicationDetail';

function Page() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <NewProductApplicationDetail applicationId="a-1" />
    </QueryClientProvider>
  );
}

function line(
  over: Partial<NewProductApplicationLine> = {},
): NewProductApplicationLine {
  return {
    id: 'l-1',
    line_no: 1,
    proposed_code: 'XY-1234-MB',
    description: 'Example kitchen sink',
    dimension: '600x400',
    material: 'Steel',
    thickness: '1.2mm',
    packing: 'Carton',
    brand_id: null,
    brand_name: null,
    expected_qty: '55',
    cost_price: null,
    opened_category_name: null,
    opened_base_uom_name: null,
    opened_list_price: null,
    opened_supplier_name: null,
    opened_product_id: null,
    opened_product_code: null,
    opened_product_name: null,
    opened_product_active: null,
    closed_reason: null,
    resolved_by: null,
    resolved_by_name: null,
    resolved_at: null,
    ...over,
  };
}

function detail(over: Partial<Detail> = {}): Detail {
  return {
    id: 'a-1',
    application_no: 'NPA-000001',
    status: 'draft',
    status_label: 'Draft',
    source: 'staff',
    applicant_id: 'u-owner',
    applicant_name: 'Owner',
    stock_inquiry_id: 'si-1',
    stock_inquiry_number: 'SI26-0412',
    stock_inquiry_product_code: 'XY-1234-MB',
    customer_id: null,
    customer_code: null,
    customer_name: 'EXAMPLE DEVELOPER SDN BHD',
    project_name: 'EXAMPLE RESIDENCE, TOWER B',
    opened_codes: [],
    needed_by: null,
    submitted_at: null,
    created_at: '2026-10-17T01:00:00',
    updated_at: null,
    remark: null,
    lead_time: null,
    attachments: [],
    decided_at: null,
    decided_by: null,
    decided_by_name: null,
    reject_reason: null,
    revise_reason: null,
    cancelled_at: null,
    cancel_reason: null,
    completed_at: null,
    lines: [
      line(),
      line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' }),
    ],
    ...over,
  };
}


beforeEach(() => {
  vi.clearAllMocks();
  state.perms = new Set();
  state.userId = 'u-owner';
  state.data = detail();
  state.search.mockResolvedValue([]);
});


describe('clicking SLA Tracking does not loop (crew pass 9 Nov)', () => {
  it('renders the SLA tab after a click without an infinite update', async () => {
    state.perms = new Set(['procurement.new_product_applications.approve']);
    state.data = detail({ status: 'submitted', status_label: 'Submitted', submitted_at: '2026-11-08T01:00:00' });
    window.history.replaceState(
      null,
      '',
      '/procurement-management/new-product-applications/a-1?page=1&limit=25&from=a-1',
    );
    const errors: unknown[] = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...a) => {
      errors.push(a);
    });
    render(<Page />);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'SLA Tracking' }));
    fireEvent.click(screen.getByRole('tab', { name: 'SLA Tracking' }));
    const text = await screen.findByText(/No SLA trackers attached to this new product application/);
    expect(errors.map(String).join(' ')).not.toMatch(/Maximum update depth/);
    // The SI's mount (FormDetailWithSLATabs): the SLA body lives in the SLA trigger's own
    // tabpanel, inside the Tabs. Rendered outside the Tabs it froze the real page on a click
    // (jsdom cannot show that loop: it needs a real browser's focus handling; verified there).
    const trigger = screen.getByRole('tab', { name: 'SLA Tracking' });
    const panel = text.closest('[role="tabpanel"]');
    expect(panel, 'the SLA body is not inside a tabpanel').not.toBeNull();
    expect(panel!.getAttribute('aria-labelledby')).toBe(trigger.id);
    spy.mockRestore();
  });

  it('keeps every tab body inside its own panel (Details, Stock inquiry)', async () => {
    window.history.replaceState(null, '', '/procurement-management/new-product-applications/a-1');
    state.perms = new Set(['procurement.new_product_applications.approve']);
    state.data = detail();
    render(<Page />);
    const details = screen.getByRole('tab', { name: 'Details' });
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(details.id);
    const si = screen.getByRole('tab', { name: 'Stock inquiry' });
    fireEvent.mouseDown(si);
    fireEvent.click(si);
    expect((await screen.findByRole('tabpanel')).getAttribute('aria-labelledby')).toBe(si.id);
  });
});
