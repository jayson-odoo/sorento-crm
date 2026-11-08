/**
 * Portal new product application form (NEW-PRODUCT-APP): start from the contact's own responded
 * inquiry, the line table without supplier or cost, Revise with a required reason, and the
 * read-only view once the application is with purchasing. The service module is mocked.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type {
  NewProductApplicationDetail,
  NewProductApplicationLine,
} from '@/types/newProductApplication';

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push, replace, back: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: () => void;
  }) => <button onClick={() => onSelect?.()}>{children}</button>,
}));

vi.mock('../lib/new-product-application-service', () => ({
  listMyRespondedInquiries: vi.fn(),
  getNewProductApplicationPrefill: vi.fn(),
  searchNewProductApplicationProducts: vi.fn(async () => []),
  getNewProductApplicationReuseSuggestions: vi.fn(async () => []),
  lookupNewProductApplication: vi.fn(async () => []),
  lookupNewProductApplicationCustomers: vi.fn(async () => []),
  downloadNewProductApplicationExcel: vi.fn(),
  createNewProductApplication: vi.fn(),
  updateNewProductApplication: vi.fn(),
  submitNewProductApplication: vi.fn(),
  reviseNewProductApplication: vi.fn(),
  cancelNewProductApplication: vi.fn(),
  getNewProductApplication: vi.fn(),
}));

import {
  createNewProductApplication,
  getNewProductApplication,
  getNewProductApplicationPrefill,
  listMyRespondedInquiries,
  reviseNewProductApplication,
  submitNewProductApplication,
  downloadNewProductApplicationExcel,
} from '../lib/new-product-application-service';
vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return { ...original, uploadAttachment: vi.fn() };
});
// The shared dropzone is exercised in its own tests; here only what the form wires to it.
const dz = vi.hoisted(() => ({
  props: [] as Record<string, unknown>[],
  pick: new File(['x'], 'sample-doc.pdf', { type: 'application/pdf' }),
}));
vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: (p: {
    kind: string;
    submissionId: string | null;
    attachments: unknown[];
    readOnly?: boolean;
    pendingFiles?: File[];
    onPendingFilesChange?: (f: File[]) => void;
  }) => {
    dz.props.push(p as unknown as Record<string, unknown>);
    return (
      <div
        data-testid="dropzone"
        data-kind={p.kind}
        data-submission={p.submissionId ?? ''}
        data-readonly={p.readOnly ? 'yes' : 'no'}
        data-attachments={p.attachments.length}
        data-pending={p.pendingFiles?.length ?? 0}
      >
        <button onClick={() => p.onPendingFilesChange?.([dz.pick])}>
          Drop pending file
        </button>
      </div>
    );
  },
}));

import { uploadAttachment } from '../lib/portal-client';
import NewProductApplicationForm from './NewProductApplicationForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const INQUIRY = {
  id: 'si-1',
  inquiry_number: 'SI26-0412',
  product_code: 'XY-1234-MB & XY-1234-BG',
  item_description: 'Example sinks',
  project_name: 'EXAMPLE RESIDENCE, TOWER B',
  purchasing_response: 'Supplier can make it, please apply for a new code.',
  last_responded_at: null,
};

function line(
  over: Partial<NewProductApplicationLine> = {},
): NewProductApplicationLine {
  return {
    id: 'l-1',
    line_no: 1,
    proposed_code: 'XY-1234-MB',
    description: 'Example kitchen sink',
    dimension: null,
    material: null,
    thickness: null,
    packing: null,
    brand_name: null,
    cost_price: null,
    opened_supplier_name: null,
    opened_product_id: null,
    opened_product_code: null,
    opened_product_name: null,
    opened_product_active: null,
    closed_reason: null,
    resolved_by: null,
    resolved_by_name: null,
    resolved_at: null,
    ...over,
  };
}

function detail(
  over: Partial<NewProductApplicationDetail> = {},
): NewProductApplicationDetail {
  return {
    id: 'a-1',
    application_no: 'NPA-000001',
    status: 'draft',
    status_label: 'Draft',
    source: 'portal',
    applicant_id: null,
    applicant_name: null,
    stock_inquiry_id: null,
    stock_inquiry_number: null,
    stock_inquiry_product_code: null,
    customer_id: null,
    customer_code: null,
    customer_name: 'EXAMPLE DEVELOPER SDN BHD',
    project_name: 'EXAMPLE RESIDENCE, TOWER B',
    first_line: 'XY-1234-MB',
    lines_total: 1,
    lines_done: 0,
    opened_codes: [],
    needed_by: null,
    submitted_at: null,
    created_at: '2026-10-17T01:00:00',
    updated_at: null,
    remark: null,
    lead_time: null,
    decided_at: null,
    decided_by: null,
    decided_by_name: null,
    reject_reason: null,
    revise_reason: null,
    cancelled_at: null,
    cancel_reason: null,
    completed_at: null,
    lines: [line()],
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  asMock(listMyRespondedInquiries).mockResolvedValue([INQUIRY]);
  asMock(createNewProductApplication).mockResolvedValue(detail());
  asMock(submitNewProductApplication).mockResolvedValue(
    detail({ status: 'submitted' }),
  );
});

describe('new application', () => {
  it('starts from my stock inquiry: the code text becomes the hint, no product rows, the customer stays typed text', async () => {
    asMock(getNewProductApplicationPrefill).mockResolvedValue({
      stock_inquiry_id: 'si-1',
      stock_inquiry_number: 'SI26-0412',
      customer_id: null,
      customer_name: 'EXAMPLE DEVELOPER SDN BHD',
      project_name: 'EXAMPLE RESIDENCE, TOWER B',
      needed_by: null,
      remark: null,
      lines: [
        {
          proposed_code: 'XY-1234-MB & XY-1234-BG',
          description: 'Example sinks',
        },
      ],
    });
    render(<NewProductApplicationForm slug="acme" />);

    const picker = await screen.findByRole('combobox', {
      name: /start from my stock inquiry/i,
    });
    fireEvent.focus(picker);
    const hit = await screen.findByText('SI26-0412 - XY-1234-MB & XY-1234-BG');
    fireEvent.mouseDown(hit);
    fireEvent.click(hit);

    expect(
      await screen.findByText('Inquiry asked: "XY-1234-MB & XY-1234-BG"'),
    ).toBeInTheDocument();
    expect(getNewProductApplicationPrefill).toHaveBeenCalledWith('si-1');
    await waitFor(() =>
      expect(
        (screen.getByLabelText('Customer') as HTMLInputElement).value,
      ).toBe('EXAMPLE DEVELOPER SDN BHD'),
    );

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(createNewProductApplication).toHaveBeenCalledTimes(1),
    );
    const body = asMock(createNewProductApplication).mock.calls[0][0];
    expect(body.customer_id).toBeNull();
    expect(body.stock_inquiry_id).toBe('si-1');
    expect(body.current_product_ids).toEqual([]);
    expect(body.lines).toEqual([]);
  });

  it('has no item group, base UOM or selling price, and no cost box to write', async () => {
    render(<NewProductApplicationForm slug="acme" />);
    await screen.findByLabelText('Product code');
    expect(screen.queryByText(/item group/i)).toBeNull();
    expect(screen.queryByText(/base uom/i)).toBeNull();
    expect(screen.queryByText(/selling/i)).toBeNull();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(
      screen.getByRole('columnheader', { name: /product code/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/product \d+ of \d+/i)).toBeNull();
  });

  it('stays on the form with the server text when Submit is refused', async () => {
    asMock(submitNewProductApplication).mockRejectedValue(
      new Error('Product 1: enter the product type.'),
    );
    render(<NewProductApplicationForm slug="acme" />);
    await screen.findByLabelText('Product code');
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    expect(
      await screen.findByText('Product 1: enter the product type.'),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});

describe('an existing application', () => {
  it('is read-only once submitted, with the lock line and Revise', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'submitted', status_label: 'Submitted' }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);

    expect(
      (await screen.findAllByText('Example kitchen sink')).length,
    ).toBeGreaterThan(0);
    // S3: the read view is plain text, not disabled inputs
    expect(screen.queryByLabelText('Product type')).toBeNull();
    expect(screen.queryAllByRole('textbox')).toHaveLength(0);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /save as draft/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^submit$/i })).toBeNull();
    expect(screen.queryByText(/Locked: Revise to change it/)).toBeNull();
    expect(screen.queryByText(/Waiting for approval/)).toBeNull();
    expect(
      screen.getByRole('button', { name: /^revise$/i }),
    ).toBeInTheDocument();
  });

  it('needs a reason before Revise goes through', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'approved', status_label: 'Approved' }),
    );
    asMock(reviseNewProductApplication).mockResolvedValue(detail());
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);

    fireEvent.click(await screen.findByRole('button', { name: /^revise$/i }));
    const dialogConfirm = await screen.findByRole('button', {
      name: /^revise$/i,
    });
    expect(dialogConfirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/what changed, and why/i), {
      target: { value: 'UOM is SET not UNIT' },
    });
    expect(dialogConfirm).not.toBeDisabled();
    fireEvent.click(dialogConfirm);
    await waitFor(() =>
      expect(reviseNewProductApplication).toHaveBeenCalledWith(
        'a-1',
        'UOM is SET not UNIT',
      ),
    );
  });

  it('hides Revise once the new code is linked, and shows no per-row Opened as column', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'approved',
        status_label: 'Approved',
        new_product_id: 'p-1',
        new_product_code: 'XY-1234-MB-69',
        new_product_active: true,
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('XY-1234-MB-69')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: /opened as/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^revise$/i })).toBeNull();
  });

  it('shows the reject reason on a rejected application and lets it be edited', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'rejected',
        status_label: 'Rejected',
        reject_reason: 'Use the existing codes',
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(
      await screen.findByText(/Use the existing codes/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Product type')).not.toBeDisabled();
  });

  it('sends a rejected application back with Appeal, not Submit (owner, 28 Oct)', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'rejected', status_label: 'Rejected', reject_reason: 'x' }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(
      await screen.findByRole('button', { name: /^appeal$/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^submit$/i })).toBeNull();
  });
});

describe('portal: stock inquiry tab and earlier codes (NPA-FROM-SI)', () => {
  const SI = {
    id: 'si-1',
    inquiry_number: 'SI26-0412',
    product_code: 'XY-1234-MB',
    status: 'responded',
    item_description: 'Kitchen sink',
    purchasing_response: 'Please apply for a new code.',
    quantity: '55',
  };

  it('shows the inquiry as plain text (no link) on its own tab', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'submitted', status_label: 'Submitted', stock_inquiry: SI }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    await screen.findAllByText('Example kitchen sink');
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Stock inquiry' }));
    expect(await screen.findByText('SI26-0412')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'SI26-0412' })).toBeNull();
    expect(screen.getByText('Please apply for a new code.')).toBeInTheDocument();
  });

  it('says there is no stock inquiry for an application without one', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'submitted', status_label: 'Submitted', stock_inquiry: null }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    await screen.findAllByText('Example kitchen sink');
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Stock inquiry' }));
    expect(await screen.findByText('No stock inquiry')).toBeInTheDocument();
  });

  it('shows the earlier code without an application number', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'submitted',
        status_label: 'Submitted',
        current_products: [{ id: 'p-1', product_code: 'XY-1234-MB' }],
        suggestions: [
          {
            product_id: 'p-9',
            product_code: 'XY-1234-MB-69',
            product_name: null,
            is_active: true,
            description: 'no tap hole',
            created_at: '2026-11-03T02:00:00',
          },
        ],
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    const row = await screen.findByTestId('npa-suggestions');
    expect(row.textContent).toContain(
      'A code was already created from XY-1234-MB: XY-1234-MB-69 (03/11/2026, "no tap hole")',
    );
  });
});

describe('purchasing feedback on the portal (PQ1)', () => {
  const filled = () =>
    detail({
      status: 'approved',
      status_label: 'Approved',
      lead_time: '3 weeks',
      new_product_id: 'p-9',
      new_product_code: 'XY-1234-MB-69',
      new_product_active: true,
      new_product_facts: { opened_supplier_name: 'Example Supplier Co' },
      lines: [line({ cost_price: '12.50' })],
    });

  it('shows COST, LEADTIME and the supplier read-only, with no Save feedback', async () => {
    asMock(getNewProductApplication).mockResolvedValue(filled());
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('3 weeks')).toBeInTheDocument();
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.getByText(/Example Supplier Co/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(screen.queryByRole('button', { name: /save feedback/i })).toBeNull();
    expect(screen.queryByText(/item group|base uom|selling/i)).toBeNull();
  });

  it('says purchasing fills it after approval while it is empty', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'submitted', status_label: 'Submitted' }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(
      await screen.findByText('Purchasing fills this after approval.'),
    ).toBeInTheDocument();
  });

  it('Download Excel calls the portal download with the application id', async () => {
    asMock(getNewProductApplication).mockResolvedValue(filled());
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    fireEvent.click(
      await screen.findByRole('button', { name: /download excel/i }),
    );
    await waitFor(() =>
      expect(downloadNewProductApplicationExcel).toHaveBeenCalledTimes(1),
    );
    expect(asMock(downloadNewProductApplicationExcel).mock.calls[0][0]).toBe(
      'a-1',
    );
  });
});

describe('portal: table form and attachments (v5)', () => {
  it('draws Stock Inquiry\'s table rows and one line table with Add row, no per-product cards', async () => {
    render(<NewProductApplicationForm slug="acme" />);
    expect(await screen.findByText('NEW PRODUCT APPLICATION')).toBeInTheDocument();
    expect(screen.queryByText(/PRODUCT INQUIRY FORM/)).toBeNull();
    const text = document.body.textContent ?? '';
    let at = -1;
    for (const l of [
      'REFF:',
      'DATE:',
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
    expect(screen.queryByLabelText(/add image/i)).toBeNull();
    expect(screen.queryByText(/copy from the inquiry/i)).toBeNull();
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /add row/i }));
    expect(screen.getAllByLabelText('Product type')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: /^remove row 1$/i }));
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
  });

  it('renders the shared dropzone for kind new_product_application; on create the files are pending and upload right after the first save', async () => {
    asMock(uploadAttachment).mockResolvedValue({ id: 'at-1', filename: 'sample-doc.pdf' });
    render(<NewProductApplicationForm slug="acme" />);
    const zone = await screen.findByTestId('dropzone');
    expect(zone).toHaveAttribute('data-kind', 'new_product_application');
    expect(zone).toHaveAttribute('data-submission', '');

    fireEvent.click(screen.getByRole('button', { name: /drop pending file/i }));
    await waitFor(() =>
      expect(screen.getByTestId('dropzone')).toHaveAttribute('data-pending', '1'),
    );
    expect(uploadAttachment).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(uploadAttachment).toHaveBeenCalledWith(
        'new_product_application',
        'a-1',
        dz.pick,
      ),
    );
    expect(asMock(createNewProductApplication).mock.invocationCallOrder[0]).toBeLessThan(
      asMock(uploadAttachment).mock.invocationCallOrder[0],
    );
  });

  it('on a saved application the dropzone gets the application id and its attachments; read-only once submitted', async () => {
    const files = [{ id: 'at-1', filename: 'sample-doc.pdf', url: '/f/1' }];
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ attachments: files } as never),
    );
    const { unmount } = render(
      <NewProductApplicationForm slug="acme" applicationId="a-1" />,
    );
    const zone = await screen.findByTestId('dropzone');
    expect(zone).toHaveAttribute('data-submission', 'a-1');
    expect(zone).toHaveAttribute('data-attachments', '1');
    expect(zone).toHaveAttribute('data-readonly', 'no');
    unmount();

    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'submitted', status_label: 'Submitted', attachments: files } as never),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByTestId('dropzone')).toHaveAttribute('data-readonly', 'yes');
  });

  it('the payload has no per-row image keys', async () => {
    render(<NewProductApplicationForm slug="acme" />);
    await screen.findByLabelText('Product code');
    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() => expect(createNewProductApplication).toHaveBeenCalled());
    const row = asMock(createNewProductApplication).mock.calls[0][0].lines[0];
    for (const k of ['images', 'staged_images', 'removed_link_ids'])
      expect(row).not.toHaveProperty(k);
  });
});

describe('an application that is not this contact\'s', () => {
  it('shows a not-found state with a way back and no paper sheet when the load is refused', async () => {
    asMock(getNewProductApplication).mockRejectedValue(
      new Error('Application not found'),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-other" />);

    expect(
      await screen.findByRole('heading', { name: 'Application not found' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('It may have been removed, or it belongs to another account.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back/i })).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: /save as draft/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^submit$/i })).toBeNull();
    expect(screen.queryByLabelText('Product type')).toBeNull();
    expect(screen.queryByText('REFF:')).toBeNull();
    expect(screen.queryByText('PRODUCT TYPE:')).toBeNull();
  });
});

describe('portal: PRODUCT CODES and NEW PRODUCT CODE rows', () => {
  const submitted = (over: Partial<NewProductApplicationDetail> = {}) =>
    detail({ status: 'submitted', status_label: 'Submitted', ...over });

  it('shows the codes as comma text and the waiting line for the new code', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      submitted({
        current_products: [
          { id: 'p-1', product_code: 'A-1' },
          { id: 'p-2', product_code: 'B-2' },
        ],
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('A-1, B-2')).toBeInTheDocument();
    expect(
      screen.getByText('Purchasing fills this in when the code is created.'),
    ).toBeInTheDocument();
  });

  it('shows the new code with an Inactive badge when it is inactive', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      submitted({ new_product_id: 'p-9', new_product_code: 'A-1-69', new_product_active: false }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('A-1-69')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('shows the supplier of the linked code and nothing else of its facts', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      submitted({
        new_product_id: 'p-9',
        new_product_code: 'A-1-69',
        new_product_active: true,
        new_product_facts: { opened_supplier_name: 'Example Supplier Co' },
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('Supplier: Example Supplier Co')).toBeInTheDocument();
    expect(screen.queryByText(/From AutoCount/)).toBeNull();
  });

  it('shows an older closed one as Rejected with the reason', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      submitted({ new_code_closed_reason: 'Customer walked away' }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('Rejected: Customer walked away')).toBeInTheDocument();
  });
});

describe('portal: Brand column gone, per-row Opened as for older applications (NPA-FROM-SI v3)', () => {
  it('draws no Brand header or picker on a new form', async () => {
    render(<NewProductApplicationForm slug="acme" />);
    await screen.findByLabelText('Product code');
    expect(screen.queryByRole('columnheader', { name: /brand/i })).toBeNull();
    expect(screen.queryByLabelText(/brand/i)).toBeNull();
  });

  it('draws no Brand header or text in the read-only view', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'submitted',
        status_label: 'Submitted',
        lines: [line({ brand_name: 'Example Brand' })],
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    await screen.findAllByText('Example kitchen sink');
    expect(screen.queryByRole('columnheader', { name: /brand/i })).toBeNull();
    expect(screen.queryByText('Example Brand')).toBeNull();
  });

  it('shows the Opened as column with the opened code and the Rejected reason per row', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'approved',
        status_label: 'Approved',
        lines_total: 3,
        lines_done: 2,
        lines: [
          line({
            opened_product_id: 'p-9',
            opened_product_code: 'XY-1234-MB-9',
            opened_product_name: 'Example sink 9',
            opened_product_active: true,
          }),
          line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG', closed_reason: 'Customer walked away' }),
          line({ id: 'l-3', line_no: 3, proposed_code: 'XY-1234-ZZ' }),
        ],
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByRole('columnheader', { name: /opened as/i })).toBeInTheDocument();
    const rows = screen.getAllByTestId('npa-line');
    expect(within(rows[0]).getByText(/XY-1234-MB-9/)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/Rejected: Customer walked away/)).toBeInTheDocument();
    expect(within(rows[2]).queryByText(/Rejected:/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
  });

  it('shows no Opened as column when no line is resolved', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'approved', status_label: 'Approved' }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    await screen.findAllByText('Example kitchen sink');
    expect(screen.queryByRole('columnheader', { name: /opened as/i })).toBeNull();
  });
});

describe('portal: no product table from a stock inquiry, purchasing result read-only (owner 8 Nov)', () => {
  it('a new form started from an inquiry has no table or add control and saves lines: []', async () => {
    asMock(getNewProductApplicationPrefill).mockResolvedValue({
      stock_inquiry_id: 'si-1',
      stock_inquiry_number: 'SI26-0412',
      customer_id: null,
      customer_name: 'EXAMPLE DEVELOPER SDN BHD',
      project_name: 'EXAMPLE RESIDENCE, TOWER B',
      needed_by: null,
      remark: null,
      lines: [{ proposed_code: 'XY-1234-MB', description: 'Example sinks' }],
    });
    render(<NewProductApplicationForm slug="acme" />);
    const picker = await screen.findByRole('combobox', { name: /start from my stock inquiry/i });
    fireEvent.focus(picker);
    const hit = await screen.findByText('SI26-0412 - XY-1234-MB & XY-1234-BG');
    fireEvent.mouseDown(hit);
    fireEvent.click(hit);
    await waitFor(() =>
      expect((screen.getByLabelText('Customer') as HTMLInputElement).value).toBe(
        'EXAMPLE DEVELOPER SDN BHD',
      ),
    );
    expect(screen.queryByRole('columnheader', { name: /product code/i })).toBeNull();
    expect(screen.queryByLabelText('Product type')).toBeNull();
    expect(screen.queryByRole('button', { name: /add (row|product)/i })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() => expect(createNewProductApplication).toHaveBeenCalledTimes(1));
    const body = asMock(createNewProductApplication).mock.calls[0][0];
    expect(body.stock_inquiry_id).toBe('si-1');
    expect(body.lines).toEqual([]);
  });

  it('the view of an SI application with no lines draws no table', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'submitted',
        status_label: 'Submitted',
        stock_inquiry_id: 'si-1',
        stock_inquiry_number: 'SI26-0412',
        lines: [],
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByRole('columnheader', { name: /product code/i })).toBeNull();
    expect(screen.queryAllByTestId('npa-line')).toHaveLength(0);
  });

  it('the view of an older SI application with lines shows them read-only', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'submitted',
        status_label: 'Submitted',
        stock_inquiry_id: 'si-1',
        stock_inquiry_number: 'SI26-0412',
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect((await screen.findAllByText('Example kitchen sink')).length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('npa-line')).toHaveLength(1);
    expect(screen.queryByLabelText('Product type')).toBeNull();
  });

  it('a standalone application keeps its table', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({ status: 'submitted', status_label: 'Submitted', stock_inquiry_id: null }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    await screen.findAllByText('Example kitchen sink');
    expect(screen.getByRole('columnheader', { name: /product code/i })).toBeInTheDocument();
    expect(screen.getAllByTestId('npa-line')).toHaveLength(1);
  });

  it('shows a typed new code (no product yet), LEADTIME and COST read-only, with no purchasing controls', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'completed',
        status_label: 'Completed',
        stock_inquiry_id: 'si-1',
        stock_inquiry_number: 'SI26-0412',
        lines: [],
        new_product_id: null,
        new_product_code: 'XY-TYPED-7',
        new_code_text: 'XY-TYPED-7',
        lead_time: '3 weeks',
        cost_price: '12.50',
      } as Partial<NewProductApplicationDetail>),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(await screen.findByText('XY-TYPED-7')).toBeInTheDocument();
    expect(screen.getByText('3 weeks')).toBeInTheDocument();
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit purchasing response/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /save feedback/i })).toBeNull();
    expect(screen.queryByLabelText(/^lead ?time/i)).toBeNull();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
  });
});
