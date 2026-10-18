/**
 * NEW-PRODUCT-APP staff detail: which button each viewer sees on each status, and the Link
 * product search (it only lists; a person picks). Hooks, the pager and the shell are mocked;
 * the page's own rules run.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type {
  NewProductApplicationDetail as Detail,
  NewProductApplicationLine,
} from '@/types/newProductApplication';

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  userId: 'u-owner',
  data: undefined as unknown,
  link: vi.fn(),
  search: vi.fn(),
  feedback: vi.fn(),
  download: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/procurement-management/new-product-applications/a-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({
  useEffectiveUserId: () => state.userId,
}));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({
    countdown: null,
    isBlocked: false,
    start: vi.fn(),
  }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/audit/AuditTrail', () => ({
  default: () => <div data-testid="audit-trail" />,
}));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({
    gear,
    primary,
  }: {
    gear?: React.ReactNode;
    primary?: React.ReactNode;
  }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
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
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: () => Promise.resolve(),
    isLoading: false,
  }),
}));
vi.mock('../hooks/useNewProductApplications', () => ({
  newProductApplicationsPagerQuery: {},
  useNewProductApplicationListingKey: (suffix?: string) =>
    suffix ? `procurement.new_product_applications.view::${suffix}` : 'procurement.new_product_applications.view',
  useNewProductApplicationQuery: () => ({
    data: state.data,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useNewProductApplicationMutations: () => {
    const idle = () => ({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
    });
    return {
      submit: idle(),
      approve: idle(),
      reject: idle(),
      revise: idle(),
      cancel: idle(),
      link: { mutate: state.link, mutateAsync: state.link, isPending: false },
      close: idle(),
      undo: idle(),
      feedback: {
        mutate: state.feedback,
        mutateAsync: state.feedback,
        isPending: false,
      },
    };
  },
}));
vi.mock('../services/newProductApplicationService', () => ({
  searchNewProductApplicationProducts: (q: string) => state.search(q),
  downloadNewProductApplicationExcel: (...a: unknown[]) => state.download(...a),
}));

import NewProductApplicationDetail from './NewProductApplicationDetail';

function Page() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <NewProductApplicationDetail applicationId="a-1" />
    </QueryClientProvider>
  );
}

function line(
  over: Partial<NewProductApplicationLine> = {},
): NewProductApplicationLine {
  return {
    id: 'l-1',
    line_no: 1,
    proposed_code: 'XY-1234-MB',
    description: 'Example kitchen sink',
    dimension: '600x400',
    material: 'Steel',
    thickness: '1.2mm',
    packing: 'Carton',
    brand_id: null,
    brand_name: null,
    expected_qty: '55',
    cost_price: null,
    images: [],
    opened_category_name: null,
    opened_base_uom_name: null,
    opened_list_price: null,
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

function detail(over: Partial<Detail> = {}): Detail {
  return {
    id: 'a-1',
    application_no: 'NPA-000001',
    status: 'draft',
    status_label: 'Draft',
    source: 'staff',
    applicant_id: 'u-owner',
    applicant_name: 'Owner',
    stock_inquiry_id: 'si-1',
    stock_inquiry_number: 'SI26-0412',
    stock_inquiry_product_code: 'XY-1234-MB',
    customer_id: null,
    customer_code: null,
    customer_name: 'EXAMPLE DEVELOPER SDN BHD',
    project_name: 'EXAMPLE RESIDENCE, TOWER B',
    first_line: 'XY-1234-MB',
    lines_total: 2,
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
    lines: [
      line(),
      line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' }),
    ],
    ...over,
  };
}

const button = (name: RegExp) => screen.queryByRole('button', { name });

beforeEach(() => {
  vi.clearAllMocks();
  state.perms = new Set();
  state.userId = 'u-owner';
  state.data = detail();
  state.search.mockResolvedValue([]);
});

describe('who sees which next action', () => {
  it('shows Submit and Edit to the owner on a draft, and neither to someone else', () => {
    state.perms = new Set(['procurement.new_product_applications.create']);
    const { unmount } = render(<Page />);
    expect(button(/^submit$/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit' })).toBeInTheDocument();
    expect(button(/^approve$/i)).not.toBeInTheDocument();
    unmount();

    state.userId = 'u-other';
    render(<Page />);
    expect(button(/^submit$/i)).not.toBeInTheDocument();
  });

  it('shows Approve and Reject to an approver on a submitted application, not Submit', () => {
    state.data = detail({ status: 'submitted', status_label: 'Submitted' });
    state.userId = 'u-approver';
    state.perms = new Set(['procurement.new_product_applications.approve']);
    render(<Page />);
    expect(button(/^approve$/i)).toBeInTheDocument();
    expect(button(/^reject$/i)).toBeInTheDocument();
    expect(button(/^submit$/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Locked: Revise to change it; it goes back to Draft and needs approval again\./,
      ),
    ).toBeInTheDocument();
  });

  it('asks for a reason before Reject goes through', async () => {
    state.data = detail({ status: 'submitted', status_label: 'Submitted' });
    state.userId = 'u-approver';
    state.perms = new Set(['procurement.new_product_applications.approve']);
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: /^reject$/i }));
    const confirm = await screen.findByRole('button', {
      name: /^reject$/i,
      hidden: false,
    });
    expect(screen.getByLabelText(/reason/i)).toBeInTheDocument();
    expect(confirm).toBeDisabled();
  });

  it('offers Revise on an approved application with no resolved line, and hides it once one is', () => {
    state.data = detail({ status: 'approved', status_label: 'Approved' });
    state.perms = new Set(['procurement.new_product_applications.create']);
    const { unmount } = render(<Page />);
    expect(button(/^revise$/i)).toBeInTheDocument();
    unmount();

    state.data = detail({
      status: 'approved',
      status_label: 'Approved',
      lines_done: 1,
      lines: [
        line({
          opened_product_id: 'p-1',
          opened_product_code: 'XY-1234-MB',
          opened_product_name: 'Example kitchen sink',
          opened_product_active: true,
        }),
        line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' }),
      ],
    });
    render(<Page />);
    expect(button(/^revise$/i)).not.toBeInTheDocument();
  });
});

describe('a portal-sourced application on the staff side', () => {
  it('hides Edit on a rejected draft the owner could otherwise change', () => {
    state.data = detail({
      status: 'rejected',
      status_label: 'Rejected',
      source: 'portal',
    });
    state.perms = new Set(['procurement.new_product_applications.create']);
    render(<Page />);
    expect(
      screen.queryByRole('link', { name: 'Edit' }),
    ).not.toBeInTheDocument();
    expect(button(/^submit$/i)).toBeInTheDocument();
  });
});

describe('Link product', () => {
  beforeEach(() => {
    state.data = detail({ status: 'approved', status_label: 'Approved' });
    state.userId = 'u-buyer';
    state.perms = new Set(['procurement.new_product_applications.open_code']);
  });

  it('says the code is not in the product list yet, and picks nothing', async () => {
    render(<Page />);
    fireEvent.click(
      screen.getAllByRole('button', { name: /^link product$/i })[1],
    );
    const box = await screen.findByRole('combobox', {
      name: /product for line 2/i,
    });
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: 'srtks2406' } });

    expect(
      await screen.findByText(
        'srtks2406 is not in the product list yet. It appears after AutoCount sends it.',
      ),
    ).toBeInTheDocument();
    expect(state.link).not.toHaveBeenCalled();
  });

  it('lists a match without choosing it; only a click links the product', async () => {
    state.search.mockResolvedValue([
      {
        id: 'p-9',
        product_code: 'XY-1234-BG',
        product_name: 'Example steel sink',
        brand_name: null,
      },
    ]);
    render(<Page />);
    fireEvent.click(
      screen.getAllByRole('button', { name: /^link product$/i })[1],
    );
    const box = await screen.findByRole('combobox', {
      name: /product for line 2/i,
    });
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: 'srtks2406' } });

    const hit = await screen.findByText(/XY-1234-BG - Example steel sink/);
    expect(state.link).not.toHaveBeenCalled();

    fireEvent.mouseDown(hit);
    fireEvent.click(hit);
    await waitFor(() =>
      expect(state.link).toHaveBeenCalledWith({
        id: 'a-1',
        lineId: 'l-2',
        productId: 'p-9',
      }),
    );
  });
});

const OPEN = 'procurement.new_product_applications.open_code';
const approved = (over: Partial<Detail> = {}) =>
  detail({ status: 'approved', status_label: 'Approved', ...over });

describe('the paper sheet', () => {
  it('shows the paper labels, REFF = the number, and Product N of M blocks', () => {
    render(<Page />);
    for (const l of [
      'REFF:',
      'DATE:',
      'SALES PERSON:',
      'PRODUCT CODE:',
      'PRODUCT TYPE:',
      'PURCHASING FEEDBACK',
      'COST:',
      'LEADTIME:',
    ])
      expect(screen.getAllByText(new RegExp(l))[0]).toBeInTheDocument();
    expect(screen.getByText('NPA-000001')).toBeInTheDocument();
    expect(screen.getByText('Product 1 of 2')).toBeInTheDocument();
    expect(screen.getByText('Product 2 of 2')).toBeInTheDocument();
  });

  it('lists each product image by file name', () => {
    state.data = detail({
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
    });
    render(<Page />);
    expect(screen.getByText('sample-front.png')).toBeInTheDocument();
  });
});

describe('PURCHASING FEEDBACK', () => {
  const editor = () => {
    state.userId = 'u-buyer';
    state.perms = new Set([OPEN]);
  };

  it.each([['approved'], ['completed']])(
    'is editable for open_code on %s and Save feedback sends lead time and costs',
    (status) => {
      editor();
      state.data = detail({ status: status as Detail['status'], status_label: status });
      render(<Page />);
      fireEvent.change(screen.getByLabelText('Lead time'), {
        target: { value: '3 weeks' },
      });
      fireEvent.change(screen.getAllByLabelText('Cost')[0], {
        target: { value: '12.50' },
      });
      fireEvent.click(screen.getByRole('button', { name: /save feedback/i }));
      expect(state.feedback).toHaveBeenCalledTimes(1);
      const arg = state.feedback.mock.calls[0][0];
      expect(arg.id).toBe('a-1');
      expect(arg.data.lead_time).toBe('3 weeks');
      expect(arg.data.lines).toHaveLength(2);
      expect(arg.data.lines[0]).toEqual({ id: 'l-1', cost_price: '12.50' });
      expect(arg.data.lines[1].id).toBe('l-2');
      expect(arg.data.lines[1].cost_price ?? null).toBeNull();
    },
  );

  it('is read-only on a draft even for open_code', () => {
    editor();
    state.data = detail();
    render(<Page />);
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(screen.queryByRole('button', { name: /save feedback/i })).toBeNull();
  });

  it('is read-only on an approved record without open_code, with the waiting line', () => {
    state.userId = 'u-owner';
    state.perms = new Set(['procurement.new_product_applications.create']);
    state.data = approved();
    render(<Page />);
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(screen.queryByLabelText('Cost')).toBeNull();
    expect(screen.queryByRole('button', { name: /save feedback/i })).toBeNull();
    expect(
      screen.getByText('Purchasing fills this after approval.'),
    ).toBeInTheDocument();
  });
});

describe('From AutoCount', () => {
  it('shows the linked product item group, base UOM, list price and supplier read-only', () => {
    state.userId = 'u-buyer';
    state.perms = new Set([OPEN]);
    state.data = approved({
      lines: [
        line({
          opened_product_id: 'p-1',
          opened_product_code: 'XY-1234-MB',
          opened_product_name: 'Example kitchen sink',
          opened_product_active: true,
          opened_category_name: 'Example Group',
          opened_base_uom_name: 'Example UOM',
          opened_list_price: '185.00',
          opened_supplier_name: 'Example Supplier Co',
        } as never),
      ],
    });
    render(<Page />);
    expect(screen.getByText(/From AutoCount/)).toBeInTheDocument();
    expect(screen.getByText(/Example Group/)).toBeInTheDocument();
    expect(screen.getByText(/Example UOM/)).toBeInTheDocument();
    expect(screen.getByText(/185\.00/)).toBeInTheDocument();
    expect(screen.getByText(/Example Supplier Co/)).toBeInTheDocument();
  });

  it('shows no From AutoCount block before a product is linked', () => {
    state.data = approved();
    render(<Page />);
    expect(screen.queryByText(/From AutoCount/)).toBeNull();
  });
});

describe('Download Excel', () => {
  it('is in the gear menu and calls the download service with the application id', async () => {
    state.data = approved();
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: /download excel/i }));
    await waitFor(() => expect(state.download).toHaveBeenCalledTimes(1));
    expect(state.download.mock.calls[0][0]).toBe('a-1');
  });
});
