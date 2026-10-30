/**
 * PORTAL-P4-REQUESTS owner hand test 2 (A) + hand test 3 note 1 (owner a25895124 Q2 a): a salesperson limited to
 * their own complaints sees that complaint's fulfilment DOs, read-only, in a "Fulfilment DOs" TAB of the portal's
 * own form (after Details / Comments / Revisions), as the staff view does. DO numbers are plain text, no edit /
 * link / unlink action, no anchor to a DO page they cannot open. The staff detail is pinned by
 * ComplaintDetail.requestScope.test.tsx (staff action set unchanged).
 *
 * CHANGED in hand test 3 (was: the portal form stubbed, DO list asserted "below the form"): the form is now the
 * REAL MyRequestPortalForm -> SubmissionForm over a fake my-requests API, because the tab lives inside it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createCrmApi, CMP_DETAIL } from '@/app/(auth)/portal/components/__fixtures__/crmSubmissionApi';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/complaint-management/complaints/cp-5',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Ann Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({ deferredToast: vi.fn(() => 't'), dismissDeferredToast: vi.fn() }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./ComplaintConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({ EntityDownloadsButton: () => null }));
vi.mock('@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses', () => ({ useComplaintRootCausesSelect: () => ({ data: [], error: null, refetch: vi.fn() }) }));
vi.mock('@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions', () => ({ useComplaintResolutionsSelect: () => ({ data: [], error: null, refetch: vi.fn() }) }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/useFormSkip', () => ({ useFormSkip: () => ({ canSkip: true, actionLabel: 'Settled on site', isSubmitting: false, skip: vi.fn() }) }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({ getFormSLATrackers: async () => [], escalateFormTracking: vi.fn() }));
vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({ SlaActiveTrackerControls: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({ SlaExtendMenuItem: () => null, SlaExtendDialog: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({ HandlingLockBanner: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({ HandlingLockReleaseMenuItem: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({ view: { kind: 'idle' }, ctasDisabled: false, cancel: vi.fn(), undo: vi.fn(), refresh: vi.fn(), isMutating: false }),
}));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => ({
    state: 'not_escalated', businessCtasEnabled: true, tracker: { id: 't1', is_resolved: false, event_logs: [] },
    claim: vi.fn(), takeOver: vi.fn(), release: vi.fn(), refresh: vi.fn(), isMutating: false,
  }),
}));
vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useReassignSLATracking: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/useFormVoid', () => ({ useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }) }));

const complaintRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/useComplaints', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useComplaint: () => ({ data: complaintRef.current, isLoading: false }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));


vi.mock('@/hooks/useRequestScope', () => ({
  useRequestScope: () => ({ limited: true, isLoading: false }),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('../services/complaintFulfilmentService', () => ({
  getComplaintFulfilmentOrders: vi.fn(async () => [
    {
      order_id: 'o-1',
      order_number: 'REPPS2605-0012',
      status: 'delivered',
      status_label: 'Delivered',
      actual_delivery_date: '2026-06-02T09:00:00',
      is_cancelled: false,
      items: [{ product_code: 'SKU-1', product_type: 'Mattress', qty: 2 }],
    },
  ]),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const detailNow = CMP_DETAIL({ id: 'cp-5', status: 'submitted', is_draft: false, is_editable: false });
const api = createCrmApi('complaint', () => detailNow);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => api.handler(...a) }));

import ComplaintDetail from './ComplaintDetail';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintDetail complaintId="cp-5" />
    </QueryClientProvider>,
  );
}

const DO_NUMBER = 'REPPS2605-0012';

beforeEach(() => cleanup());

describe('ComplaintDetail, limited user, fulfilment DOs tab', () => {
  it('(fixture guard) the portal form renders Details / Comments / Revisions tabs', async () => {
    mount();
    await screen.findByRole('tab', { name: /^Revisions/ });
    const names = screen.getAllByRole('tab').map((t) => (t.textContent ?? '').trim());
    expect(names[0]).toMatch(/^Details/);
    expect(names.some((n) => /^Comments/.test(n))).toBe(true);
  });

  it('has a "Fulfilment DOs" tab after Details / Comments / Revisions', async () => {
    mount();
    await screen.findByRole('tab', { name: /Fulfilment DOs/ });
    const names = screen.getAllByRole('tab').map((t) => (t.textContent ?? '').trim());
    expect(names[0]).toMatch(/^Details/);
    expect(names[names.length - 1]).toMatch(/^Fulfilment DOs/);
    expect(names.findIndex((n) => /^Comments/.test(n))).toBeGreaterThan(-1);
    expect(names.findIndex((n) => /^Revisions/.test(n))).toBeGreaterThan(-1);
    expect(names.findIndex((n) => /^Fulfilment DOs/.test(n))).toBeGreaterThan(
      names.findIndex((n) => /^Revisions/.test(n)),
    );
  });

  it('the DO list is no longer below the form: nothing until the tab is opened', async () => {
    mount();
    await screen.findByRole('tab', { name: /Fulfilment DOs/ });
    expect(screen.queryByText(DO_NUMBER)).toBeNull();
  });

  it('opening the tab shows the DO number as plain text', async () => {
    const { container } = mount();
    await userEvent.setup().click(await screen.findByRole('tab', { name: /Fulfilment DOs/ }));
    const number = await screen.findByText(DO_NUMBER);
    expect(number.closest('a')).toBeNull();
    expect(number.closest('[role="tabpanel"]')).not.toBeNull();
    expect(container.querySelector('a[href*="/order"]')).toBeNull();
  });

  it('is read-only: no edit / link / unlink / delete action in the tab', async () => {
    mount();
    await userEvent.setup().click(await screen.findByRole('tab', { name: /Fulfilment DOs/ }));
    await screen.findByText(DO_NUMBER);
    const panel = screen.getByRole('tabpanel');
    expect(panel.querySelectorAll('a').length).toBe(0);
    for (const b of within(panel).queryAllByRole('button')) {
      const name = (b.getAttribute('aria-label') || b.textContent || '').trim();
      expect(name, `unexpected action "${name}"`).not.toMatch(/edit|link|unlink|delete|remove|add/i);
    }
    expect(within(panel).queryByText(/unlink/i)).toBeNull();
  });

  it('going back to Details hides the DO list again', async () => {
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: /Fulfilment DOs/ }));
    await screen.findByText(DO_NUMBER);
    await user.click(screen.getByRole('tab', { name: /^Details/ }));
    expect(screen.queryByText(DO_NUMBER)).toBeNull();
  });
});
