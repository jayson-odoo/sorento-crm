/**
 * PORTAL-P4-REQUESTS S2 (P4-14, P4-25): the complaint detail gains a Revisions tab (Q6 a). The complaint page
 * moves from `FormDetailWithSLATabs` to `FormDetailTabsWithRevisions` with `revisionsKind="complaint"`:
 *  - the tab shows when the complaint type is enabled in the revision map, or the record already has a lineage;
 *  - the strip reads Details, Comments, Fulfilment DOs, Revisions, SLA Tracking;
 *  - for a LIMITED user the tab body reads the lineage from `/api/v1/my-requests/submissions/complaint/<id>/revisions`.
 * Modelled on FormDetailTabsWithRevisions.test.tsx.
 */
import React from 'react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mapMock = vi.fn();
vi.mock('./useRevisionEnabledMap', () => ({ useRevisionEnabledMap: () => mapMock() }));
vi.mock('./FormSLATrackingTab', () => ({ __esModule: true, default: () => <div data-testid="sla" /> }));
vi.mock('@/components/common/comments/FormComments', () => ({ FormComments: () => <div>thread</div> }));
vi.mock('@/hooks/useFormComments', () => ({ useFormCommentsQuery: () => ({ data: [] }) }));

const complaintMock = vi.fn();
vi.mock('@/app/(protected)/complaint-management/complaints/hooks/useComplaints', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useComplaint: (...a: unknown[]) => complaintMock(...a),
}));
vi.mock('@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useStockInquiry: () => ({ data: undefined }),
}));
vi.mock('@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  usePurchaseRequest: () => ({ data: undefined }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import FormDetailTabsWithRevisions from './FormDetailTabsWithRevisions';
import type { FormRevisionsKind } from './FormRevisionsTab';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FormDetailTabsWithRevisions
        sourceEntityType="complaint"
        sourceEntityId="cp-1"
        revisionsKind={'complaint' as FormRevisionsKind}
        commentsKind="complaint"
        extraTabs={[{ value: 'fulfilment', label: 'Fulfilment DOs', content: <div>dos</div> }]}
      >
        <div>Details content</div>
      </FormDetailTabsWithRevisions>
    </QueryClientProvider>,
  );
}
const tabs = () => screen.getAllByRole('tab').map((t) => t.textContent);

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  held = new Set();
  complaintMock.mockReturnValue({ data: undefined, isLoading: false });
  apiFetch.mockImplementation(async () =>
    new Response(JSON.stringify({ items: [], revision_no: 0 }), { status: 200, headers: { 'content-type': 'application/json' } }),
  );
});

describe('Revisions tab on the complaint shell', () => {
  it('shows when the complaint type is enabled, between Fulfilment DOs and SLA Tracking', () => {
    mapMock.mockReturnValue({ data: { complaint: true } });
    mount();
    expect(tabs()).toEqual(['Details', 'Comments (0)', 'Fulfilment DOs', 'Revisions', 'SLA Tracking']);
  });

  it('is hidden when the type is disabled and the record was never revised', () => {
    mapMock.mockReturnValue({ data: { complaint: false } });
    complaintMock.mockReturnValue({ data: { revision_no: 0 }, isLoading: false });
    mount();
    expect(tabs()).not.toContain('Revisions');
  });

  it('stays when the type is disabled but the record already has a lineage', () => {
    mapMock.mockReturnValue({ data: { complaint: false } });
    complaintMock.mockReturnValue({ data: { revision_no: 2 }, isLoading: false });
    mount();
    expect(tabs()).toContain('Revisions');
  });

  it('limited user: the tab body reads the lineage through my-requests, not a staff route', async () => {
    held = new Set(['complaint_management.complaints.view_own']);
    mapMock.mockReturnValue({ data: { complaint: true } });
    complaintMock.mockReturnValue({ data: { id: 'cp-1', revision_no: 0, status: 'processed_by_cs' }, isLoading: false });
    mount();
    await userEvent.setup().click(screen.getByRole('tab', { name: 'Revisions' }));
    await waitFor(() =>
      expect(apiFetch.mock.calls.map((c) => String(c[0]))).toContain('/api/v1/my-requests/submissions/complaint/cp-1/revisions'),
    );
    expect(apiFetch.mock.calls.map((c) => String(c[0])).filter((u) => /complaints?(-management)?\/.*revisions/.test(u) && !u.includes('my-requests'))).toEqual([]);
  });
});

describe('the complaint page wiring', () => {
  it('[id]/page.tsx wraps the detail in FormDetailTabsWithRevisions with revisionsKind="complaint"', () => {
    const src = readFileSync(join(process.cwd(), 'app/(protected)/complaint-management/complaints/[id]/page.tsx'), 'utf8');
    expect(src).toContain('FormDetailTabsWithRevisions');
    expect(src).toMatch(/revisionsKind=["{']+complaint/);
    expect(src).toContain('commentsKind="complaint"');
    expect(src).toContain('Fulfilment DOs');
  });
});
