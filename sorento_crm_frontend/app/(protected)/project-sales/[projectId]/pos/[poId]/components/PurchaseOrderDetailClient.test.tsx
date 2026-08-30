/**
 * The PO's page as an edit VIEW.
 *
 * The client's complaint on the quotation, which this page had too: "every addition of line
 * doesn't trigger a save, cause now i delete each line, then you ask me to confirm, then when i
 * add line, you also trigger save, very annoying, we should have an edit view imo".
 *
 * So what is pinned here is the promise that answers it: a read that cannot be typed into, an
 * Edit that turns the SAME fields into inputs in place, ONE request carrying the header and the
 * whole line set, one confirmation when that save deletes lines, and a Cancel that leaves the
 * server untouched.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectPurchaseOrder,
  PurchaseOrderLine,
} from '../../../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
let searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/pos/po1',
  useSearchParams: () => searchParams,
}));

const getProject = vi.fn();
const listPurchaseOrders = vi.fn();
const listPurchaseOrderLines = vi.fn();
const updatePurchaseOrder = vi.fn();
const deletePurchaseOrder = vi.fn();

vi.mock('../../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/projectService')
  >();
  return {
    ...actual,
    getProject: (...args: unknown[]) => getProject(...args),
    listPurchaseOrders: (...args: unknown[]) => listPurchaseOrders(...args),
    listPurchaseOrderLines: (...args: unknown[]) => listPurchaseOrderLines(...args),
    updatePurchaseOrder: (...args: unknown[]) => updatePurchaseOrder(...args),
    deletePurchaseOrder: (...args: unknown[]) => deletePurchaseOrder(...args),
    listQuotations: vi.fn(async () => []),
    listQuotationVersions: vi.fn(async () => []),
    listParties: vi.fn(async () => ({ data: [], pagination: { total: 0 } })),
  };
});

// The documents strip. Its own tests cover it; here it must simply not fetch.
vi.mock('../../../../_shared/services/poIntakeService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/poIntakeService')
  >();
  return { ...actual, listPOVersions: vi.fn(async () => []) };
});

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    custom: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

import { PurchaseOrderDetailClient } from './PurchaseOrderDetailClient';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  };
}

function po(overrides: Partial<ProjectPurchaseOrder> = {}): ProjectPurchaseOrder {
  return {
    id: 'po1',
    project_id: 'p1',
    po_number: 'PO-9001',
    po_source: 'contractor_direct',
    quotation_version_id: 'v2',
    scope_label: 'House Units',
    version_no: 2,
    issuing_party_id: 'party-1',
    issuing_party_name: 'Bina Utama Sdn Bhd',
    po_date: '2026-07-24',
    po_amount: null,
    notes: 'Phase 1 only',
    line_count: 1,
    line_total: '9000.00',
    model_mismatch_count: 0,
    price_mismatch_count: 0,
    updated_at: '2026-07-25T02:00:00',
    ...overrides,
  };
}

function line(overrides: Partial<PurchaseOrderLine> = {}): PurchaseOrderLine {
  return {
    id: 'pl1',
    po_id: 'po1',
    product_code: 'SRT-WC-01',
    description: 'Wall-hung WC',
    unit_price: '900.00',
    quantity: '10.00',
    uom: 'PCS',
    line_total: '9000.00',
    model_mismatch: false,
    price_mismatch: false,
    sort_order: 0,
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrderDetailClient projectId="p1" poId="po1" />
    </QueryClientProvider>,
  );
}

/** Into the session, from the header's one call to action. */
async function openEditor() {
  // The lines have to be on screen first: the session seeds itself from them, and a Save
  // pressed before that seeding would carry a set the user never saw.
  await screen.findByText('Wall-hung WC');
  fireEvent.click(await screen.findByRole('button', { name: /Edit the PO/i }));
  const save = await screen.findByRole('button', { name: 'Save purchase order' });
  await screen.findByRole('textbox', { name: 'Code on the PO on SRT-WC-01' });
  return save;
}

/** Into the gear, where everything that is not Edit now lives. */
async function openGear() {
  // Radix opens its menus on pointerdown, which fireEvent.click does not send.
  fireEvent.pointerDown(
    await screen.findByRole('button', { name: 'Purchase order actions' }),
    { button: 0, ctrlKey: false },
  );
  return within(await screen.findByRole('menu'));
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams();
  getProject.mockResolvedValue(project());
  listPurchaseOrders.mockResolvedValue([po()]);
  listPurchaseOrderLines.mockResolvedValue([line()]);
  updatePurchaseOrder.mockImplementation(async () => po({ po_number: 'PO-9001-A' }));
  deletePurchaseOrder.mockResolvedValue(undefined);
});

describe('PurchaseOrderDetailClient states', () => {
  it('shows a skeleton while the PO is being fetched', () => {
    listPurchaseOrders.mockReturnValue(new Promise(() => {}));

    const { container } = renderPage();

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it('says the PO could not be loaded, with the way back, when it is not in the list', async () => {
    listPurchaseOrders.mockResolvedValue([]);

    renderPage();

    expect(
      await screen.findByText(/This purchase order could not be loaded/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Back to POs/i })).toHaveAttribute(
      'href',
      '/project-sales/p1?tab=pos',
    );
  });

  it('carries the failure reason through when the list itself errored', async () => {
    listPurchaseOrders.mockRejectedValue(new Error('Failed to load purchase orders'));

    renderPage();

    expect(await screen.findByText('Failed to load purchase orders')).toBeInTheDocument();
  });

  it('reads every header field, and the lines, with nothing to type into', async () => {
    renderPage();

    expect(await screen.findByRole('heading', { name: 'PO-9001' })).toBeInTheDocument();
    // The header fields lived only in a modal before, so the record could not show them.
    expect(screen.getByText('House Units v2')).toBeInTheDocument();
    expect(screen.getByText('Bina Utama Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Phase 1 only')).toBeInTheDocument();
    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    // Read-only metadata sits in the header, never in a section that has an edit counterpart.
    expect(screen.getByText(/Last updated/i)).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save purchase order' })).toBeNull();
  });

  it('still renders every section, and no way in, for a reader', async () => {
    getProject.mockResolvedValue(project({ can_edit: false }));
    listPurchaseOrderLines.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByRole('heading', { name: 'PO-9001' })).toBeInTheDocument();
    expect(screen.getByText('Documents')).toBeInTheDocument();
    expect(screen.getByText('Lines')).toBeInTheDocument();
    expect(
      screen.getByText(/You can read this purchase order but not change it/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Purchase order actions' })).toBeNull();
  });
});

describe('PurchaseOrderDetailClient edit view', () => {
  it('swaps the header values for inputs in place, holding what was on screen', async () => {
    renderPage();
    await openEditor();

    expect(await screen.findByLabelText('PO number')).toHaveValue('PO-9001');
    expect(screen.getByLabelText('PO date')).toHaveValue('2026-07-24');
    expect(screen.getByLabelText('Notes')).toHaveValue('Phase 1 only');
    // The lines became a spreadsheet in the same move.
    expect(
      screen.getByRole('textbox', { name: 'Code on the PO on SRT-WC-01' }),
    ).toHaveValue('SRT-WC-01');
    expect(screen.getByText(/Nothing is written until you press Save/i)).toBeInTheDocument();
  });

  it('opens the session straight away when the list sent the user here to edit', async () => {
    searchParams = new URLSearchParams('edit=1');

    renderPage();

    expect(await screen.findByLabelText('PO number')).toHaveValue('PO-9001');
    expect(
      await screen.findByRole('textbox', { name: 'Code on the PO on SRT-WC-01' }),
    ).toBeInTheDocument();
  });

  it('leaves Save disabled until something actually changes', async () => {
    renderPage();
    const save = await openEditor();

    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText('PO number'), { target: { value: 'PO-9001-A' } });

    await waitFor(() => expect(save).toBeEnabled());
  });

  it('sends the header and the whole line set in ONE request', async () => {
    renderPage();
    const save = await openEditor();

    fireEvent.change(screen.getByLabelText('PO number'), { target: { value: 'PO-9001-A' } });
    fireEvent.change(
      await screen.findByRole('textbox', { name: 'Ordered at on SRT-WC-01' }),
      { target: { value: '820.00' } },
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    fireEvent.change(
      await screen.findByRole('textbox', { name: 'Code on the PO on line 2' }),
      { target: { value: 'THEIRS-7' } },
    );
    fireEvent.change(screen.getByRole('textbox', { name: 'Ordered at on line 2' }), {
      target: { value: '410.00' },
    });
    fireEvent.click(save);

    await waitFor(() => expect(updatePurchaseOrder).toHaveBeenCalledTimes(1));
    expect(updatePurchaseOrder).toHaveBeenCalledWith('po1', {
      po_number: 'PO-9001-A',
      lines: [
        {
          id: 'pl1',
          product_id: null,
          product_code: 'SRT-WC-01',
          description: 'Wall-hung WC',
          unit_price: '820.00',
          quantity: '10.00',
          uom: 'PCS',
          notes: null,
        },
        {
          product_id: null,
          product_code: 'THEIRS-7',
          description: null,
          unit_price: '410.00',
          quantity: '1',
          uom: null,
          notes: null,
        },
      ],
    });
    // Back to the read once it lands.
    await waitFor(() => expect(screen.queryByLabelText('PO number')).toBeNull());
  });

  it('sends no lines at all when only the header moved', async () => {
    renderPage();
    const save = await openEditor();

    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'Staged ordering' } });
    fireEvent.click(save);

    await waitFor(() => expect(updatePurchaseOrder).toHaveBeenCalledTimes(1));
    // A whole-set write of rows nobody touched is a real rewrite, not a no-op.
    expect(updatePurchaseOrder).toHaveBeenCalledWith('po1', { notes: 'Staged ordering' });
  });

  it('asks once, naming the count, before a save that deletes lines', async () => {
    renderPage();
    const save = await openEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Remove SRT-WC-01' }));
    fireEvent.click(save);

    expect(await screen.findByText(/Saving removes 1 line from PO-9001/i)).toBeInTheDocument();
    expect(updatePurchaseOrder).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Save and remove 1 line/i }));

    await waitFor(() => expect(updatePurchaseOrder).toHaveBeenCalledTimes(1));
    expect(updatePurchaseOrder).toHaveBeenCalledWith('po1', { lines: [] });
  });

  it('refuses to save a line that names neither a product nor a code, and says how many', async () => {
    renderPage();
    const save = await openEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Description on line 2' }), {
      target: { value: 'Something they wrote' },
    });
    fireEvent.click(save);

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'One line still needs a product or the code on the PO.',
      ),
    );
    expect(updatePurchaseOrder).not.toHaveBeenCalled();
  });

  it('refuses to save a PO with its number emptied', async () => {
    renderPage();
    const save = await openEditor();

    fireEvent.change(screen.getByLabelText('PO number'), { target: { value: '' } });
    fireEvent.click(save);

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'A PO needs its number - it is how the contractor refers to it.',
      ),
    );
    expect(updatePurchaseOrder).not.toHaveBeenCalled();
  });

  it('throws the staged work away on Cancel, and writes nothing', async () => {
    renderPage();
    await openEditor();

    fireEvent.change(screen.getByLabelText('PO number'), { target: { value: 'PO-TYPO' } });
    fireEvent.change(
      await screen.findByRole('textbox', { name: 'Ordered at on SRT-WC-01' }),
      { target: { value: '1.00' } },
    );
    expect(await screen.findByRole('heading', { name: 'PO-TYPO' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(await screen.findByRole('heading', { name: 'PO-9001' })).toBeInTheDocument();
    expect(screen.getByText('RM 900.00')).toBeInTheDocument();
    expect(screen.queryByLabelText('PO number')).toBeNull();
    expect(updatePurchaseOrder).not.toHaveBeenCalled();
  });

  it('states that sales orders already went out, before anything is saved', async () => {
    listPurchaseOrders.mockResolvedValue([po({ published_sales_order_count: 2 })]);

    renderPage();
    await openEditor();

    expect(
      await screen.findByText(
        /2 sales orders already went out from this PO\. Changing it here does not change them\./i,
      ),
    ).toBeInTheDocument();
  });

  it('moves the total with the lines while they are being edited', async () => {
    renderPage();
    await openEditor();

    fireEvent.change(await screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' }), {
      target: { value: '3' },
    });

    // The header card's own figure, not just the table footer: the reader is owed the total of
    // what is on the screen.
    await waitFor(() => expect(screen.getAllByText('RM 2,700.00').length).toBeGreaterThan(1));
  });
});

/**
 * The header standard: ONE call to action, everything else behind the gear, and a pager.
 *
 * The same standard the sales order and the delivery schedule carry, and for the client's
 * same complaint about the row of buttons that competed with each other.
 */
describe('PurchaseOrderDetailClient header', () => {
  it('offers Edit the PO, and puts the upload behind the gear', async () => {
    renderPage();

    expect(await screen.findByRole('button', { name: /Edit the PO/i })).toBeInTheDocument();
    // The upload used to be the header's solid button, competing with nothing to do.
    expect(screen.queryByRole('button', { name: /Upload a document/i })).toBeNull();

    const gear = await openGear();
    expect(gear.getByRole('menuitem', { name: /Upload a document/i })).toBeInTheDocument();
    // Destructive last.
    const items = gear.getAllByRole('menuitem');
    expect(items[items.length - 1]).toHaveTextContent('Delete this PO');
  });

  it('replaces the call to action with Cancel and Save while a session is open', async () => {
    renderPage();
    await openEditor();

    expect(screen.queryByRole('button', { name: /Edit the PO/i })).toBeNull();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save purchase order' })).toBeInTheDocument();
  });

  it('offers a reader neither a call to action nor a gear', async () => {
    getProject.mockResolvedValue(project({ can_edit: false }));

    renderPage();

    await screen.findByRole('heading', { name: 'PO-9001' });
    expect(screen.queryByRole('button', { name: /Edit the PO/i })).toBeNull();
    // An empty menu is worse than no menu.
    expect(screen.queryByRole('button', { name: 'Purchase order actions' })).toBeNull();
  });

  it('S3-03: walks the project POs the page already holds, without a second request', async () => {
    // The project's POs are in memory (the record is read out of them), so the
    // pager states the position from that list rather than asking the server.
    listPurchaseOrders.mockResolvedValue([
      po({ id: 'po0', po_number: 'PO-9000' }),
      po(),
      po({ id: 'po2', po_number: 'PO-9002' }),
    ]);
    renderPage();

    await screen.findByRole('heading', { name: 'PO-9001' });
    expect(screen.getByText('2 / 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next purchase order' }));

    expect(push).toHaveBeenCalledWith('/project-sales/p1/pos/po2');
  });

  /**
   * The pager stands down for the duration of a session, exactly as it does on the quotation
   * document. The staged work would in fact survive a step away - it lives in the session, not
   * in the table - but a Next sitting beside Cancel and Save reads like it will discard it, and
   * a control nobody dares press is worse than one that is absent.
   */
  it('stands the pager down while an edit session is open, and brings it back on Cancel', async () => {
    renderPage();

    expect(
      await screen.findByRole('button', { name: 'Next purchase order' }),
    ).toBeInTheDocument();

    await openEditor();

    expect(screen.queryByRole('button', { name: 'Next purchase order' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Previous purchase order' })).toBeNull();
    // Cancel and Save are what the header states instead.
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(
      await screen.findByRole('button', { name: 'Next purchase order' }),
    ).toBeInTheDocument();
  });
});
