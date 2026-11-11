/**
 * CERT-TAB-UX: the certificate box editor.
 *
 * Owner, 11 Nov 2026: no "Remove box" button (select + Delete, or right-click > Delete); a one-click
 * "Go to box"; Save is the page's obvious primary CTA with a visible unsaved/saved state; no
 * "Suggested, check". The PdfViewer is replaced by a stub that draws page 1's overlay only.
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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1/certification/cert-1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/components/common/PdfViewer', () => ({
  PdfViewer: ({ renderPageOverlay }: { renderPageOverlay?: (page: number) => React.ReactNode }) => (
    <div data-testid="pdf-viewer" className="relative">
      {renderPageOverlay?.(1)}
    </div>
  ),
}));
vi.mock('@/app/(protected)/master-data-management/certificates/components/CoverageCodeEditor', () => ({
  CoverageCodeEditor: ({ code }: { code: string | null }) => <span>{code}</span>,
}));

const saveBoxes = { mutate: vi.fn(), isPending: false };
const detailQuery = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useQuotationCertificates', () => ({
  quotationCertificateKey: (d: string, c: string) => ['quotation-certificate', d, c],
  useQuotationCertificate: (...a: unknown[]) => detailQuery(...a),
  useQuotationCertificateMutations: () => ({
    saveBoxes,
    resetBoxes: { mutate: vi.fn(), isPending: false },
    setSend: { mutate: vi.fn(), isPending: false },
  }),
}));

import { CertificateReader, boxOrder, revealInViewer } from '../CertificateReader';

const box = (over: Record<string, unknown> = {}) => ({
  page: 1,
  x: 0.1,
  y: 0.3,
  w: 0.5,
  h: 0.05,
  product_id: 'prod-1',
  ...over,
});

function detail(over: Record<string, unknown> = {}) {
  return {
    certificate_id: 'cert-1',
    also_filed_as: [],
    scheme: 'PPS',
    certificate_number: '01816FC',
    title: null,
    certifying_body: 'IKRAM',
    valid_until: '2027-04-01',
    validity_state: 'valid',
    source: 'auto',
    marked: { count: 2, state: 'found' },
    send_to_customer: true,
    has_file: true,
    verified: true,
    revision_id: 'rev-1',
    page_count: 1,
    has_text: true,
    can_edit: true,
    can_edit_defaults: true,
    box_source: 'default',
    boxes: [box({ y: 0.6 }), box({ y: 0.2, product_id: 'prod-2' })],
    products: [
      {
        product_id: 'prod-1',
        product_code: 'SRTWCY8840-SH',
        coverage_id: 'cov-1',
        model_code: 'WCY 8840',
        model_code_source: 'ai',
        code_used: 'WCY 8840',
        number_only: false,
        state: 'found',
      },
      {
        product_id: 'prod-2',
        product_code: 'SRTWB1515',
        coverage_id: 'cov-2',
        model_code: 'WB 1515',
        model_code_source: 'manual',
        code_used: 'WB 1515',
        number_only: false,
        state: 'found',
      },
      {
        product_id: 'prod-3',
        product_code: 'SRTHOSE',
        coverage_id: 'cov-3',
        model_code: null,
        model_code_source: null,
        code_used: null,
        number_only: false,
        state: 'code_needed',
      },
    ],
    ...over,
  };
}

function renderReader(data = detail()) {
  detailQuery.mockReturnValue({ data, isLoading: false, error: null });
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <CertificateReader projectId="p1" documentId="d1" certificateId="cert-1" />
    </QueryClientProvider>,
  );
}

const boxesOnPage = () => document.querySelectorAll('[data-box-index]');

beforeEach(() => {
  saveBoxes.mutate.mockReset();
  detailQuery.mockReset();
});

describe('CertificateReader (CERT-TAB-UX)', () => {
  it('has no Remove box button, keeps Draw box', () => {
    renderReader();
    expect(screen.queryByRole('button', { name: /remove box/i })).toBeNull();
    expect(screen.getByRole('button', { name: /draw box/i })).toBeInTheDocument();
  });

  it('never says Suggested', () => {
    renderReader();
    expect(document.body.textContent).not.toMatch(/suggested/i);
    expect(screen.getAllByText('Marked').length).toBe(2);
  });

  it('deletes a selected box with the Delete key', () => {
    renderReader();
    expect(boxesOnPage()).toHaveLength(2);
    const first = boxesOnPage()[0] as HTMLElement;
    fireEvent.pointerDown(first, { button: 0, clientX: 1, clientY: 1 });
    fireEvent.pointerUp(first);
    fireEvent.keyDown(document, { key: 'Delete' });
    expect(boxesOnPage()).toHaveLength(1);
  });

  it('deletes a box from its right-click menu', async () => {
    renderReader();
    fireEvent.contextMenu(boxesOnPage()[1] as HTMLElement);
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }));
    await waitFor(() => expect(boxesOnPage()).toHaveLength(1));
  });

  it('a Delete key while a box menu is open removes nothing under the menu', async () => {
    renderReader(detail({ boxes: [box({ y: 0.1 }), box({ y: 0.3 }), box({ y: 0.5 })] }));
    fireEvent.contextMenu(boxesOnPage()[0] as HTMLElement);
    const item = await screen.findByRole('menuitem', { name: /delete/i });
    fireEvent.keyDown(item, { key: 'Delete' });
    expect(boxesOnPage()).toHaveLength(3);
    fireEvent.click(item);
    await waitFor(() => expect(boxesOnPage()).toHaveLength(2));
  });

  it('Delete on a focused box removes that box, not the selected one', () => {
    renderReader(detail({ boxes: [box({ y: 0.1 }), box({ y: 0.3, product_id: 'prod-2' })] }));
    const [a, b] = Array.from(boxesOnPage()) as HTMLElement[];
    fireEvent.pointerDown(a, { button: 0, clientX: 1, clientY: 1 });
    fireEvent.pointerUp(a);
    b.focus();
    fireEvent.keyDown(b, { key: 'Delete' });
    const left = Array.from(boxesOnPage()) as HTMLElement[];
    expect(left).toHaveLength(1);
    // Box a (y 0.1, top 10%) is the one left.
    expect(left[0].style.top).toBe('10%');
  });

  it('offers no menu and no delete when the viewer cannot edit', () => {
    renderReader(detail({ can_edit: false }));
    fireEvent.contextMenu(boxesOnPage()[0] as HTMLElement);
    expect(screen.queryByRole('menuitem', { name: /delete/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /save boxes/i })).toBeNull();
  });

  it('puts Save boxes in the page header as the primary CTA with an unsaved state', () => {
    renderReader();
    const save = screen.getByRole('button', { name: /save boxes/i });
    // In the page header beside the title, not down in the products panel.
    expect(save.closest('aside')).toBeNull();
    expect(screen.getAllByRole('button', { name: /save boxes/i })).toHaveLength(1);
    expect(save).toBeDisabled();
    expect(screen.queryByText('Unsaved changes')).toBeNull();
    fireEvent.contextMenu(boxesOnPage()[0] as HTMLElement);
    fireEvent.click(screen.getByRole('menuitem', { name: /delete/i }));
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(save).toBeEnabled();
    fireEvent.click(save);
    expect(saveBoxes.mutate).toHaveBeenCalledTimes(1);
    const [, options] = saveBoxes.mutate.mock.calls[0];
    (options as { onSuccess: () => void }).onSuccess();
    return waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument());
  });

  it('opens at the first box, in reading order', async () => {
    renderReader();
    // boxes[1] (y 0.2) reads before boxes[0] (y 0.6).
    await waitFor(() => expect(document.querySelector('[data-flashed]')).not.toBeNull());
    expect(document.querySelector('[data-flashed]')?.getAttribute('data-box-index')).toBe('1');
  });

  it('jumps to a product box in one click and outlines it', async () => {
    renderReader();
    fireEvent.click(screen.getByRole('button', { name: /go to the box of SRTWCY8840-SH/i }));
    await waitFor(() =>
      expect(document.querySelector('[data-flashed]')?.getAttribute('data-box-index')).toBe('0'),
    );
  });

  it('shows Not marked, and no Go to box, for a product whose box was deleted', () => {
    const d = detail();
    d.products[0].state = 'unmarked';
    renderReader({ ...d, boxes: [box({ y: 0.2, product_id: 'prod-2' })] });
    expect(screen.getByText('Not marked')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /go to the box of SRTWCY8840-SH/i })).toBeNull();
  });

  it('offers Go to box only for a product that has a box', () => {
    renderReader();
    expect(screen.getByRole('button', { name: /go to the box of SRTWB1515/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /go to the box of SRTHOSE/i })).toBeNull();
  });
});

describe('boxOrder', () => {
  it('orders by page, then top to bottom, and finds merged boxes by product_ids', () => {
    const boxes = [
      box({ page: 2, y: 0.1 }),
      box({ page: 1, y: 0.5, product_id: null, product_ids: ['prod-1', 'prod-2'] }),
      box({ page: 1, y: 0.2, product_id: 'prod-2' }),
    ];
    expect(boxOrder(boxes)).toEqual([2, 1, 0]);
    expect(boxOrder(boxes, 'prod-1')).toEqual([1, 0]);
    expect(boxOrder(boxes, 'prod-9')).toEqual([]);
  });
});

describe('revealInViewer', () => {
  it('scrolls the nearest scrolling ancestor, never the window', () => {
    const scroller = document.createElement('div');
    scroller.style.overflowY = 'auto';
    const node = document.createElement('div');
    scroller.appendChild(node);
    document.body.appendChild(scroller);
    scroller.getBoundingClientRect = () => ({ top: 0, left: 0, height: 400, width: 600 }) as DOMRect;
    node.getBoundingClientRect = () => ({ top: 900, left: 0, height: 20, width: 600 }) as DOMRect;
    const windowScroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    revealInViewer(node);
    expect(scroller.scrollTop).toBe(900 - 190);
    expect(windowScroll).not.toHaveBeenCalled();
    scroller.remove();
  });
});
