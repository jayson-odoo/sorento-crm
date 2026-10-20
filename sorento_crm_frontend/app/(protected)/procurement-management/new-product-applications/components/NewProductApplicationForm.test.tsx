/**
 * NEW-PRODUCT-APP staff New / Edit form (card rules 1-3). Hooks and the network are mocked;
 * the form's own rules run: the pre-fill copies text only, an emptied number box is sent as
 * null, and a Submit the server refuses keeps the user on the form with the draft saved once.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from '@/lib/toast';
import type { NewProductApplicationPrefill } from '@/types/newProductApplication';

const mock = vi.hoisted(() => ({
  push: vi.fn(),
  createAsync: vi.fn(),
  updateAsync: vi.fn(),
  submitAsync: vi.fn(),
  prefill: undefined as unknown,
  prefillError: null as Error | null,
  linkAttachment: vi.fn(),
  unlinkRun: vi.fn(),
  unlinkInputs: [] as Record<string, unknown>[],
  dialogProps: [] as Record<string, unknown>[],
  existing: undefined as unknown,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mock.push, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock('../hooks/useNewProductApplications', () => ({
  useNewProductApplicationMutations: () => ({
    create: { mutateAsync: mock.createAsync, isPending: false },
    update: { mutateAsync: mock.updateAsync, isPending: false },
    submit: { mutateAsync: mock.submitAsync, isPending: false },
  }),
  useNewProductApplicationQuery: () => ({ data: mock.existing, isLoading: false }),
  useNewProductApplicationPrefillQuery: () => ({
    data: mock.prefill,
    isLoading: false,
    isError: Boolean(mock.prefillError),
    error: mock.prefillError,
  }),
  useNewProductApplicationLookups: () => ({ brands: async () => [] }),
}));
vi.mock('../services/newProductApplicationService', () => ({
  searchStockInquiryOptions: vi.fn(async () => []),
  linkNewProductApplicationAttachment: (...a: unknown[]) =>
    mock.linkAttachment(...a),
}));
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);

// The shared attachment library dialog: a stand-in that surfaces what was wired to it.
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({
  __esModule: true,
  default: (props: {
    open: boolean;
    entityId?: string;
    linkAttachment?: (entityId: string, attachmentId: string) => Promise<unknown>;
    linkedAttachmentIds?: Set<string>;
  }) => {
    mock.dialogProps.push(props as unknown as Record<string, unknown>);
    if (!props.open) return null;
    return (
      <div role="dialog" aria-label="Link attachment library">
        <button onClick={() => void props.linkAttachment?.(props.entityId!, 'at-5')}>
          Pick library file
        </button>
      </div>
    );
  },
}));
// Unlink is a server-deferred action (D7): the row action hook is the seam.
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    mock.unlinkInputs.push(input);
    return { run: mock.unlinkRun, targetId: null, isPending: false, countdown: null };
  },
}));

import NewProductApplicationForm from './NewProductApplicationForm';

const PREFILL: NewProductApplicationPrefill = {
  stock_inquiry_id: 'si-1',
  stock_inquiry_number: 'SI26-0412',
  customer_id: null,
  customer_name: 'EXAMPLE DEVELOPER SDN BHD',
  project_name: 'EXAMPLE RESIDENCE, TOWER B',
  needed_by: '2028-01-17',
  remark: null,
  lines: [
    {
      proposed_code: 'XY-1234-MB & XY-1234-BG',
      description: 'Example sinks',
      expected_qty: '55',
    },
  ],
};

function renderForm(
  props: { applicationId?: string; stockInquiryId?: string } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <NewProductApplicationForm {...props} />
    </QueryClientProvider>,
  );
}

const saveDraft = () =>
  fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
const lastBody = () => mock.createAsync.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  mock.prefill = undefined;
  mock.prefillError = null;
  mock.existing = undefined;
  mock.unlinkInputs = [];
  mock.dialogProps = [];
  mock.linkAttachment.mockReset();
  mock.linkAttachment.mockResolvedValue({});
  mock.createAsync.mockResolvedValue({ id: 'npa-1' });
  mock.updateAsync.mockResolvedValue({ id: 'npa-1' });
  mock.submitAsync.mockResolvedValue({ id: 'npa-1' });
});

describe('pre-fill from a responded stock inquiry', () => {
  it('puts the code text in line 1 and sends customer_id null', async () => {
    mock.prefill = PREFILL;
    renderForm({ stockInquiryId: 'si-1' });

    const code = await screen.findByLabelText('Product code');
    expect((code as HTMLInputElement).value).toBe('XY-1234-MB & XY-1234-BG');
    expect((screen.getByLabelText('Customer') as HTMLInputElement).value).toBe(
      'EXAMPLE DEVELOPER SDN BHD',
    );

    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    const body = lastBody();
    expect(body.customer_id).toBeNull();
    expect(body.customer_name).toBe('EXAMPLE DEVELOPER SDN BHD');
    expect(body.stock_inquiry_id).toBe('si-1');
    expect(body.lines).toHaveLength(1);
    expect(body.lines[0].proposed_code).toBe('XY-1234-MB & XY-1234-BG');
    for (const k of [
      'category_id',
      'base_uom_id',
      'item_type_id',
      'supplier_id',
      'cost_price',
      'selling_price',
      'further_description',
    ])
      expect(body.lines[0]).not.toHaveProperty(k);
  });
});

describe('number fields', () => {
  it('sends null, never 0, once the quantity is cleared, and has no cost box', async () => {
    mock.prefill = PREFILL;
    renderForm({ stockInquiryId: 'si-1' });

    const qty = (await screen.findByLabelText('Qty')) as HTMLInputElement;
    expect(qty.value).toBe('55');
    fireEvent.change(qty, { target: { value: '' } });
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();

    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    expect(lastBody().lines[0].expected_qty).toBeNull();
  });
});

describe('paper layout', () => {
  it('draws Stock Inquiry\'s table rows under the title, then one line table with Add row and remove', async () => {
    renderForm();
    expect(await screen.findByText('NEW PRODUCT APPLICATION')).toBeInTheDocument();
    expect(screen.queryByText(/PRODUCT INQUIRY FORM/)).toBeNull();
    let at = -1;
    const text = document.body.textContent ?? '';
    for (const l of [
      'REFF:',
      'DATE:',
      'SALES PERSON:',
      'STOCK INQUIRY:',
      'CUSTOMER:',
      'PROJECT:',
      'TARGET DELIVERY:',
      'REMARK:',
      'LEADTIME:',
    ]) {
      const i = text.indexOf(l, at + 1);
      expect(i, `row ${l} after ${at}`).toBeGreaterThan(at);
      at = i;
    }
    expect(screen.queryByText(/product \d+ of \d+/i)).toBeNull();
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /add row/i }));
    expect(screen.getAllByLabelText('Product type')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: /^remove row 1$/i }));
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    expect(lastBody().lines).toHaveLength(1);
  });

  it('shows LEADTIME read-only to the applicant with the waiting line, and no cost box', async () => {
    renderForm();
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByLabelText(/^lead ?time/i)).toBeNull();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
    expect(
      screen.getAllByText('Purchasing fills this after approval.').length,
    ).toBeGreaterThan(0);
  });

  it('sends only the v4 header keys and the paper line keys', async () => {
    mock.prefill = PREFILL;
    renderForm({ stockInquiryId: 'si-1' });
    await screen.findByLabelText('Product code');
    fireEvent.change(screen.getByLabelText('Dimension'), {
      target: { value: '600x400' },
    });
    fireEvent.change(screen.getByLabelText('Packing'), {
      target: { value: 'Carton' },
    });
    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    const body = lastBody();
    expect(Object.keys(body).sort()).toEqual([
      'customer_id',
      'customer_name',
      'lines',
      'needed_by',
      'project_name',
      'remark',
      'stock_inquiry_id',
    ]);
    for (const k of ['images', 'staged_images', 'removed_link_ids'])
      expect(body.lines[0]).not.toHaveProperty(k);
    expect(body.lines[0].dimension).toBe('600x400');
    expect(body.lines[0].packing).toBe('Carton');
  });
});

describe('Submit', () => {
  it('stays on the form when the server refuses, and reuses the saved draft on the next press', async () => {
    mock.prefill = PREFILL;
    mock.submitAsync.mockRejectedValueOnce(
      new Error('Product 1: enter the product type.'),
    );
    renderForm({ stockInquiryId: 'si-1' });
    await screen.findByLabelText('Product code');

    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(mock.submitAsync).toHaveBeenCalledTimes(1));
    expect(mock.push).not.toHaveBeenCalled();
    expect(mock.createAsync).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(mock.submitAsync).toHaveBeenCalledTimes(2));
    expect(mock.createAsync).toHaveBeenCalledTimes(1);
    expect(mock.updateAsync).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(mock.push).toHaveBeenCalledWith(expect.stringContaining('npa-1')),
    );
  });
});

describe('pre-fill failure', () => {
  it('says why in a toast and leaves a usable empty form', async () => {
    mock.prefillError = new Error('That stock inquiry could not be loaded.');
    renderForm({ stockInquiryId: 'si-gone' });

    const code = (await screen.findByLabelText(
      'Product code',
    )) as HTMLInputElement;
    expect(code.value).toBe('');
    expect(toast.error).toHaveBeenCalledWith(
      'That stock inquiry could not be loaded.',
    );
    fireEvent.change(code, { target: { value: 'XY-1' } });
    expect(code.value).toBe('XY-1');
  });
});


const FILE = {
  link_id: 'k-1',
  attachment_id: 'at-1',
  filename: 'sample-doc.pdf',
  url: '/files/1',
  content_type: 'application/pdf',
};
const savedDraft = (over: Record<string, unknown> = {}) => ({
  id: 'npa-1',
  status: 'draft',
  status_label: 'Draft',
  source: 'staff',
  application_no: 'NPA-000001',
  applicant_name: 'Owner',
  created_at: '2026-10-17T01:00:00',
  stock_inquiry_id: null,
  customer_id: null,
  customer_name: 'EXAMPLE DEVELOPER SDN BHD',
  project_name: null,
  needed_by: null,
  remark: null,
  lead_time: null,
  attachments: [FILE],
  lines: [
    { id: 'l-1', line_no: 1, proposed_code: 'XY-1', description: 'First' },
    { id: 'l-2', line_no: 2, proposed_code: 'XY-2', description: 'Second' },
  ],
  ...over,
});

describe('attachments (Stock Inquiry flow)', () => {
  it('are not offered on the unsaved create form', async () => {
    renderForm();
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByRole('button', { name: /link attachment/i })).toBeNull();
    expect(screen.queryByText('sample-doc.pdf')).toBeNull();
  });

  it('on a saved draft list the files and Link Attachment opens the library and links through the service', async () => {
    mock.existing = savedDraft();
    renderForm({ applicationId: 'npa-1' });
    expect(await screen.findByText('sample-doc.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));
    fireEvent.click(await screen.findByRole('button', { name: /pick library file/i }));
    await waitFor(() =>
      expect(mock.linkAttachment).toHaveBeenCalledWith('npa-1', 'at-5'),
    );
    const last = mock.dialogProps.at(-1) as { linkedAttachmentIds?: Set<string> };
    expect(last.linkedAttachmentIds?.has('at-1')).toBe(true);
  });

  it('unlink is a deferred row action, never a confirm dialog', async () => {
    mock.existing = savedDraft();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderForm({ applicationId: 'npa-1' });
    fireEvent.click(
      await screen.findByRole('button', { name: /unlink sample-doc\.pdf/i }),
    );
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(mock.unlinkRun).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'k-1' }),
    );
    expect(
      mock.unlinkInputs.some(
        (i) => i.actionKey === 'new_product_application_attachment.unlink',
      ),
    ).toBe(true);
    confirmSpy.mockRestore();
  });
});

describe('products by id after a save', () => {
  it('a removed saved row and a new row: ids sent in body order, no duplicates on the next save', async () => {
    mock.existing = savedDraft();
    const after = {
      id: 'npa-1',
      lines: [
        { id: 'l-2', line_no: 1 },
        { id: 'l-new', line_no: 2 },
      ],
    };
    mock.updateAsync.mockResolvedValue(after);
    renderForm({ applicationId: 'npa-1' });
    fireEvent.click(
      await screen.findByRole('button', { name: /^remove row 1$/i }),
    );
    fireEvent.click(screen.getByRole('button', { name: /add row/i }));
    saveDraft();
    await waitFor(() => expect(mock.updateAsync).toHaveBeenCalledTimes(1));
    expect(
      (mock.updateAsync.mock.calls[0][0].data.lines as { id?: string }[]).map(
        (l) => l.id ?? null,
      ),
    ).toEqual(['l-2', null]);
    saveDraft();
    await waitFor(() => expect(mock.updateAsync).toHaveBeenCalledTimes(2));
    expect(
      (mock.updateAsync.mock.calls[1][0].data.lines as { id?: string }[]).map(
        (l) => l.id,
      ),
    ).toEqual(['l-2', 'l-new']);
  });
});
