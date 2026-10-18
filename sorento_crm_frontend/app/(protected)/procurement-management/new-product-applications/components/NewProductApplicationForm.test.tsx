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
  inquiryOptions: vi.fn(async (..._a: unknown[]): Promise<unknown[]> => []),
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
    uploadImage: { mutateAsync: mock.upload, isPending: false },
    copyImage: { mutateAsync: mock.copy, isPending: false },
    deleteImage: { mutateAsync: mock.del, isPending: false },
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
  searchStockInquiryOptions: (q: string) => mock.inquiryOptions(q),
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
  mock.attachments.mockReset();
  mock.upload.mockReset();
  mock.copy.mockReset();
  mock.del.mockReset();
  mock.inquiryOptions.mockReset();
  mock.inquiryOptions.mockResolvedValue([]);
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
    expect(mock.upload).toHaveBeenCalledWith({
      id: 'npa-1',
      lineId: 'l-new',
      file,
    });
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
      expect(mock.copy).toHaveBeenCalledWith({
        id: 'npa-1',
        lineId: 'l-1',
        attachmentId: 'at-9',
      }),
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
    expect(mock.del).toHaveBeenCalledWith({
      id: 'npa-1',
      lineId: 'l-1',
      linkId: 'k-1',
    });
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
      expect(mock.del).toHaveBeenCalledWith({
      id: 'npa-1',
      lineId: 'l-1',
      linkId: 'k-1',
    }),
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

  const image = (name: string, link: string) => ({
    link_id: link,
    attachment_id: `at-${link}`,
    filename: name,
    url: `/files/${link}`,
    content_type: 'image/png',
  });

  it('B1a: after removing old.png and uploading new.png, old.png stays hidden and Save deletes it once', async () => {
    const rec = saved();
    rec.lines[0].images = [image('old.png', 'k-old')];
    mock.existing = rec;
    // the server has not seen the removal yet, so its answer still lists old.png
    mock.upload.mockResolvedValue({
      ...rec,
      lines: [
        {
          ...rec.lines[0],
          images: [image('old.png', 'k-old'), image('new.png', 'k-new')],
        },
      ],
    });
    mock.del.mockResolvedValue(undefined);
    renderForm({ applicationId: 'npa-1' });

    fireEvent.click(
      await screen.findByRole('button', { name: /remove.*old\.png/i }),
    );
    fireEvent.change(screen.getByLabelText('Add image'), {
      target: {
        files: [new File(['x'], 'new.png', { type: 'image/png' })],
      },
    });
    expect(await screen.findByText('new.png')).toBeInTheDocument();
    expect(screen.queryByText('old.png')).toBeNull();

    saveDraft();
    await waitFor(() => expect(mock.del).toHaveBeenCalledTimes(1));
    expect(mock.del).toHaveBeenCalledWith({
      id: 'npa-1',
      lineId: 'l-1',
      linkId: 'k-old',
    });
  });

  it('B1b: a removed saved product plus a new one with an image sends no duplicated id and uploads to the returned id', async () => {
    mock.existing = saved();
    mock.updateAsync.mockResolvedValue({
      id: 'npa-1',
      lines: [{ id: 'l-fresh', line_no: 1, images: [] }],
    });
    mock.upload.mockResolvedValue({ id: 'npa-1', lines: [] });
    renderForm({ applicationId: 'npa-1' });

    fireEvent.click(await screen.findByRole('button', { name: /add product/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /^remove$/i })[0]);
    expect(screen.getByText('Product 1 of 1')).toBeInTheDocument();
    const file = new File(['x'], 'fresh.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Add image'), {
      target: { files: [file] },
    });
    saveDraft();

    await waitFor(() => expect(mock.updateAsync).toHaveBeenCalledTimes(1));
    const lines = mock.updateAsync.mock.calls[0][0].data.lines as {
      id?: string;
    }[];
    expect(lines).toHaveLength(1);
    expect(lines[0].id ?? null).toBeNull();
    const ids = lines.map((l) => l.id).filter(Boolean);
    expect(new Set(ids).size).toBe(ids.length);
    await waitFor(() => expect(mock.upload).toHaveBeenCalledTimes(1));
    expect(mock.upload).toHaveBeenCalledWith({
      id: 'npa-1',
      lineId: 'l-fresh',
      file,
    });
  });

  it('S4: a failed inquiry attachment fetch toasts the error and does not claim the inquiry has no images', async () => {
    mock.existing = saved();
    mock.attachments.mockRejectedValue(new Error('Could not load the inquiry files'));
    renderForm({ applicationId: 'npa-1' });
    fireEvent.click(
      await screen.findByRole('button', { name: /copy from the inquiry/i }),
    );
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error).toHaveBeenCalledWith('Could not load the inquiry files');
    expect(screen.queryByText(/no images on the inquiry/i)).toBeNull();
  });

  it('S5: with the inquiry changed but unsaved, Copy from the inquiry never reads the new inquiry', async () => {
    mock.existing = saved();
    mock.inquiryOptions.mockResolvedValue([
      { value: 'si-2', label: 'SI26-0999 - XY-9' },
    ]);
    mock.attachments.mockResolvedValue([]);
    renderForm({ applicationId: 'npa-1' });

    const picker = await screen.findByRole('combobox', {
      name: /stock inquiry/i,
    });
    fireEvent.click(picker);
    fireEvent.change(picker, { target: { value: 'SI26' } });
    const option = await screen.findByText('SI26-0999 - XY-9');
    fireEvent.mouseDown(option);
    fireEvent.click(option);
    expect(await screen.findByText(/SI26-0999/)).toBeInTheDocument();

    const copy = screen.queryByRole('button', {
      name: /copy from the inquiry/i,
    });
    if (copy) {
      fireEvent.click(copy);
      await waitFor(() => expect(mock.attachments).toHaveBeenCalled());
    }
    for (const c of mock.attachments.mock.calls) expect(c[0]).toBe('si-1');
  });
});
