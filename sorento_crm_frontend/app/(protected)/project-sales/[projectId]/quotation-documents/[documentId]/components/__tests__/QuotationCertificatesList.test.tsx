/**
 * QUOTE-CERT-TAB FE-2 red test: the Certification tab list.
 *
 * Written BEFORE the component. Contract of this file:
 *   Component  `QuotationCertificatesList` (named export of ../QuotationCertificatesList), props `{ projectId, documentId }`.
 *   Hook       `_shared/hooks/useQuotationCertificates` exports `useQuotationCertificates(projectId, documentId)`
 *              returning `{ data, isLoading, error, refetch }`; `data` = `{ can_edit, can_edit_defaults, items: Row[] }`.
 *   List       `PanelDataGrid`; scheme, number, a validity badge, and marked text that carries the count and the
 *              state in words ("2 rows, found").
 *   Toolbar    "Download certificates PDF"; "Add certificate" only when `can_edit`.
 *   Empty      heading "No certificates" and the hint "None of the quoted products has a certificate on file."
 *   Remove     the row menu deferred action `quotation_certificate.remove` (entity type `quotation_certificate`,
 *              entity id = the document id, payload `{ certificate_id }`): no confirm dialog.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1/certification',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const createPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...a: unknown[]) => createPendingAction(...a),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));

const useQuotationCertificates = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useQuotationCertificates', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>().catch(() => ({}));
  return {
    ...actual,
    useQuotationCertificates: (...a: unknown[]) => useQuotationCertificates(...a),
  };
});

import { QuotationCertificatesList } from '../QuotationCertificatesList';

function row(over: Record<string, unknown> = {}) {
  return {
    certificate_id: 'cert-1',
    also_filed_as: [],
    scheme: 'PPS',
    certificate_number: 'ZZT-0119',
    title: 'Sanitary ware',
    certifying_body: 'IKRAM',
    valid_until: '2027-04-01',
    validity_state: 'valid',
    source: 'auto',
    products: [
      { product_id: 'prod-1', product_code: 'SRTWB1515' },
      { product_id: 'prod-2', product_code: 'SRTWC8355' },
    ],
    marked: { count: 2, state: 'found' },
    send_to_customer: true,
    has_file: true,
    ...over,
  };
}

function data(items: unknown[], canEdit = true) {
  return { can_edit: canEdit, can_edit_defaults: false, items };
}

function ok(items: unknown[], canEdit = true) {
  useQuotationCertificates.mockReturnValue({
    data: data(items, canEdit),
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationCertificatesList projectId="p1" documentId="d1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockReset();
  useQuotationCertificates.mockReset();
  createPendingAction.mockReset().mockResolvedValue({
    id: 'pa-1',
    action_key: 'quotation_certificate.remove',
    entity_type: 'quotation_certificate',
    entity_id: 'd1',
    commit_at: new Date(Date.now() + 5_000).toISOString().replace('Z', ''),
    window_seconds: 5,
  });
});

describe('QuotationCertificatesList', () => {
  it('reads the list for the project and the document', () => {
    ok([row()]);
    renderList();
    expect(useQuotationCertificates).toHaveBeenCalledWith('p1', 'd1');
  });

  it('renders scheme, number, validity badge and the marked text', async () => {
    ok([
      row(),
      row({
        certificate_id: 'cert-2',
        scheme: 'SPAN',
        certificate_number: 'ZZT-0200',
        validity_state: 'expired',
        marked: { count: 0, state: 'not_found' },
      }),
    ]);
    renderList();
    expect(await screen.findByText('ZZT-0119')).toBeInTheDocument();
    expect(screen.getByText('PPS')).toBeInTheDocument();
    expect(screen.getByText('SPAN')).toBeInTheDocument();
    expect(screen.getByText('ZZT-0200')).toBeInTheDocument();
    expect(screen.getByText(/^valid$/i)).toBeInTheDocument();
    expect(screen.getByText(/expired/i)).toBeInTheDocument();
    expect(screen.getByText(/2 rows?, found/i)).toBeInTheDocument();
    // No UUID reaches the screen.
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('opens the certificate page when a row is clicked', async () => {
    ok([row()]);
    renderList();
    fireEvent.click(await screen.findByText('ZZT-0119'));
    expect(push).toHaveBeenCalledTimes(1);
    expect(push.mock.calls[0][0]).toContain('/project-sales/p1/quotation-documents/d1/certification/cert-1');
  });

  it('shows the empty state with its heading and hint', async () => {
    ok([]);
    renderList();
    expect(await screen.findByText('No certificates')).toBeInTheDocument();
    expect(screen.getByText('None of the quoted products has a certificate on file.')).toBeInTheDocument();
  });

  it('shows the download and add buttons for an editor', async () => {
    ok([row()]);
    renderList();
    expect(await screen.findByRole('button', { name: /download certificates pdf/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add certificate/i })).toBeInTheDocument();
  });

  it('hides Add certificate when the viewer cannot edit', async () => {
    ok([row()], false);
    renderList();
    await screen.findByText('ZZT-0119');
    expect(screen.queryByRole('button', { name: /add certificate/i })).toBeNull();
  });

  it('shows neither the empty state nor rows while loading', () => {
    useQuotationCertificates.mockReturnValue({ data: undefined, isLoading: true, error: null, refetch: vi.fn() });
    renderList();
    expect(screen.queryByText('No certificates')).toBeNull();
    expect(screen.queryByText('ZZT-0119')).toBeNull();
  });

  it('shows the load error instead of the empty state', async () => {
    useQuotationCertificates.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Could not load the certificates'),
      refetch: vi.fn(),
    });
    renderList();
    expect(await screen.findByText(/Could not load the certificates/)).toBeInTheDocument();
    expect(screen.queryByText('No certificates')).toBeNull();
  });

  it('Remove starts the deferred countdown with no confirm dialog', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    ok([row()]);
    renderList();
    await screen.findByText('ZZT-0119');
    const trigger = screen.getAllByRole('button', { name: /actions/i })[0];
    trigger.focus();
    fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
    fireEvent.click(await screen.findByRole('menuitem', { name: /remove/i }));
    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'quotation_certificate.remove',
        entityType: 'quotation_certificate',
        entityId: 'd1',
        payload: expect.objectContaining({ certificate_id: 'cert-1' }),
      }),
    );
    expect(confirm).not.toHaveBeenCalled();
  });
});
