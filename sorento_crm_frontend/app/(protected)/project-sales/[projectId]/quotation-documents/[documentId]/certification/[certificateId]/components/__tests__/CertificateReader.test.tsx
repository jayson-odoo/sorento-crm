/**
 * CERT-TAB-UX: the certificate box editor.
 *
 * Owner, 11 Nov 2026: no "Remove box" button (select + Delete, or right-click > Delete); a one-click
 * "Go to box"; Save is the page's obvious primary CTA with a visible unsaved/saved state; no
 * "Suggested, check". The PdfViewer is replaced by a stub that draws page 1's overlay only.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

const router = { push: vi.fn(), replace: vi.fn(), back: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/project-sales/p1/quotation-documents/d1/certification/cert-1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
/** Set per test: the stub draws its pages (and their boxes) only after this many ms, the way the
 *  real viewer draws them once the file has loaded. 0 draws them at once. */
const pdf = { loadMs: 0 };
function PdfViewerStub({ renderPageOverlay }: { renderPageOverlay?: (page: number) => React.ReactNode }) {
  const [ready, setReady] = React.useState(pdf.loadMs === 0);
  React.useEffect(() => {
    if (ready) return;
    const timer = window.setTimeout(() => setReady(true), pdf.loadMs);
    return () => window.clearTimeout(timer);
  }, [ready]);
  return (
    <div data-testid="pdf-viewer" className="relative">
      {ready && renderPageOverlay?.(1)}
    </div>
  );
}
vi.mock('@/components/common/PdfViewer', () => ({ PdfViewer: PdfViewerStub }));
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
  pdf.loadMs = 0;
  router.push.mockReset();
  router.replace.mockReset();
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

// ---------------------------------------------------------- CERT-TAB-FOLLOWUPS

describe('every open lands on the first box', () => {
  /** The dev server runs React StrictMode (next.config.mjs reactStrictMode), and a certificate
   *  opened before is already cached, so its data is there on the first render. */
  function openStrict(certificateId: string, data: ReturnType<typeof detail>, client = new QueryClient()) {
    detailQuery.mockReturnValue({ data, isLoading: false, error: null });
    const tree = (id: string) => (
      <React.StrictMode>
        <QueryClientProvider client={client}>
          <CertificateReader projectId="p1" documentId="d1" certificateId={id} />
        </QueryClientProvider>
      </React.StrictMode>
    );
    const view = render(tree(certificateId));
    return { ...view, switchTo: (id: string) => view.rerender(tree(id)) };
  }
  const flashedIndex = () => document.querySelector('[data-flashed]')?.getAttribute('data-box-index');

  it('lands on the first box when the data is cached and the file is still loading', async () => {
    pdf.loadMs = 30;
    openStrict('cert-1', detail());
    await waitFor(() => expect(flashedIndex()).toBe('1'));
  });

  it('lands again on a second open of the same certificate', async () => {
    pdf.loadMs = 30;
    const client = new QueryClient();
    const first = openStrict('cert-1', detail(), client);
    await waitFor(() => expect(flashedIndex()).toBe('1'));
    first.unmount();
    openStrict('cert-1', detail(), client);
    await waitFor(() => expect(flashedIndex()).toBe('1'));
  });

  it('lands on the new certificate first box after switching certificates', async () => {
    pdf.loadMs = 30;
    const view = openStrict('cert-1', detail());
    await waitFor(() => expect(flashedIndex()).toBe('1'));
    detailQuery.mockReturnValue({
      data: detail({
        certificate_id: 'cert-2',
        revision_id: 'rev-2',
        boxes: [box({ y: 0.7 }), box({ y: 0.5 }), box({ y: 0.1, product_id: 'prod-2' })],
      }),
      isLoading: false,
      error: null,
    });
    view.switchTo('cert-2');
    await waitFor(() => expect(flashedIndex()).toBe('2'));
  });

  it('a certificate with no boxes opens with nothing outlined and nothing waiting', async () => {
    pdf.loadMs = 30;
    openStrict('cert-1', detail({ boxes: [] }));
    await new Promise((r) => setTimeout(r, 80));
    expect(document.querySelector('[data-flashed]')).toBeNull();
  });
});

describe('unsaved boxes ask before leaving (shared useUnsavedChangesGuard)', () => {
  const LIST = '/project-sales/p1/quotation-documents/d1/certification';
  const leaveTitle = () => screen.queryByText('Leave with unsaved changes?');
  /** Delete a box, which leaves an unsaved change. */
  async function makeUnsaved() {
    fireEvent.contextMenu(boxesOnPage()[0] as HTMLElement);
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }));
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    // The box menu hides the page from the accessibility tree until it has closed.
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
  }
  function click(link: Element) {
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    act(() => {
      link.dispatchEvent(event);
    });
    return event;
  }
  const went = () => [...router.push.mock.calls, ...router.replace.mock.calls].map((c) => c[0]);
  /** A link outside the reader: the sidebar, or another certificate. */
  function outsideLink(href: string) {
    const a = document.createElement('a');
    a.href = href;
    a.textContent = 'outside';
    document.body.appendChild(a);
    return a;
  }
  afterEach(() => {
    document.querySelectorAll('body > a').forEach((a) => a.remove());
    vi.restoreAllMocks();
  });

  it('closing the editor (Back to certification) asks, Keep editing keeps the changes', async () => {
    renderReader();
    await makeUnsaved();
    const back = screen.getByRole('link', { name: /back to certification/i });
    expect(click(back).defaultPrevented).toBe(true);
    expect(leaveTitle()).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    // The dialog animates out.
    await waitFor(() => expect(leaveTitle()).toBeNull());
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(went()).toEqual([]);
  });

  it('Leave without saving goes back to the certification list', async () => {
    renderReader();
    await makeUnsaved();
    click(screen.getByRole('link', { name: /back to certification/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Leave without saving' }));
    expect(went()).toEqual([LIST]);
  });

  it('a breadcrumb asks first', async () => {
    renderReader();
    await makeUnsaved();
    const crumb = screen.getByRole('link', { name: 'Certification' });
    expect(click(crumb).defaultPrevented).toBe(true);
    expect(leaveTitle()).toBeInTheDocument();
  });

  it('switching to another certificate asks first, then opens it', async () => {
    renderReader();
    await makeUnsaved();
    expect(click(outsideLink(`${LIST}/cert-2`)).defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Leave without saving' }));
    expect(went()).toEqual([`${LIST}/cert-2`]);
  });

  it('a sidebar link asks first', async () => {
    renderReader();
    await makeUnsaved();
    expect(click(outsideLink('/project-sales')).defaultPrevented).toBe(true);
    expect(leaveTitle()).toBeInTheDocument();
  });

  it('the browser Back asks first', async () => {
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    renderReader();
    await makeUnsaved();
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
    });
    expect(leaveTitle()).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Leave without saving' }));
    expect(back).toHaveBeenCalled();
  });

  it('a refresh or closing the tab gets the browser leave prompt', async () => {
    renderReader();
    const clean = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    await makeUnsaved();
    const dirty = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });

  it('nothing asks once Save boxes has saved', async () => {
    vi.spyOn(window.history, 'back').mockImplementation(() => {});
    renderReader();
    await makeUnsaved();
    fireEvent.click(screen.getByRole('button', { name: /save boxes/i }));
    const [, options] = saveBoxes.mutate.mock.calls[0];
    act(() => (options as { onSuccess: () => void }).onSuccess());
    expect(click(screen.getByRole('link', { name: /back to certification/i })).defaultPrevented).toBe(false);
    expect(leaveTitle()).toBeNull();
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);
  });

  it('nothing asks when no box was changed', () => {
    renderReader();
    expect(click(screen.getByRole('link', { name: /back to certification/i })).defaultPrevented).toBe(false);
    expect(leaveTitle()).toBeNull();
  });

  it('keeps Save boxes the one main button and no Remove button in the editor', async () => {
    renderReader();
    await makeUnsaved();
    expect(screen.getAllByRole('button', { name: /save boxes/i })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /remove/i })).toBeNull();
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
