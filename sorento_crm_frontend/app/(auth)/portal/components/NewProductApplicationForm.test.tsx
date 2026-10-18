/**
 * Portal new product application form (NEW-PRODUCT-APP): start from the contact's own responded
 * inquiry, the line table without supplier or cost, Revise with a required reason, and the
 * read-only view once the application is with purchasing. The service module is mocked.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from '@/lib/toast';
import type {
  NewProductApplicationDetail,
  NewProductApplicationLine,
} from '@/types/newProductApplication';

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
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
  lookupNewProductApplication: vi.fn(async () => []),
  lookupNewProductApplicationCustomers: vi.fn(async () => []),
  uploadNewProductApplicationLineImage: vi.fn(),
  deleteNewProductApplicationLineImage: vi.fn(),
  copyNewProductApplicationLineImage: vi.fn(),
  listInquiryImagesForNewProductApplication: vi.fn(),
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
  uploadNewProductApplicationLineImage,
  deleteNewProductApplicationLineImage,
  copyNewProductApplicationLineImage,
  listInquiryImagesForNewProductApplication,
  updateNewProductApplication,
  downloadNewProductApplicationExcel,
} from '../lib/new-product-application-service';
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
    images: [],
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
  it('starts from my stock inquiry: line 1 gets the code text, the customer stays typed text', async () => {
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

    await waitFor(() =>
      expect(
        (screen.getByLabelText('Product code') as HTMLInputElement).value,
      ).toBe('XY-1234-MB & XY-1234-BG'),
    );
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
    expect(body.lines[0].proposed_code).toBe('XY-1234-MB & XY-1234-BG');
  });

  it('has no item group, base UOM or selling price, and no cost box to write', async () => {
    render(<NewProductApplicationForm slug="acme" />);
    await screen.findByLabelText('Product code');
    expect(screen.queryByText(/item group/i)).toBeNull();
    expect(screen.queryByText(/base uom/i)).toBeNull();
    expect(screen.queryByText(/selling/i)).toBeNull();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(screen.getByText('PRODUCT CODE:')).toBeInTheDocument();
    expect(screen.getByText('Product 1 of 1')).toBeInTheDocument();
  });

  it('stages an image and uploads it with the line id the create returns', async () => {
    asMock(createNewProductApplication).mockResolvedValue(detail());
    render(<NewProductApplicationForm slug="acme" />);
    const file = new File(['x'], 'sample-front.png', { type: 'image/png' });
    fireEvent.change(await screen.findByLabelText('Add image'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(uploadNewProductApplicationLineImage).toHaveBeenCalledWith(
        'a-1',
        'l-1',
        file,
      ),
    );
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
    expect(
      screen.getByText(
        /Locked: Revise to change it; it goes back to Draft and needs approval again\./,
      ),
    ).toBeInTheDocument();
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

  it('hides Revise once a line is resolved and shows the result of each line', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        status: 'approved',
        status_label: 'Approved',
        lines: [
          line({ opened_product_id: 'p-1', opened_product_code: 'XY-1234-MB' }),
          line({ id: 'l-2', line_no: 2, closed_reason: 'supplier dropped it' }),
        ],
      }),
    );
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    expect(
      await screen.findByText('XY-1234-MB', { selector: 'span,p,a' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/not opening/i)).toBeInTheDocument();
    expect(screen.getByText('supplier dropped it')).toBeInTheDocument();
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
});

describe('purchasing feedback on the portal (PQ1)', () => {
  const filled = () =>
    detail({
      status: 'approved',
      status_label: 'Approved',
      lead_time: '3 weeks',
      lines: [
        line({
          cost_price: '12.50',
          opened_supplier_name: 'Example Supplier Co',
        }),
      ],
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

describe('image removal on a saved portal draft', () => {
  it('stages the removal and applies it only after Save as draft', async () => {
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        lines: [
          line({
            images: [
              {
                link_id: 'k-1',
                attachment_id: 'at-1',
                filename: 'sample-front.png',
                url: '/files/1',
                content_type: 'image/png',
              },
            ],
          } as never),
        ],
      }),
    );
    asMock(updateNewProductApplication).mockResolvedValue(detail());
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    fireEvent.click(
      await screen.findByRole('button', { name: /remove.*sample-front\.png/i }),
    );
    expect(screen.queryByText('sample-front.png')).toBeNull();
    expect(deleteNewProductApplicationLineImage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(deleteNewProductApplicationLineImage).toHaveBeenCalledWith(
        'a-1',
        'l-1',
        'k-1',
      ),
    );
    expect(deleteNewProductApplicationLineImage).toHaveBeenCalledTimes(1);
  });
});

describe('image merge after a save (B1, portal)', () => {
  const img = (name: string, link: string) => ({
    link_id: link,
    attachment_id: `at-${link}`,
    filename: name,
    url: `/files/${link}`,
    content_type: 'image/png',
  });

  it('B1a: old.png removed then new.png uploaded: old.png stays hidden, Save deletes it once', async () => {
    const base = detail({
      lines: [line({ images: [img('old.png', 'k-old')] } as never)],
    });
    asMock(getNewProductApplication).mockResolvedValue(base);
    asMock(uploadNewProductApplicationLineImage).mockResolvedValue(
      detail({
        lines: [
          line({
            images: [img('old.png', 'k-old'), img('new.png', 'k-new')],
          } as never),
        ],
      }),
    );
    asMock(updateNewProductApplication).mockResolvedValue(base);
    asMock(deleteNewProductApplicationLineImage).mockResolvedValue(undefined);
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);

    fireEvent.click(
      await screen.findByRole('button', { name: /remove.*old\.png/i }),
    );
    fireEvent.change(screen.getByLabelText('Add image'), {
      target: { files: [new File(['x'], 'new.png', { type: 'image/png' })] },
    });
    expect(await screen.findByText('new.png')).toBeInTheDocument();
    expect(screen.queryByText('old.png')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(deleteNewProductApplicationLineImage).toHaveBeenCalledTimes(1),
    );
    expect(deleteNewProductApplicationLineImage).toHaveBeenCalledWith(
      'a-1',
      'l-1',
      'k-old',
    );
  });

  it('B1b: a removed saved product plus a new one with an image: no duplicated id, upload to the returned id', async () => {
    asMock(getNewProductApplication).mockResolvedValue(detail());
    asMock(updateNewProductApplication).mockResolvedValue(
      detail({ lines: [line({ id: 'l-fresh', images: [] } as never)] }),
    );
    asMock(uploadNewProductApplicationLineImage).mockResolvedValue(detail());
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);

    fireEvent.click(await screen.findByRole('button', { name: /add product/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /^remove$/i })[0]);
    const file = new File(['x'], 'fresh.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Add image'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));

    await waitFor(() => expect(updateNewProductApplication).toHaveBeenCalled());
    const lines = asMock(updateNewProductApplication).mock.calls[0][1]
      .lines as { id?: string }[];
    expect(lines).toHaveLength(1);
    expect(lines[0].id ?? null).toBeNull();
    await waitFor(() =>
      expect(uploadNewProductApplicationLineImage).toHaveBeenCalledWith(
        'a-1',
        'l-fresh',
        file,
      ),
    );
  });
});

describe('portal: copy from the inquiry on a new form, non-image files, B1c', () => {
  const NOT_IMAGE = 'Upload a JPEG, PNG or WebP image.';
  const pdf = () => new File(['x'], 'notes.pdf', { type: 'application/pdf' });

  it('stages a copy from the started-from inquiry and applies it after the first save', async () => {
    asMock(getNewProductApplicationPrefill).mockResolvedValue({
      stock_inquiry_id: 'si-1',
      stock_inquiry_number: 'SI26-0412',
      customer_id: null,
      customer_name: 'EXAMPLE DEVELOPER SDN BHD',
      project_name: null,
      needed_by: null,
      remark: null,
      lines: [{ proposed_code: 'XY-1', description: 'Example sinks' }],
    });
    asMock(listInquiryImagesForNewProductApplication).mockResolvedValue([
      { attachment_id: 'at-9', filename: 'inquiry-sketch.png' },
    ]);
    asMock(copyNewProductApplicationLineImage).mockResolvedValue(detail());
    render(<NewProductApplicationForm slug="acme" />);
    const picker = await screen.findByRole('combobox', {
      name: /start from my stock inquiry/i,
    });
    fireEvent.focus(picker);
    const hit = await screen.findByText('SI26-0412 - XY-1234-MB & XY-1234-BG');
    fireEvent.mouseDown(hit);
    fireEvent.click(hit);
    await waitFor(() =>
      expect(
        (screen.getByLabelText('Product code') as HTMLInputElement).value,
      ).toBe('XY-1'),
    );

    fireEvent.click(
      await screen.findByRole('button', { name: /copy from the inquiry/i }),
    );
    expect(listInquiryImagesForNewProductApplication).toHaveBeenCalledWith(
      'si-1',
    );
    fireEvent.click(await screen.findByText('inquiry-sketch.png'));
    expect(screen.getAllByText('inquiry-sketch.png').length).toBeGreaterThan(0);
    expect(copyNewProductApplicationLineImage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(copyNewProductApplicationLineImage).toHaveBeenCalledWith(
        'a-1',
        'l-1',
        'at-9',
      ),
    );
  });

  it('refuses a non-image file at once on an unsaved product', async () => {
    render(<NewProductApplicationForm slug="acme" />);
    fireEvent.change(await screen.findByLabelText('Add image'), {
      target: { files: [pdf()] },
    });
    expect(toast.error).toHaveBeenCalledWith(NOT_IMAGE);
    expect(screen.queryByText('notes.pdf')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(createNewProductApplication).toHaveBeenCalledTimes(1),
    );
    expect(uploadNewProductApplicationLineImage).not.toHaveBeenCalled();
  });

  it('refuses a non-image file on a saved product: toast, no upload call', async () => {
    asMock(getNewProductApplication).mockResolvedValue(detail());
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);
    fireEvent.change(await screen.findByLabelText('Add image'), {
      target: { files: [pdf()] },
    });
    expect(toast.error).toHaveBeenCalledWith(NOT_IMAGE);
    expect(uploadNewProductApplicationLineImage).not.toHaveBeenCalled();
  });

  it('B1c: a live upload before and after a save targets each product own id; no save sends a duplicated id', async () => {
    const img = {
      link_id: 'k-1',
      attachment_id: 'at-1',
      filename: 'one.png',
      url: '/files/1',
      content_type: 'image/png',
    };
    asMock(getNewProductApplication).mockResolvedValue(
      detail({
        lines: [
          line({ id: 'l-1', line_no: 1, description: 'First' }),
          line({ id: 'l-2', line_no: 2, description: 'Second' }),
        ],
      }),
    );
    const before = detail({
      lines: [
        line({ id: 'l-1', line_no: 1, description: 'First' }),
        line({ id: 'l-2', line_no: 2, description: 'Second', images: [img] } as never),
      ],
    });
    const after = detail({
      lines: [
        line({ id: 'l-2', line_no: 1, description: 'Second', images: [img] } as never),
        line({ id: 'l-new', line_no: 2, description: null }),
      ],
    });
    asMock(updateNewProductApplication).mockResolvedValue(after);
    asMock(uploadNewProductApplicationLineImage)
      .mockResolvedValueOnce(before)
      .mockResolvedValue(after);
    render(<NewProductApplicationForm slug="acme" applicationId="a-1" />);

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /^remove$/i }))[0],
    );
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    const f1 = new File(['x'], 'one.png', { type: 'image/png' });
    const f2 = new File(['x'], 'two.png', { type: 'image/png' });
    fireEvent.change(screen.getAllByLabelText('Add image')[0], {
      target: { files: [f1] },
    });
    await waitFor(() =>
      expect(uploadNewProductApplicationLineImage).toHaveBeenCalledTimes(1),
    );

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() => expect(updateNewProductApplication).toHaveBeenCalled());
    const first = (
      asMock(updateNewProductApplication).mock.calls[0][1].lines as {
        id?: string;
      }[]
    ).map((l) => l.id ?? null);
    expect(first).toEqual(['l-2', null]);

    fireEvent.change(screen.getAllByLabelText('Add image')[1], {
      target: { files: [f2] },
    });
    await waitFor(() =>
      expect(uploadNewProductApplicationLineImage).toHaveBeenCalledTimes(2),
    );
    const up = asMock(uploadNewProductApplicationLineImage).mock.calls;
    expect(up[0]).toEqual(['a-1', 'l-2', f1]);
    expect(up[1]).toEqual(['a-1', 'l-new', f2]);

    fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));
    await waitFor(() =>
      expect(updateNewProductApplication).toHaveBeenCalledTimes(2),
    );
    const second = (
      asMock(updateNewProductApplication).mock.calls[1][1].lines as {
        id?: string;
      }[]
    ).map((l) => l.id);
    expect(second).toEqual(['l-2', 'l-new']);
  });

  it('keeps the image just uploaded on the IMAGE row after a refused Submit', async () => {
    asMock(createNewProductApplication).mockResolvedValue(
      detail({ lines: [line({ id: 'l-1', images: [] } as never)] }),
    );
    asMock(uploadNewProductApplicationLineImage).mockResolvedValue(
      detail({
        lines: [
          line({
            images: [
              {
                link_id: 'k-1',
                attachment_id: 'at-1',
                filename: 'sample-front.png',
                url: '/files/1',
                content_type: 'image/png',
              },
            ],
          } as never),
        ],
      }),
    );
    asMock(submitNewProductApplication).mockRejectedValue(
      new Error('Product 1: enter the product type.'),
    );
    render(<NewProductApplicationForm slug="acme" />);
    fireEvent.change(await screen.findByLabelText('Add image'), {
      target: {
        files: [new File(['x'], 'sample-front.png', { type: 'image/png' })],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(submitNewProductApplication).toHaveBeenCalled());
    expect(
      await screen.findByRole('link', { name: 'sample-front.png' }),
    ).toBeInTheDocument();
  });
});
