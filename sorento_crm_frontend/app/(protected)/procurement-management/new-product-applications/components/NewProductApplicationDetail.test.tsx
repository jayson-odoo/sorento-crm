/**
 * NEW-PRODUCT-APP staff detail: which button each viewer sees on each status, and the Link
 * product search (it only lists; a person picks). Hooks, the pager and the shell are mocked;
 * the page's own rules run.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
  purchasing: vi.fn(),
  purchasingReject: vi.fn(),
  purchasingReply: vi.fn(),
  closeCode: vi.fn(),
  undoCode: vi.fn(),
  undoLine: vi.fn(),
  search: vi.fn(),
  feedback: vi.fn(),
  download: vi.fn(),
  linkAtt: vi.fn(),
  unlinkRun: vi.fn(),
  unlinkInputs: [] as Record<string, unknown>[],
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
      linkNewCode: { mutate: state.link, mutateAsync: state.link, isPending: false },
      closeNewCode: {
        mutate: state.closeCode,
        mutateAsync: state.closeCode,
        isPending: false,
      },
      undo: { mutate: state.undoLine, mutateAsync: state.undoLine, isPending: false },
      undoNewCode: { mutate: state.undoCode, mutateAsync: state.undoCode, isPending: false },
      purchasingReply: {
        mutate: state.purchasingReply,
        mutateAsync: state.purchasingReply,
        isPending: false,
      },
      purchasingReject: {
        mutate: state.purchasingReject,
        mutateAsync: state.purchasingReject,
        isPending: false,
      },
      purchasingResponse: {
        mutate: state.purchasing,
        mutateAsync: state.purchasing,
        isPending: false,
      },
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
  linkNewProductApplicationAttachment: (...a: unknown[]) => state.linkAtt(...a),
}));

vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({
  __esModule: true,
  default: (props: {
    open: boolean;
    entityId?: string;
    linkAttachment?: (e: string, a: string) => Promise<unknown>;
  }) =>
    props.open ? (
      <div role="dialog" aria-label="Link attachment library">
        <button onClick={() => void props.linkAttachment?.(props.entityId!, 'at-5')}>
          Pick library file
        </button>
      </div>
    ) : null,
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    state.unlinkInputs.push(input);
    return { run: state.unlinkRun, targetId: null, isPending: false, countdown: null };
  },
}));

// NPA-FORM-SLA: the SI's handling lock and SLA tab, mocked so each test sets the lock state.
const lock = vi.hoisted(() => ({
  enabled: true,
  input: null as null | Record<string, unknown>,
}));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: (input: Record<string, unknown>) => {
    lock.input = input;
    return {
      state: lock.enabled ? 'not_escalated' : 'other_holds',
      businessCtasEnabled: lock.enabled,
      tracker: lock.enabled ? null : { handled_by_name: 'Purchasing Manager' },
      banner: null,
      claim: vi.fn(),
      takeOver: vi.fn(),
      release: vi.fn(),
      refresh: vi.fn(),
      isMutating: false,
    };
  },
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({
  HandlingLockBanner: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({
  HandlingLockReleaseMenuItem: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/FormSLATrackingTab', () => ({
  default: (p: { sourceEntityType: string; sourceEntityId: string }) => (
    <div data-testid="sla-tab">{`${p.sourceEntityType}:${p.sourceEntityId}`}</div>
  ),
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
    attachments: [],
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
    expect(screen.queryByText(/Locked: Revise to change it/)).toBeNull();
    expect(screen.queryByText(/Waiting for approval/)).toBeNull();
  });

  it('treats a resubmitted application like a submitted one (RESUBMITTED-STATUS)', () => {
    state.data = detail({ status: 'resubmitted', status_label: 'Resubmitted' });
    state.userId = 'u-approver';
    state.perms = new Set(['procurement.new_product_applications.approve']);
    render(<Page />);
    expect(button(/^approve$/i)).toBeInTheDocument();
    expect(button(/^reject$/i)).toBeInTheDocument();
    expect(screen.queryByText(/Locked: Revise to change it/)).toBeNull();
    expect(screen.queryByText(/Waiting for approval/)).toBeNull();
  });

  it('labels the applicant\'s send button Appeal on a rejected application', () => {
    state.data = detail({ status: 'rejected', status_label: 'Rejected', reject_reason: 'x' });
    state.perms = new Set(['procurement.new_product_applications.create']);
    render(<Page />);
    expect(button(/^appeal$/i)).toBeInTheDocument();
    expect(button(/^submit$/i)).not.toBeInTheDocument();
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
    // A rejected application goes back as a resubmission (RESUBMITTED-STATUS).
    expect(button(/^appeal$/i)).toBeInTheDocument();
  });
});

const openPurchasingDialog = async () => {
  fireEvent.click(
    await screen.findByRole('button', { name: /^edit purchasing response$/i }),
  );
  return screen.findByRole('dialog');
};

describe('Edit purchasing response: Link an existing product code', () => {
  beforeEach(() => {
    state.data = detail({ status: 'approved', status_label: 'Approved' });
    state.userId = 'u-buyer';
    state.perms = new Set(['procurement.new_product_applications.open_code']);
  });

  it('says there is no match for a code that is not in the product list, and picks nothing', async () => {
    render(<Page />);
    const dialog = await openPurchasingDialog();
    fireEvent.click(
      within(dialog).getByRole('radio', { name: /link an existing product code/i }),
    );
    fireEvent.click(await within(dialog).findByRole('combobox', { name: /product code/i }));
    fireEvent.change(await screen.findByPlaceholderText('Search...'), {
      target: { value: 'srtks2406' },
    });
    expect(await screen.findByText('No product matches that.')).toBeInTheDocument();
    expect(state.purchasing).not.toHaveBeenCalled();
  });

  it('lists a match without choosing it; only Save sends the picked product', async () => {
    state.search.mockResolvedValue([
      {
        id: 'p-9',
        product_code: 'XY-1234-BG',
        product_name: 'Example steel sink',
        brand_name: null,
      },
    ]);
    render(<Page />);
    const dialog = await openPurchasingDialog();
    fireEvent.click(
      within(dialog).getByRole('radio', { name: /link an existing product code/i }),
    );
    fireEvent.click(await within(dialog).findByRole('combobox', { name: /product code/i }));
    const hit = await screen.findByRole('option', { name: /XY-1234-BG/ });
    expect(state.purchasing).not.toHaveBeenCalled();
    fireEvent.click(hit);
    expect(state.purchasing).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
    await waitFor(() => expect(state.purchasing).toHaveBeenCalledTimes(1));
    expect(state.purchasing.mock.calls[0][0].data).toMatchObject({
      outcome: 'link',
      product_id: 'p-9',
    });
  });
});

const OPEN = 'procurement.new_product_applications.open_code';
const approved = (over: Partial<Detail> = {}) =>
  detail({ status: 'approved', status_label: 'Approved', ...over });

describe('the table form', () => {
  it('shows Stock Inquiry\'s rows under the title and the line table, no Product N of M cards', () => {
    render(<Page />);
    expect(screen.getByText('NEW PRODUCT APPLICATION')).toBeInTheDocument();
    expect(screen.queryByText(/PRODUCT INQUIRY FORM/)).toBeNull();
    const text = document.body.textContent ?? '';
    let at = -1;
    for (const l of [
      'REFF:',
      'DATE:',
      'SALES PERSON:',
      'STOCK INQUIRY:',
      'PRODUCT CODES:',
      'CUSTOMER:',
      'PROJECT:',
      'TARGET DELIVERY:',
      'REMARK:',
      'NEW PRODUCT CODE:',
      'LEADTIME:',
    ]) {
      const i = text.indexOf(l, at + 1);
      expect(i, `row ${l} after ${at}`).toBeGreaterThan(at);
      at = i;
    }
    expect(screen.getByText('NPA-000001')).toBeInTheDocument();
    expect(screen.queryByText(/product \d+ of \d+/i)).toBeNull();
    for (const h of [/product code/i, /product type/i, /dimension/i, /qty/i, /cost \(myr\)/i])
      expect(screen.getByRole('columnheader', { name: h })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: /opened as/i })).toBeNull();
    expect(screen.getAllByRole('row').length).toBeGreaterThanOrEqual(3);
  });
});

describe('PURCHASING FEEDBACK (Edit purchasing response)', () => {
  const editor = () => {
    state.userId = 'u-buyer';
    state.perms = new Set([OPEN]);
  };

  it.each([['approved'], ['completed']])(
    'is edited by open_code on %s and Save sends lead time and one cost per line',
    async (status) => {
      editor();
      state.data = detail({ status: status as Detail['status'], status_label: status });
      render(<Page />);
      const dialog = await openPurchasingDialog();
      fireEvent.change(within(dialog).getByRole('textbox', { name: /lead ?time/i }), {
        target: { value: '3 weeks' },
      });
      fireEvent.change(within(dialog).getByLabelText('Cost for product 1'), {
        target: { value: '12.50' },
      });
      fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
      fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
      await waitFor(() => expect(state.purchasing).toHaveBeenCalledTimes(1));
      const arg = state.purchasing.mock.calls[0][0];
      expect(arg.id).toBe('a-1');
      expect(arg.data.lead_time).toBe('3 weeks');
      expect(arg.data.lines).toHaveLength(2);
      expect(arg.data.lines[0]).toEqual({ id: 'l-1', cost_price: '12.50' });
      expect(arg.data.lines[1].id).toBe('l-2');
      expect(arg.data.lines[1].cost_price ?? null).toBeNull();
    },
  );

  it('has no Edit purchasing response button on a draft, even for open_code', () => {
    editor();
    state.data = detail();
    render(<Page />);
    expect(button(/edit purchasing response/i)).toBeNull();
    expect(screen.queryByLabelText('Lead time')).toBeNull();
  });

  it('is read-only on an approved record without open_code, with the waiting line', () => {
    state.userId = 'u-owner';
    state.perms = new Set(['procurement.new_product_applications.create']);
    state.data = approved();
    render(<Page />);
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(screen.queryByLabelText(/^cost/i)).toBeNull();
    expect(button(/edit purchasing response/i)).toBeNull();
    expect(screen.getByText('Purchasing fills this after approval.')).toBeInTheDocument();
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

describe('read view shows plain values (S3)', () => {
  it('renders values as text, not disabled inputs; dates dd/mm/yyyy; empty as a dash', () => {
    state.data = detail({
      status: 'submitted',
      status_label: 'Submitted',
      needed_by: '2028-01-17',
    });
    state.userId = 'u-other';
    state.perms = new Set(['procurement.new_product_applications.view']);
    render(<Page />);
    expect(screen.queryAllByRole('textbox')).toHaveLength(0);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.queryAllByRole('spinbutton')).toHaveLength(0);
    expect(screen.getAllByText('Example kitchen sink').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Carton').length).toBeGreaterThan(0);
    expect(screen.getByText('17/01/2028')).toBeInTheDocument();
    expect(screen.getByText('17/10/2026')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});

describe('Cost inputs are uniquely named (S6)', () => {
  it('Cost for product 1 and 2 in the dialog for open_code on an approved record', async () => {
    state.userId = 'u-buyer';
    state.perms = new Set([OPEN]);
    state.data = approved();
    render(<Page />);
    const dialog = await openPurchasingDialog();
    expect(within(dialog).getByLabelText('Cost for product 1')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Cost for product 2')).toBeInTheDocument();
  });
});

describe('attachments panel', () => {
  const FILE = {
    link_id: 'k-1',
    attachment_id: 'at-1',
    filename: 'sample-doc.pdf',
    url: '/files/1',
    content_type: 'application/pdf',
  };

  it('lists the files and lets the owner of a Draft link and unlink (deferred, no confirm)', async () => {
    state.perms = new Set(['procurement.new_product_applications.create']);
    state.data = detail({ attachments: [FILE] } as never);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<Page />);
    expect(screen.getByText('sample-doc.pdf')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));
    fireEvent.click(await screen.findByRole('button', { name: /pick library file/i }));
    await waitFor(() => expect(state.linkAtt).toHaveBeenCalledWith('a-1', 'at-5'));

    fireEvent.click(screen.getByRole('button', { name: /unlink sample-doc\.pdf/i }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(state.unlinkRun).toHaveBeenCalledWith(expect.objectContaining({ id: 'k-1' }));
    expect(
      state.unlinkInputs.some(
        (i) => i.actionKey === 'new_product_application_attachment.unlink',
      ),
    ).toBe(true);
    confirmSpy.mockRestore();
  });

  it('lists the files but offers no Link or Unlink once the application is Submitted', () => {
    state.perms = new Set(['procurement.new_product_applications.create']);
    state.data = detail({
      status: 'submitted',
      status_label: 'Submitted',
      attachments: [FILE],
    } as never);
    render(<Page />);
    expect(screen.getByText('sample-doc.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /link attachment/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /unlink/i })).toBeNull();
  });

  it('offers no Link to someone who does not own the draft', () => {
    state.userId = 'u-other';
    state.perms = new Set(['procurement.new_product_applications.view']);
    state.data = detail({ attachments: [FILE] } as never);
    render(<Page />);
    expect(screen.queryByRole('button', { name: /link attachment/i })).toBeNull();
  });
});

describe('attachments list is the shared PanelDataGrid', () => {
  it('renders the files through PanelDataGrid', () => {
    state.perms = new Set(['procurement.new_product_applications.create']);
    state.data = detail({
      attachments: [
        {
          link_id: 'k-1',
          attachment_id: 'at-1',
          filename: 'sample-doc.pdf',
          url: '/files/1',
          content_type: 'application/pdf',
        },
      ],
    } as never);
    render(<Page />);
    // PRINCIPLES: the attachments list is the shared PanelDataGrid, not a hand-rolled table
    const cell = screen.getByText('sample-doc.pdf');
    expect(cell.closest('table')).toHaveAttribute('data-slot', 'data-grid-table');
    const panel = cell.closest('[data-slot="card"]');
    expect(panel).not.toBeNull();
    expect(
      within(panel as HTMLElement).getByRole('button', { name: /link attachment/i }),
    ).toBeInTheDocument();
  });
});

describe('From AutoCount (header)', () => {
  it('shows the linked product item group, base UOM, list price and supplier read-only', () => {
    state.userId = 'u-buyer';
    state.perms = new Set([OPEN]);
    state.data = approved({
      new_product_id: 'p-1',
      new_product_code: 'XY-1234-MB',
      new_product_name: 'Example kitchen sink',
      new_product_active: true,
      new_product_facts: {
        opened_category_name: 'Example Group',
        opened_base_uom_name: 'Example UOM',
        opened_list_price: '185.00',
        opened_supplier_name: 'Example Supplier Co',
      },
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

describe('NEW PRODUCT CODE (header)', () => {
  const earlier = {
    product_id: 'p-69',
    product_code: 'XY-1234-MB-69',
    product_name: 'Example sink 69',
    is_active: true,
    description: 'no tap hole',
    created_at: '2026-11-03T02:00:00',
    application_id: 'a-0',
    application_no: 'NPA-000123',
  };

  beforeEach(() => {
    state.data = approved({
      current_products: [
        { id: 'p-1', product_code: 'XY-1234-MB', product_name: 'Sink' },
      ],
      suggestions: [earlier],
    });
    state.userId = 'u-buyer';
    state.perms = new Set([OPEN]);
  });

  it('has no Opened as column and the table keeps its paper columns', () => {
    render(<Page />);
    expect(screen.queryByRole('columnheader', { name: /opened as/i })).toBeNull();
    expect(screen.getByRole('columnheader', { name: /cost \(myr\)/i })).toBeInTheDocument();
  });

  it('keeps the suggestion out of the page; Use <code> in the dialog pre-selects Link and saves nothing', async () => {
    render(<Page />);
    expect(screen.queryByText(/Created before:/)).toBeNull();
    const dialog = await openPurchasingDialog();
    expect(within(dialog).getByText(/Created before:/).textContent).toContain(
      'XY-1234-MB-69 (NPA-000123)',
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use XY-1234-MB-69' }));
    expect(
      within(dialog).getByRole('radio', { name: /link an existing product code/i }),
    ).toBeChecked();
    expect(state.purchasing).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
    await waitFor(() => expect(state.purchasing).toHaveBeenCalledTimes(1));
    expect(state.purchasing.mock.calls[0][0].data).toMatchObject({
      outcome: 'link',
      product_id: 'p-69',
    });
  });

  it('Reject (header) needs a reason, then rejects through purchasingReject', async () => {
    render(<Page />);
    fireEvent.click(await screen.findByRole('button', { name: /^reject$/i }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: /^reject$/i });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByRole('textbox', { name: /rejection reason/i }), {
      target: { value: 'Supplier cannot make it' },
    });
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(state.purchasingReject).toHaveBeenCalledWith({
        id: 'a-1',
        reason: 'Supplier cannot make it',
      }),
    );
  });

  it('shows the linked code read-only, with no Undo or Link controls', () => {
    state.data = approved({
      new_product_id: 'p-69',
      new_product_code: 'XY-1234-MB-69',
      new_product_name: 'Example sink 69',
      new_product_active: false,
      new_code_by_name: 'Buyer',
      new_code_at: '2026-11-03T02:00:00',
    });
    render(<Page />);
    expect(screen.getByRole('link', { name: /XY-1234-MB-69/ })).toHaveAttribute(
      'href',
      '/master-data-management/products/p-69',
    );
    expect(screen.getByText('Inactive')).toBeInTheDocument();
    expect(button(/^undo$/i)).toBeNull();
    expect(button(/^link/i)).toBeNull();
  });

  it('shows an older closed one as Rejected with the reason, and no Edit button to a viewer without open_code', () => {
    state.perms = new Set();
    state.data = approved({ new_code_closed_reason: 'Customer walked away' });
    render(<Page />);
    expect(screen.getByText('Rejected: Customer walked away')).toBeInTheDocument();
    expect(button(/edit purchasing response/i)).toBeNull();
    expect(button(/^undo$/i)).toBeNull();
  });
});

describe('Stock inquiry tab', () => {
  it('shows the inquiry with a link to it, its status, response and qty', () => {
    state.data = detail({
      stock_inquiry: {
        id: 'si-1',
        inquiry_number: 'SI26-0412',
        product_code: 'XY-1234-MB',
        status: 'responded',
        item_description: 'Kitchen sink',
        purchasing_response: 'Supplier can do it',
        quantity: '55',
      },
    });
    render(<Page />);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Stock inquiry' }));
    const link = screen.getByRole('link', { name: 'SI26-0412' });
    expect(link).toHaveAttribute(
      'href',
      '/procurement-management/stock-inquiries/si-1',
    );
    expect(screen.getByText('Responded')).toBeInTheDocument();
    expect(screen.getByText('Supplier can do it')).toBeInTheDocument();
    expect(screen.getByText('Kitchen sink')).toBeInTheDocument();
  });

  it('says there is none for an application raised from the list', () => {
    state.data = detail({ stock_inquiry: null });
    render(<Page />);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Stock inquiry' }));
    expect(screen.getByText('No stock inquiry')).toBeInTheDocument();
    expect(
      screen.getByText('Applications raised from a stock inquiry show it here.'),
    ).toBeInTheDocument();
  });
});

describe('older applications worked row by row (NPA-FROM-SI v3)', () => {
  const opened = () =>
    approved({
      lines_done: 2,
      lines: [
        line({
          opened_product_id: 'p-9',
          opened_product_code: 'XY-1234-MB-9',
          opened_product_name: 'Example sink 9',
          opened_product_active: true,
        }),
        line({
          id: 'l-2',
          line_no: 2,
          proposed_code: 'XY-1234-BG',
          closed_reason: 'Customer walked away',
        }),
        line({ id: 'l-3', line_no: 3, proposed_code: 'XY-1234-ZZ' }),
      ],
    });

  it('shows the Opened as column with the opened code and the Rejected reason per row', () => {
    state.data = opened();
    state.perms = new Set([OPEN]);
    render(<Page />);
    expect(screen.getByRole('columnheader', { name: /opened as/i })).toBeInTheDocument();
    const rows = screen.getAllByTestId('npa-line');
    expect(within(rows[0]).getByText(/XY-1234-MB-9/)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/Rejected: Customer walked away/)).toBeInTheDocument();
    expect(within(rows[2]).queryByText(/Rejected:/)).toBeNull();
    expect(within(rows[2]).queryByText(/XY-1234-MB-9/)).toBeNull();
  });

  it('keeps Undo on a resolved row for open_code, and it undoes that row', () => {
    state.data = opened();
    state.perms = new Set([OPEN]);
    render(<Page />);
    const rows = screen.getAllByTestId('npa-line');
    fireEvent.click(within(rows[0]).getByRole('button', { name: 'Undo' }));
    expect(state.undoLine).toHaveBeenCalledWith({ id: 'a-1', lineId: 'l-1' });
    expect(within(rows[2]).queryByRole('button', { name: 'Undo' })).toBeNull();
  });

  it('shows the column but no Undo to a viewer without open_code', () => {
    state.data = opened();
    state.perms = new Set();
    render(<Page />);
    expect(screen.getByRole('columnheader', { name: /opened as/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
  });

  it('shows no Opened as column when no line is resolved', () => {
    state.data = approved();
    state.perms = new Set([OPEN]);
    render(<Page />);
    expect(screen.queryByRole('columnheader', { name: /opened as/i })).toBeNull();
  });

  it('has no Brand column', () => {
    state.data = opened();
    render(<Page />);
    expect(screen.queryByRole('columnheader', { name: /brand/i })).toBeNull();
  });
});

describe('Stock inquiry tab status is a Badge (NPA-FROM-SI)', () => {
  it('draws the inquiry status through the Badge component', () => {
    state.data = detail({
      stock_inquiry: {
        id: 'si-1',
        inquiry_number: 'SI26-0412',
        product_code: 'XY-1234-MB',
        status: 'responded',
        item_description: 'Kitchen sink',
        purchasing_response: 'ok',
        quantity: '55',
      },
    });
    render(<Page />);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Stock inquiry' }));
    const pill = screen.getByText('Responded');
    const badge = pill.closest('[data-slot="badge"]');
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toContain('Responded');
  });
});


describe('NPA-FORM-SLA: the SI\'s SLA tab and handling lock', () => {
  beforeEach(() => {
    lock.enabled = true;
    lock.input = null;
  });

  it('offers SLA Tracking to a view-all holder and renders the SI tracker tab for this NPA', () => {
    state.perms = new Set(['procurement.new_product_applications.approve']);
    state.data = detail({ status: 'submitted', status_label: 'Submitted', submitted_at: '2026-11-08T01:00:00' });
    render(<Page />);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'SLA Tracking' }));
    fireEvent.click(screen.getByRole('tab', { name: 'SLA Tracking' }));
    expect(screen.getByTestId('sla-tab')).toHaveTextContent('new_product_application:a-1');
    expect(lock.input).toMatchObject({ sourceEntityType: 'new_product_application', enabled: true });
  });

  it('hides SLA Tracking from an applicant without a view-all slug, and reads no tracker', () => {
    state.perms = new Set(['procurement.new_product_applications.create']);
    state.data = detail();
    render(<Page />);
    expect(screen.queryByRole('tab', { name: 'SLA Tracking' })).not.toBeInTheDocument();
    expect(lock.input).toMatchObject({ enabled: false, sourceEntityId: null });
  });

  it('disables Approve and Reject while another person holds the escalated stage', () => {
    lock.enabled = false;
    state.perms = new Set(['procurement.new_product_applications.approve']);
    state.data = detail({ status: 'submitted', status_label: 'Submitted', submitted_at: '2026-11-08T01:00:00' });
    render(<Page />);
    const approve = screen.getByRole('button', { name: 'Approve' });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute('title', 'Being handled by Purchasing Manager - take over to act');
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });

  it('disables Edit purchasing response while the purchasing stage is held by someone else', () => {
    lock.enabled = false;
    state.perms = new Set(['procurement.new_product_applications.open_code']);
    state.data = detail({ status: 'approved', status_label: 'Approved', submitted_at: '2026-11-08T01:00:00' });
    render(<Page />);
    expect(screen.getByRole('button', { name: 'Edit purchasing response' })).toBeDisabled();
  });
});
