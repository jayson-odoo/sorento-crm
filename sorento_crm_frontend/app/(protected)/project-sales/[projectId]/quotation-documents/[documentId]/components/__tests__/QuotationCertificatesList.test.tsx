/**
 * QUOTE-CERT-TAB FE-2 red test: the Certification tab list.
 *
 * Written BEFORE the component. Contract of this file:
 *   Component  `QuotationCertificatesList` (named export of ../QuotationCertificatesList), props `{ projectId, documentId }`.
 *   Hook       `_shared/hooks/useQuotationCertificates` exports `useQuotationCertificates(projectId, documentId)`
 *              returning `{ data, isLoading, error, refetch }`; `data` = `{ can_edit, can_edit_defaults, items: Row[] }`.
 *   List       `PanelDataGrid`; scheme, number, a validity badge, and marked text that carries the count and the
 *              state in words ("2 rows, found").
 *   Toolbar    "Download certificates PDF" (Actions menu); "Add certificate" only when `can_add`.
 *   Empty      heading "No certificates" and the hint "None of the quoted products has a certificate on file."
 *   Remove     the row's right-click menu deferred action `quotation_certificate.remove` (entity type `quotation_certificate`,
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
  return { can_edit: canEdit, can_add: canEdit, can_edit_defaults: false, items };
}

function ok(items: unknown[], canEdit = true) {
  useQuotationCertificates.mockReturnValue({
    data: data(items, canEdit),
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
}

/** Download certificates PDF lives in the toolbar's Actions menu (CERT-TAB-UX, 375px). */
async function findDownloadItem() {
  const trigger = await screen.findByRole('button', { name: /^actions$/i });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
  return screen.findByRole('menuitem', { name: /download certificates pdf/i });
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
    // CERT-TAB-UX: a marked row reads "2 rows" (no "found" / "suggested, check" words).
    expect(screen.getByText('2 rows')).toBeInTheDocument();
    expect(screen.getByText('Code not found')).toBeInTheDocument();
    // No UUID reaches the screen.
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('names the other certificates filed as the same file', async () => {
    ok([
      row({
        also_filed_as: [
          { certificate_id: 'cert-9', scheme: 'WCM', certificate_number: '000318' },
          { certificate_id: 'cert-8', scheme: 'PC', certificate_number: '000318' },
        ],
      }),
    ]);
    renderList();
    // One line per row: the other filings are in the number's tooltip, not on a second line.
    const number = await screen.findByText('ZZT-0119');
    expect(number.getAttribute('title')).toContain('Also filed as WCM 000318, PC 000318');
    expect(screen.queryByText('Also filed as WCM 000318, PC 000318')).toBeNull();
  });

  it('says nothing about other filings when there are none', async () => {
    ok([row()]);
    renderList();
    await screen.findByText('ZZT-0119');
    expect(screen.queryByText(/also filed as/i)).toBeNull();
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
    expect(await screen.findByRole('button', { name: /add certificate/i })).toBeInTheDocument();
    expect(await findDownloadItem()).toBeInTheDocument();
  });

  it('hides Add certificate when the viewer cannot edit', async () => {
    ok([row()], false);
    renderList();
    await screen.findByText('ZZT-0119');
    expect(screen.queryByRole('button', { name: /add certificate/i })).toBeNull();
  });

  it('hides Add certificate when the viewer can edit but may not read the register', async () => {
    useQuotationCertificates.mockReturnValue({
      data: { can_edit: true, can_add: false, can_edit_defaults: false, items: [row()] },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    renderList();
    await screen.findByText('ZZT-0119');
    expect(screen.queryByRole('button', { name: /add certificate/i })).toBeNull();
    expect(await findDownloadItem()).toBeInTheDocument();
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
    fireEvent.contextMenu(await screen.findByText('ZZT-0119'));
    fireEvent.click(await screen.findByRole('menuitem', { name: /remove/i }));
    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'quotation_certificate.remove',
        entityType: 'quotation_certificate',
        // One countdown per certificate: `<document id>:<certificate id>`.
        entityId: 'd1:cert-1',
      }),
    );
    expect(confirm).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------- CERT-TAB-UX

  it('keeps every row to one line: the description is a tooltip, not a second line', async () => {
    ok([row()]);
    renderList();
    const number = await screen.findByText('ZZT-0119');
    expect(number.getAttribute('title')).toContain('Sanitary ware');
    expect(screen.queryByText('Sanitary ware')).toBeNull();
  });

  it('never says Suggested', async () => {
    ok([row()]);
    renderList();
    await screen.findByText('ZZT-0119');
    expect(document.body.textContent).not.toMatch(/suggested/i);
  });

  it('searches number, scheme and quoted product codes', async () => {
    ok([
      row(),
      row({
        certificate_id: 'cert-2',
        scheme: 'SPAN',
        certificate_number: 'ZZT-0200',
        products: [{ product_id: 'prod-3', product_code: 'SRTWCY8840-SH' }],
      }),
    ]);
    renderList();
    await screen.findByText('ZZT-0119');
    fireEvent.change(screen.getByRole('searchbox', { name: /search certificates/i }), {
      target: { value: 'wcy8840' },
    });
    await waitFor(() => expect(screen.queryByText('ZZT-0119')).toBeNull());
    expect(screen.getByText('ZZT-0200')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: /search certificates/i }), {
      target: { value: 'nothing like this' },
    });
    expect(await screen.findByText('Nothing matches')).toBeInTheDocument();
  });

  it('sorts by a column header click, client-side', async () => {
    ok([
      row({ certificate_id: 'cert-b', certificate_number: 'ZZT-0300' }),
      row({ certificate_id: 'cert-a', certificate_number: 'ZZT-0100' }),
    ]);
    renderList();
    await screen.findByText('ZZT-0300');
    const order = () =>
      screen.getAllByText(/^ZZT-0[13]00$/).map((el) => el.textContent);
    expect(order()).toEqual(['ZZT-0300', 'ZZT-0100']);
    fireEvent.click(screen.getByRole('button', { name: /^certificate$/i }));
    await waitFor(() => expect(order()).toEqual(['ZZT-0100', 'ZZT-0300']));
  });

  it('opens a filter menu with Scheme, Validity, Rows marked and Source', async () => {
    ok([row()]);
    renderList();
    await screen.findByText('ZZT-0119');
    const trigger = screen.getByRole('button', { name: /filter/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
    const menu = await screen.findByRole('menu');
    const labels = Array.from(menu.querySelectorAll('label')).map((l) => l.textContent);
    expect(labels).toEqual(['Scheme', 'Validity', 'Rows marked', 'Source']);
  });
});

describe('QuotationCertificatesList filters (CERT-TAB-UX)', () => {
  async function pick(filter: string, option: string) {
    const trigger = screen.getByRole('button', { name: /^filters/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
    const combo = await screen.findByRole('combobox', { name: filter });
    fireEvent.click(combo);
    fireEvent.click(await screen.findByRole('option', { name: option }));
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
  }

  const rows = () => [
    row({ certificate_id: 'c1', certificate_number: 'ZZT-A1', scheme: 'PPS', marked: { count: 1, state: 'found' } }),
    row({ certificate_id: 'c2', certificate_number: 'ZZT-A2', scheme: 'SPAN', marked: { count: 0, state: 'not_found' } }),
    row({
      certificate_id: 'c3',
      certificate_number: 'ZZT-A3',
      scheme: 'PPS',
      verified: false,
      marked: { count: 0, state: 'not_on_certificate' },
    }),
    row({ certificate_id: 'c4', certificate_number: 'ZZT-A4', scheme: 'PPS', source: 'manual', marked: { count: 0, state: 'no_text' } }),
  ];

  const shown = () => ['ZZT-A1', 'ZZT-A2', 'ZZT-A3', 'ZZT-A4'].filter((n) => screen.queryByText(n));

  it('Rows marked: Code not found keeps not_found and the greyed not_on_certificate rows', async () => {
    ok(rows());
    renderList();
    await screen.findByText('ZZT-A1');
    await pick('Rows marked', 'Code not found');
    await waitFor(() => expect(shown()).toEqual(['ZZT-A2', 'ZZT-A3']));
  });

  it('Scheme and Source narrow the rows together', async () => {
    ok(rows());
    renderList();
    await screen.findByText('ZZT-A1');
    await pick('Scheme', 'PPS');
    await waitFor(() => expect(shown()).toEqual(['ZZT-A1', 'ZZT-A3', 'ZZT-A4']));
    await pick('Source', 'Added');
    await waitFor(() => expect(shown()).toEqual(['ZZT-A4']));
  });
});

describe('Rows marked filter buckets (owner, 11 Nov 2026)', () => {
  it('offers exactly Marked, Edited, Code not found, Code needed, No text, No file', async () => {
    const { MARKED_FILTERS } = await import('../../../../../_shared/lib/quotationCertificateDisplay');
    expect(MARKED_FILTERS.map((f) => f.label)).toEqual([
      'Marked',
      'Edited',
      'Code not found',
      'Code needed',
      'No text',
      'No file',
    ]);
  });

  it('puts each state in its bucket', async () => {
    const { markedFilterOf } = await import('../../../../../_shared/lib/quotationCertificateDisplay');
    expect(markedFilterOf('found')).toBe('marked');
    expect(markedFilterOf('edited')).toBe('edited');
    expect(markedFilterOf('not_found')).toBe('code_not_found');
    expect(markedFilterOf('not_on_certificate')).toBe('code_not_found');
    expect(markedFilterOf('code_needed')).toBe('code_needed');
    expect(markedFilterOf('no_text')).toBe('no_text');
    expect(markedFilterOf('no_file')).toBe('no_file');
    expect(markedFilterOf('none')).toBeNull();
  });

  // ---------------------------------------------------------- CERT-TAB-FOLLOWUPS

  describe('right-click row menu (owner: right-click over icons)', () => {
    it('has no Actions column and no "..." button on a row', async () => {
      ok([row()]);
      renderList();
      await screen.findByText('ZZT-0119');
      expect(screen.queryByRole('button', { name: /ZZT-0119 actions/i })).toBeNull();
      expect(screen.queryByRole('columnheader', { name: /^actions$/i })).toBeNull();
    });

    it('right-clicking a row offers Open, Download and Remove to an editor', async () => {
      ok([row()]);
      renderList();
      fireEvent.contextMenu(await screen.findByText('SRTWB1515, SRTWC8355'));
      const items = (await screen.findAllByRole('menuitem')).map((i) => i.textContent?.trim());
      expect(items).toEqual(['Open', 'Download', 'Remove']);
    });

    it('offers no Remove to a viewer without the edit right', async () => {
      ok([row()], false);
      renderList();
      fireEvent.contextMenu(await screen.findByText('ZZT-0119'));
      const items = (await screen.findAllByRole('menuitem')).map((i) => i.textContent?.trim());
      expect(items).toEqual(['Open', 'Download']);
    });

    it('Open goes to the certificate the row was right-clicked on', async () => {
      ok([row(), row({ certificate_id: 'cert-2', certificate_number: 'ZZT-0200' })]);
      renderList();
      fireEvent.contextMenu(await screen.findByText('ZZT-0200'));
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Open' }));
      expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/certification/cert-2');
    });

    it('Download is disabled when the certificate has no file', async () => {
      ok([row({ has_file: false })]);
      renderList();
      fireEvent.contextMenu(await screen.findByText('ZZT-0119'));
      const download = await screen.findByRole('menuitem', { name: 'Download' });
      expect(download).toHaveAttribute('data-disabled');
    });

    it('right-clicking outside a row leaves the browser menu alone', async () => {
      ok([row()]);
      renderList();
      await screen.findByText('ZZT-0119');
      const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
      screen.getByRole('columnheader', { name: /certificate/i }).dispatchEvent(event);
      // No app menu at all (not even an empty one), and the browser's own menu is not blocked.
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByRole('menu')).toBeNull();
      expect(event.defaultPrevented).toBe(false);
    });

    it('a long-press on a row (touch) opens the same menu for that row', async () => {
      ok([row(), row({ certificate_id: 'cert-2', certificate_number: 'ZZT-0200' })]);
      renderList();
      fireEvent.pointerDown(await screen.findByText('ZZT-0200'), { pointerType: 'touch', button: 0 });
      const items = await screen.findAllByRole('menuitem', {}, { timeout: 2000 });
      expect(items.map((i) => i.textContent?.trim())).toEqual(['Open', 'Download', 'Remove']);
      fireEvent.click(screen.getByRole('menuitem', { name: 'Open' }));
      expect(push).toHaveBeenCalledWith('/project-sales/p1/quotation-documents/d1/certification/cert-2');
    });

    it('a long-press outside a row opens no empty menu', async () => {
      ok([row()]);
      renderList();
      await screen.findByText('ZZT-0119');
      fireEvent.pointerDown(screen.getByRole('columnheader', { name: /certificate/i }), {
        pointerType: 'touch',
        button: 0,
      });
      await new Promise((r) => setTimeout(r, 900));
      expect(screen.queryByRole('menu')).toBeNull();
    });
  });
});
