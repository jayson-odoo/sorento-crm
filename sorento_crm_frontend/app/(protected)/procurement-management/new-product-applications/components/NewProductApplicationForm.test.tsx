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
  upload: vi.fn(),
  copy: vi.fn(),
  del: vi.fn(),
  attachments: vi.fn(),
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
  uploadNewProductApplicationLineImage: (...a: unknown[]) =>
    mock.upload(...a),
  copyNewProductApplicationLineImage: (...a: unknown[]) => mock.copy(...a),
  deleteNewProductApplicationLineImage: (...a: unknown[]) => mock.del(...a),
  getStockInquiryAttachmentsForNpa: (...a: unknown[]) => mock.attachments(...a),
}));
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);

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
    expect(screen.queryByLabelText('Cost')).toBeNull();

    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    expect(lastBody().lines[0].expected_qty).toBeNull();
  });
});

describe('paper layout', () => {
  it('shows the paper labels and adds and removes products', async () => {
    renderForm();
    expect(await screen.findByText('NEW PRODUCT APPLICATION')).toBeInTheDocument();
    for (const l of ['REFF:', 'DATE:', 'SALES PERSON:', 'PRODUCT CODE:', 'CUSTOMER:'])
      expect(screen.getByText(l)).toBeInTheDocument();
    expect(screen.getByText('Product 1 of 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    expect(screen.getByText('Product 2 of 2')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /^remove$/i })[0]);
    expect(screen.getByText('Product 1 of 1')).toBeInTheDocument();
    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    expect(lastBody().lines).toHaveLength(1);
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
    expect(body.lines[0].dimension).toBe('600x400');
    expect(body.lines[0].packing).toBe('Carton');
  });

  it('stages an image on a new draft and uploads it with the line id the create returns', async () => {
    mock.createAsync.mockResolvedValue({
      id: 'npa-1',
      lines: [{ id: 'l-new', line_no: 1 }],
    });
    renderForm();
    const file = new File(['x'], 'sample-front.png', { type: 'image/png' });
    fireEvent.change(await screen.findByLabelText('Add image'), {
      target: { files: [file] },
    });
    expect(mock.upload).not.toHaveBeenCalled();
    saveDraft();
    await waitFor(() => expect(mock.upload).toHaveBeenCalledTimes(1));
    expect(mock.upload).toHaveBeenCalledWith('npa-1', 'l-new', file);
    expect(mock.createAsync.mock.invocationCallOrder[0]).toBeLessThan(
      mock.upload.mock.invocationCallOrder[0],
    );
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

describe('images on a saved draft', () => {
  const saved = () => ({
    id: 'npa-1',
    status: 'draft',
    status_label: 'Draft',
    source: 'staff',
    application_no: 'NPA-000001',
    applicant_name: 'Owner',
    created_at: '2026-10-17T01:00:00',
    stock_inquiry_id: 'si-1',
    stock_inquiry_number: 'SI26-0412',
    stock_inquiry_product_code: 'XY-1234-MB',
    customer_id: null,
    customer_name: 'EXAMPLE DEVELOPER SDN BHD',
    project_name: null,
    needed_by: null,
    remark: null,
    lead_time: null,
    lines: [
      {
        id: 'l-1',
        line_no: 1,
        proposed_code: 'XY-1234-MB',
        description: 'Example sink',
        images: [
          {
            link_id: 'k-1',
            attachment_id: 'at-1',
            filename: 'sample-front.png',
            url: '/files/1',
            content_type: 'image/png',
          },
        ],
      },
    ],
  });

  it('Copy from the inquiry lists the inquiry attachments and a pick copies it to the line', async () => {
    mock.existing = saved();
    mock.attachments.mockResolvedValue([
      { attachment_id: 'at-9', filename: 'inquiry-sketch.png' },
    ]);
    mock.copy.mockResolvedValue({});
    renderForm({ applicationId: 'npa-1' });

    fireEvent.click(
      await screen.findByRole('button', { name: /copy from the inquiry/i }),
    );
    const pick = await screen.findByText('inquiry-sketch.png');
    expect(mock.attachments).toHaveBeenCalledWith('si-1');
    expect(mock.copy).not.toHaveBeenCalled();
    fireEvent.click(pick);
    await waitFor(() =>
      expect(mock.copy).toHaveBeenCalledWith('npa-1', 'l-1', 'at-9'),
    );
  });

  it('removing an image only stages it: hidden at once, nothing sent until Save as draft', async () => {
    mock.existing = saved();
    mock.del.mockResolvedValue(undefined);
    const { unmount } = renderForm({ applicationId: 'npa-1' });

    fireEvent.click(
      await screen.findByRole('button', {
        name: /remove.*sample-front\.png/i,
      }),
    );
    expect(screen.queryByText('sample-front.png')).toBeNull();
    expect(mock.del).not.toHaveBeenCalled();

    saveDraft();
    await waitFor(() => expect(mock.del).toHaveBeenCalledTimes(1));
    expect(mock.del).toHaveBeenCalledWith('npa-1', 'l-1', 'k-1');
    expect(mock.updateAsync.mock.invocationCallOrder[0]).toBeLessThan(
      mock.del.mock.invocationCallOrder[0],
    );
    unmount();
  });

  it('applies a staged removal on Submit too', async () => {
    mock.existing = saved();
    mock.del.mockResolvedValue(undefined);
    renderForm({ applicationId: 'npa-1' });
    fireEvent.click(
      await screen.findByRole('button', { name: /remove.*sample-front\.png/i }),
    );
    expect(mock.del).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() =>
      expect(mock.del).toHaveBeenCalledWith('npa-1', 'l-1', 'k-1'),
    );
    expect(mock.del).toHaveBeenCalledTimes(1);
  });

  it('leaving without saving removes nothing', async () => {
    mock.existing = saved();
    const { unmount } = renderForm({ applicationId: 'npa-1' });
    fireEvent.click(
      await screen.findByRole('button', { name: /remove.*sample-front\.png/i }),
    );
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    unmount();
    expect(mock.del).not.toHaveBeenCalled();
  });
});
