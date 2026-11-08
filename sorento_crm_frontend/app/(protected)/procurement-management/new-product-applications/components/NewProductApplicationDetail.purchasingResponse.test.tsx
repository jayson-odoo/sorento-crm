/**
 * NPA-FROM-SI (owner hand test, 8 Nov): purchasing answers in ONE dialog, like the stock inquiry's
 * "Edit purchasing response". Real hooks and service run; only the network edge (`apiFetch`) is
 * stubbed, so the assertions are on the HTTP calls: `PUT .../{id}/purchasing-response`.
 *
 * Assumed controls inside the dialog (the coder matches them):
 *   radios "Link an existing product code" / "New product code" / "No answer yet" (answered records only);
 *   Link: a combobox named /product code/i (product search); New: a textbox named /new product code/i;
 *   a textbox "Lead time"; "Cost (MYR)" (no lines) or
 *   "Cost for product N" (lines); a "Save" button.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  data: undefined as unknown,
  calls: [] as { url: string; method: string; body: unknown }[],
  onReject: null as null | ((reason: string) => unknown),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/procurement-management/new-product-applications/a-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  usePermissions: () => ({ permissionSet: state.perms, isLoading: false }),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => 'u-buyer' }));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ gear, primary }: { gear?: React.ReactNode; primary?: React.ReactNode }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
    <button onClick={() => onSelect?.()}>{children}</button>
  ),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: () => Promise.resolve(), isLoading: false }),
}));
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({ __esModule: true, default: () => null }));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

vi.mock('@/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...original,
    apiFetch: async (url: string, init?: { method?: string; body?: string }) => {
      const method = init?.method ?? 'GET';
      state.calls.push({ url, method, body: init?.body ? JSON.parse(init.body) : undefined });
      if (/\/products\?q=/.test(url)) {
        return json([{ id: 'p-69', product_code: 'XY-1234-MB-69', product_name: 'Example sink 69', brand_name: null }]);
      }
      if (/\/purchasing-reject$/.test(url) && method === 'POST') {
        if (state.onReject) state.data = state.onReject((init?.body ? JSON.parse(init.body) : {}).reason);
        return json(state.data);
      }
      if (/\/purchasing-response$/.test(url)) return json(state.data);
      if (/\/new-product-applications\/a-1(\?.*)?$/.test(url) && method === 'GET') return json(state.data);
      return json({ items: [], data: [], pagination: { total: 0, page: 1, limit: 20 } });
    },
  };
});

import NewProductApplicationDetail from './NewProductApplicationDetail';

const OPEN = 'procurement.new_product_applications.open_code';
const VIEW = 'procurement.new_product_applications.view';

function Page() {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NewProductApplicationDetail applicationId="a-1" />
    </QueryClientProvider>
  );
}

const line = (over: Record<string, unknown> = {}) => ({
  id: 'l-1',
  line_no: 1,
  proposed_code: 'XY-1234-MB',
  description: 'Example kitchen sink',
  dimension: null,
  material: null,
  thickness: null,
  packing: null,
  brand_id: null,
  brand_name: null,
  expected_qty: '55',
  cost_price: null,
  opened_product_id: null,
  opened_product_code: null,
  closed_reason: null,
  ...over,
});

const app = (over: Record<string, unknown> = {}) => ({
  id: 'a-1',
  application_no: 'NPA-000001',
  status: 'approved',
  status_label: 'Approved',
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
  first_line: null,
  lines_total: 0,
  lines_done: 0,
  opened_codes: [],
  needed_by: null,
  submitted_at: null,
  created_at: '2026-10-17T01:00:00',
  updated_at: null,
  remark: null,
  lead_time: null,
  cost_price: null,
  new_code_text: null,
  new_product_id: null,
  new_product_code: null,
  new_code_closed_reason: null,
  current_products: [],
  suggestions: [],
  attachments: [],
  lines: [],
  ...over,
});

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

const puts = () => state.calls.filter((c) => c.method === 'PUT' && /purchasing-response$/.test(c.url));
const editButton = () => screen.queryByRole('button', { name: /^edit purchasing response$/i });

async function openDialog() {
  fireEvent.click(await screen.findByRole('button', { name: /^edit purchasing response$/i }));
  return screen.findByRole('dialog');
}

beforeEach(() => {
  vi.clearAllMocks();
  state.calls = [];
  state.perms = new Set([VIEW, OPEN]);
  state.data = app();
  state.onReject = null;
});

describe('inline purchasing controls are gone', () => {
  it('no NEW PRODUCT CODE picker, Link product, Not opening, Undo, inline Lead time or Save feedback', async () => {
    state.data = app({ suggestions: [earlier] });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    await screen.findByRole('button', { name: /^edit purchasing response$/i });
    for (const name of [/^link product$/i, /^not opening$/i, /^undo$/i, /^save feedback$/i, /^use /i, /^link$/i]) {
      expect(screen.queryByRole('button', { name })).toBeNull();
    }
    expect(screen.queryByRole('combobox', { name: /new product code/i })).toBeNull();
    expect(screen.queryByLabelText(/^lead ?time/i)).toBeNull();
    expect(screen.queryByText(/Created before:/)).toBeNull();
  });

  it('a Completed record has no inline Undo either', async () => {
    state.data = app({
      status: 'completed',
      status_label: 'Completed',
      new_product_id: 'p-69',
      new_product_code: 'XY-1234-MB-69',
    });
    render(<Page />);
    await screen.findByText('XY-1234-MB-69');
    expect(screen.queryByRole('button', { name: /^undo$/i })).toBeNull();
  });
});

describe('the Edit purchasing response button', () => {
  it.each([
    ['approved', 'Approved'],
    ['completed', 'Completed'],
  ])('is shown to an open_code holder on %s', async (status, label) => {
    state.data = app({ status, status_label: label });
    render(<Page />);
    expect(await screen.findByRole('button', { name: /^edit purchasing response$/i })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /edit purchasing response/i })).toHaveLength(1);
  });

  it('is absent without open_code', async () => {
    state.perms = new Set([VIEW]);
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(editButton()).toBeNull();
  });

  it.each([['draft'], ['submitted'], ['rejected'], ['cancelled']])('is absent on %s', async (status) => {
    state.data = app({ status, status_label: status });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(editButton()).toBeNull();
  });
});

describe('the dialog', () => {
  it('is titled like the stock inquiry one and offers the three outcomes, Lead time, one Cost and Save', async () => {
    render(<Page />);
    const dialog = await openDialog();
    expect(within(dialog).getByText('Edit purchasing response')).toBeInTheDocument();
    expect(within(dialog).getByRole('radio', { name: /link an existing product code/i })).toBeInTheDocument();
    expect(within(dialog).getByRole('radio', { name: /^new product code$/i })).toBeInTheDocument();
    expect(within(dialog).queryByRole('radio', { name: /not opening/i })).toBeNull();
    expect(within(dialog).queryByRole('textbox', { name: /reason/i })).toBeNull();
    expect(within(dialog).getByRole('textbox', { name: /lead ?time/i })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Cost (MYR)')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/^Cost for product/)).toBeNull();
    expect(within(dialog).getByRole('button', { name: /^save$/i })).toBeInTheDocument();
  });

  it('with lines, asks one cost per line and no single cost', async () => {
    state.data = app({
      lines: [line(), line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' })],
      lines_total: 2,
    });
    render(<Page />);
    const dialog = await openDialog();
    expect(within(dialog).getByLabelText('Cost for product 1')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Cost for product 2')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Cost (MYR)')).toBeNull();
  });

  it('starts from the saved lead time', async () => {
    state.data = app({ lead_time: '3 weeks' });
    render(<Page />);
    const dialog = await openDialog();
    expect((within(dialog).getByRole('textbox', { name: /lead ?time/i }) as HTMLInputElement).value).toBe('3 weeks');
  });
});

describe('Save calls PUT purchasing-response once', () => {
  it('Link: outcome link, the picked product id, lead time and cost', async () => {
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('radio', { name: /link an existing product code/i }));
    fireEvent.click(await within(dialog).findByRole('combobox', { name: /product code/i }));
    fireEvent.click(await screen.findByText(/XY-1234-MB-69/));
    fireEvent.change(within(dialog).getByRole('textbox', { name: /lead ?time/i }), { target: { value: '3 weeks' } });
    fireEvent.change(within(dialog).getByLabelText('Cost (MYR)'), { target: { value: '12.50' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as Record<string, unknown>;
    expect(body).toMatchObject({ outcome: 'link', product_id: 'p-69', lead_time: '3 weeks' });
    expect(Number(body.cost_price)).toBe(12.5);
    expect(puts()[0].url).toContain('/a-1/purchasing-response');
  });

  it('New product code: outcome new with the typed code', async () => {
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('radio', { name: /^new product code$/i }));
    fireEvent.change(await within(dialog).findByRole('textbox', { name: /new product code/i }), {
      target: { value: 'XY-NEW-1' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toMatchObject({ outcome: 'new', new_code: 'XY-NEW-1' });
  });

  it('has no Not opening choice and no reason box, even on an answered record (Reject replaced it)', async () => {
    state.data = app({
      status: 'completed',
      status_label: 'Completed',
      new_product_id: 'p-1',
      new_product_code: 'XY-1234-MB-1',
    });
    render(<Page />);
    const dialog = await openDialog();
    expect(within(dialog).queryByText(/not opening/i)).toBeNull();
    expect(within(dialog).queryByLabelText(/reason/i)).toBeNull();
    expect(within(dialog).getByRole('radio', { name: /link an existing product code/i })).toBeInTheDocument();
    expect(within(dialog).getByRole('radio', { name: /^new product code$/i })).toBeInTheDocument();
    expect(within(dialog).getByRole('radio', { name: /no answer yet/i })).toBeInTheDocument();
    expect(within(dialog).getByRole('textbox', { name: /lead ?time/i })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Cost (MYR)')).toBeInTheDocument();
  });

  it('sends no outcome key when only the lead time changed on an answered record', async () => {
    state.data = app({
      status: 'completed',
      status_label: 'Completed',
      new_product_id: 'p-1',
      new_product_code: 'XY-1234-MB-1',
    });
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.change(within(dialog).getByRole('textbox', { name: /lead ?time/i }), { target: { value: '5 weeks' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as Record<string, unknown>;
    expect(body.lead_time).toBe('5 weeks');
    expect(body).not.toHaveProperty('outcome');
  });

  it('with lines, sends one cost per line id', async () => {
    state.data = app({
      lines: [line(), line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' })],
      lines_total: 2,
    });
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.change(within(dialog).getByLabelText('Cost for product 1'), { target: { value: '10' } });
    fireEvent.change(within(dialog).getByLabelText('Cost for product 2'), { target: { value: '20.5' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as { lines: { id: string; cost_price: unknown }[] };
    expect(body.lines.map((l) => [l.id, Number(l.cost_price)])).toEqual([
      ['l-1', 10],
      ['l-2', 20.5],
    ]);
    expect(body).not.toHaveProperty('cost_price');
  });
});

describe('"Created before" suggestion lives in the dialog', () => {
  it('is only inside the dialog; Use pre-selects Link + the code and does not save', async () => {
    state.data = app({ suggestions: [earlier] });
    render(<Page />);
    await screen.findByRole('button', { name: /^edit purchasing response$/i });
    expect(screen.queryByText(/Created before:/)).toBeNull();
    const dialog = await openDialog();
    expect(within(dialog).getByText(/Created before:/).textContent).toContain('XY-1234-MB-69 (NPA-000123)');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use XY-1234-MB-69' }));
    expect(within(dialog).getByRole('radio', { name: /link an existing product code/i })).toBeChecked();
    expect(within(dialog).getAllByText(/XY-1234-MB-69/).length).toBeGreaterThan(1);
    expect(puts()).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toMatchObject({ outcome: 'link', product_id: 'p-69' });
  });
});

describe('the result, read-only on the detail', () => {
  it('shows a typed new code, LEADTIME and COST', async () => {
    state.data = app({
      status: 'completed',
      status_label: 'Completed',
      new_product_id: null,
      new_product_code: 'XY-TYPED-7',
      new_code_text: 'XY-TYPED-7',
      lead_time: '3 weeks',
      cost_price: '12.50',
    });
    render(<Page />);
    expect(await screen.findByText('XY-TYPED-7')).toBeInTheDocument();
    expect(screen.getByText('3 weeks')).toBeInTheDocument();
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^lead ?time/i)).toBeNull();
  });

  it('an older application closed as not opening reads Rejected: x, with a Rejected pill, never Not opening', async () => {
    state.data = app({
      status: 'completed',
      status_label: 'Rejected',
      new_code_closed_reason: 'x',
    });
    render(<Page />);
    expect(await screen.findByText('Rejected: x')).toBeInTheDocument();
    expect(screen.getAllByText('Rejected').length).toBeGreaterThan(0);
    expect(screen.queryByText(/not opening/i)).toBeNull();
  });

  it('shows the waiting text while unanswered', async () => {
    render(<Page />);
    expect(await screen.findByText('Purchasing fills this in when the code is created.')).toBeInTheDocument();
  });
});

describe('product table on the staff detail', () => {
  it('an SI application with no lines draws no table', async () => {
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByRole('columnheader', { name: /product code/i })).toBeNull();
    expect(screen.queryAllByTestId('npa-line')).toHaveLength(0);
  });

  it('an older SI application with lines shows them read-only', async () => {
    state.data = app({ lines: [line(), line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' })], lines_total: 2 });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.getAllByTestId('npa-line')).toHaveLength(2);
    expect(screen.queryByLabelText('Product type')).toBeNull();
    expect(screen.queryByRole('button', { name: /add (row|product)/i })).toBeNull();
  });

  it('a standalone application keeps its table', async () => {
    state.data = app({
      stock_inquiry_id: null,
      stock_inquiry_number: null,
      lines: [line()],
      lines_total: 1,
    });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.getByRole('columnheader', { name: /product code/i })).toBeInTheDocument();
    expect(screen.getAllByTestId('npa-line')).toHaveLength(1);
  });
});

describe('reviewer round 4: typed earlier code, No answer yet, no prose', () => {
  const typedEarlier = { ...earlier, product_id: null, product_code: 'XY-TYPED-9' };

  it('Use on a typed earlier code (no product id) pre-selects New product code with the code filled, never Link', async () => {
    state.data = app({ suggestions: [typedEarlier] });
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use XY-TYPED-9' }));
    expect(within(dialog).getByRole('radio', { name: /^new product code$/i })).toBeChecked();
    expect(
      (within(dialog).getByRole('textbox', { name: /new product code/i }) as HTMLInputElement).value,
    ).toBe('XY-TYPED-9');
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as Record<string, unknown>;
    expect(body).toMatchObject({ outcome: 'new', new_code: 'XY-TYPED-9' });
    expect(body).not.toHaveProperty('product_id');
  });

  it('offers No answer yet only when the application has an answer, and saving it sends outcome null', async () => {
    state.data = app({ status: 'completed', status_label: 'Completed', new_code_text: 'XY-TYPED-7', new_product_code: 'XY-TYPED-7' });
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('radio', { name: /^no answer yet$/i }));
    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as Record<string, unknown>;
    expect(body).toHaveProperty('outcome', null);
  });

  it('has no No answer yet radio while the application is unanswered', async () => {
    render(<Page />);
    const dialog = await openDialog();
    expect(within(dialog).queryByRole('radio', { name: /no answer yet/i })).toBeNull();
  });

  it('shows no explanation prose in the dialog', async () => {
    render(<Page />);
    const dialog = await openDialog();
    expect(within(dialog).queryByText(/Save records the new product code/i)).toBeNull();
  });
});

describe('purchasing Reject replaces Not opening (owner 8 Nov 09:30)', () => {
  const rejects = () => state.calls.filter((c) => c.method === 'POST' && /purchasing-reject$/.test(c.url));
  const headerReject = () => screen.queryByRole('button', { name: /^reject$/i });

  it('an open_code holder on Approved sees a secondary Reject next to Edit purchasing response, styled like the stock inquiry one', async () => {
    render(<Page />);
    await screen.findByRole('button', { name: /^edit purchasing response$/i });
    const btn = headerReject();
    expect(btn).not.toBeNull();
    expect(btn!.className).toMatch(/text-destructive/);
    expect(btn!.className).toMatch(/border-destructive/);
    expect(btn!.querySelector('svg.lucide-circle-x, svg.lucide-x-circle')).not.toBeNull();
    expect(btn!.parentElement).toBe(
      screen.getByRole('button', { name: /^edit purchasing response$/i }).parentElement,
    );
  });

  it.each([['submitted'], ['resubmitted'], ['completed'], ['draft']])('has no purchasing Reject on %s', async (status) => {
    state.data = app({ status, status_label: status });
    state.perms = new Set([VIEW, OPEN]);
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(headerReject()).toBeNull();
  });

  it('has none for a user without open_code', async () => {
    state.perms = new Set([VIEW]);
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(headerReject()).toBeNull();
  });

  it('opens the reject dialog with a required reason; Confirm stays disabled while blank', async () => {
    render(<Page />);
    await screen.findByRole('button', { name: /^edit purchasing response$/i });
    fireEvent.click(headerReject()!);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Reject new product application')).toBeInTheDocument();
    const box = within(dialog).getByRole('textbox', { name: /rejection reason/i });
    const confirm = within(dialog).getByRole('button', { name: /^(confirm|reject)$/i });
    expect(confirm).toBeDisabled();
    fireEvent.change(box, { target: { value: '   ' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(box, { target: { value: 'Supplier cannot make it' } });
    expect(confirm).toBeEnabled();
  });

  it('Confirm POSTs purchasing-reject with the reason, and the page then shows Rejected with it', async () => {
    state.onReject = (reason) =>
      app({ status: 'rejected', status_label: 'Rejected', reject_reason: reason, decided_by_name: 'Buyer' });
    render(<Page />);
    await screen.findByRole('button', { name: /^edit purchasing response$/i });
    fireEvent.click(headerReject()!);
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('textbox', { name: /rejection reason/i }), {
      target: { value: 'Supplier cannot make it' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^(confirm|reject)$/i }));
    await waitFor(() => expect(rejects()).toHaveLength(1));
    expect(rejects()[0].url).toContain('/api/v1/procurement/new-product-applications/a-1/purchasing-reject');
    expect(rejects()[0].body).toEqual({ reason: 'Supplier cannot make it' });
    expect(await screen.findByText('Supplier cannot make it')).toBeInTheDocument();
    expect(screen.getAllByText('Rejected').length).toBeGreaterThan(0);
  });
});

describe('no lock banner while Submitted or Resubmitted (owner 8 Nov 09:30)', () => {
  it.each([
    ['submitted', 'Submitted'],
    ['resubmitted', 'Resubmitted'],
  ])('shows neither "Waiting for approval." nor the Locked sentence on %s', async (status, label) => {
    state.data = app({ status, status_label: label });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByText(/Waiting for approval/)).toBeNull();
    expect(screen.queryByText(/Locked: Revise to change it/)).toBeNull();
  });

  it('Approved keeps "Approved by X on D."', async () => {
    state.data = app({ decided_by_name: 'Approver One', decided_at: '2026-11-02T01:00:00' });
    render(<Page />);
    expect(await screen.findByText(/Approved by Approver One on /)).toBeInTheDocument();
  });
});
