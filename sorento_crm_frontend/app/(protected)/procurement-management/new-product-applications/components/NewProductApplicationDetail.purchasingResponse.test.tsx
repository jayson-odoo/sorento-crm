/**
 * NPA-FROM-SI (owner hand test, 8 Nov): purchasing answers in ONE dialog, like the stock inquiry's
 * "Edit purchasing response". Real hooks and service run; only the network edge (`apiFetch`) is
 * stubbed, so the assertions are on the HTTP calls: `PUT .../{id}/purchasing-response`.
 *
 * Assumed controls inside the dialog (the coder matches them):
 *   radios "Link an existing product code" / "New product code";
 *   Link: a combobox named /product code/i (product search); New: a textbox named /new product code/i;
 *   the shared PurchasingResponseDialog (data-testid purchasing-response-dialog) whose first field is the
 *   "Purchasing response" textarea, buttons Cancel / "Save only" / "Update & Reply" (only when detail.can_reply);
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
      if (/\/purchasing-response(\/reply)?$/.test(url)) return json(state.data);
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
  opened_codes: [],
  needed_by: null,
  submitted_at: null,
  created_at: '2026-10-17T01:00:00',
  updated_at: null,
  remark: null,
  lead_time: null,
  cost_price: null,
  purchasing_response: null,
  can_reply: false,
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

describe('crew pass 8 Nov', () => {
  it("(d) the dialog carries the stock inquiry's description line when it can reply", async () => {
    state.data = app({ can_reply: true });
    render(<Page />);
    const dialog = await openDialog();
    expect(
      within(dialog).getByText(
        'Save updates the record only. Update & Reply saves your text and sends it to the contact.',
      ),
    ).toBeVisible();
  });

  it('(d) owner re-test 9 Nov: with no reply, the line says why and names no missing button', async () => {
    state.data = app({ can_reply: false });
    render(<Page />);
    const dialog = await openDialog();
    expect(
      within(dialog).getByText(
        'Save updates the record only. No reply: this application was not raised from a stock inquiry conversation or in the portal.',
      ),
    ).toBeInTheDocument();
    expect(within(dialog).queryByText(/Update & Reply/)).toBeNull();
  });

  it('(d) owner 9 Nov ~02:30: a portal-raised NPA replies through the portal, and says so', async () => {
    state.data = app({ can_reply: true, reply_channel: 'portal' });
    render(<Page />);
    const dialog = await openDialog();
    expect(
      within(dialog).getByText(
        'Save updates the record only. Update & Reply saves your text and notifies the applicant in the portal.',
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /update & reply/i })).toBeInTheDocument();
  });

  it('(c) a long PROJECT clamps, with the full text in its title and behind the eye button', async () => {
    const long = 'CADANGAN PEMBANGUNAN BERCAMPUR 2 BLOK PANGSAPURI SERVIS 38 TINGKAT '.repeat(9).trim();
    state.data = app({ project_name: long });
    render(<Page />);
    const value = await screen.findByTitle(long);
    expect(value.className).toMatch(/line-clamp-2/);
    expect(value).toHaveTextContent(long);
  });
});

describe('owner hand test 8 Nov 20:45: the Link picker opens with something to pick', () => {
  it('opens the picker on the linked code (the search starts from it)', async () => {
    state.data = app({
      status: 'completed',
      status_label: 'Completed',
      new_product_id: 'p-1',
      new_product_code: 'CB313',
    });
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.click(await within(dialog).findByRole('combobox', { name: /product code/i }));
    await waitFor(() =>
      expect(state.calls.some((c) => /\/products\?q=CB313(&|$)/.test(c.url))).toBe(true),
    );
  });

  it('with nothing linked it opens on an empty search (the server lists products)', async () => {
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('radio', { name: /link an existing product code/i }));
    fireEvent.click(await within(dialog).findByRole('combobox', { name: /product code/i }));
    await waitFor(() =>
      expect(state.calls.some((c) => /\/products\?q=(&|$)/.test(c.url))).toBe(true),
    );
    expect(await within(document.body).findByText('XY-1234-MB-69')).toBeInTheDocument();
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
    expect(within(dialog).getByRole('button', { name: /^save only$/i })).toBeInTheDocument();
  });

  it('with lines, asks one cost per line and no single cost', async () => {
    state.data = app({
      lines: [line(), line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' })],
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
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
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
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
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
    expect(within(dialog).queryByRole('radio', { name: /no answer yet/i })).toBeNull();
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
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as Record<string, unknown>;
    expect(body.lead_time).toBe('5 weeks');
    expect(body).not.toHaveProperty('outcome');
  });

  it('with lines, sends one cost per line id', async () => {
    state.data = app({
      lines: [line(), line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' })],
    });
    render(<Page />);
    const dialog = await openDialog();
    fireEvent.change(within(dialog).getByLabelText('Cost for product 1'), { target: { value: '10' } });
    fireEvent.change(within(dialog).getByLabelText('Cost for product 2'), { target: { value: '20.5' } });
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
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
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
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

  it('an older application with lines, SI or standalone, draws no table (owner hand test 9 Nov)', async () => {
    state.data = app({
      stock_inquiry_id: null,
      stock_inquiry_number: null,
      lines: [line(), line({ id: 'l-2', line_no: 2, proposed_code: 'XY-1234-BG' })],
    });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByRole('columnheader', { name: /product code/i })).toBeNull();
    expect(screen.queryAllByTestId('npa-line')).toHaveLength(0);
  });
});

describe('reviewer round 4: typed earlier code, no prose', () => {
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
    fireEvent.change(within(dialog).getByRole('textbox', { name: /purchasing response/i }), { target: { value: 'We can supply' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    const body = puts()[0].body as Record<string, unknown>;
    expect(body).toMatchObject({ outcome: 'new', new_code: 'XY-TYPED-9' });
    expect(body).not.toHaveProperty('product_id');
  });

  it.each([['unanswered', {}], ['answered', { status: 'completed', status_label: 'Completed', new_code_text: 'XY-TYPED-7', new_product_code: 'XY-TYPED-7' }]])(
    'has no No answer yet option while %s (the stock inquiry has no equivalent)',
    async (_name, over) => {
      state.data = app(over as Record<string, unknown>);
      render(<Page />);
      const dialog = await openDialog();
      expect(within(dialog).queryByRole('radio', { name: /no answer yet/i })).toBeNull();
      expect(within(dialog).queryByText(/no answer yet/i)).toBeNull();
    },
  );

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
    // The SAME button as the stock inquiry's (crew pass 3): the lighter red border.
    expect(btn!.className).toMatch(/border-destructive\/40/);
    expect(btn!.className).toMatch(/hover:bg-destructive\/10/);
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

  it('the reject confirm is destructive, like the stock inquiry one (browser pass 8 Nov)', async () => {
    render(<Page />);
    await screen.findByRole('button', { name: /^edit purchasing response$/i });
    fireEvent.click(headerReject()!);
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: /^(confirm|reject)$/i });
    expect(confirm.className).toMatch(/bg-destructive/);
  });

  it('an application with no product rows does not say "0 of 0 lines done"', async () => {
    state.data = app({ lines: [] });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByText(/0 of 0/)).toBeNull();
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
    // RejectionReasonBanner prints " - <reason>" after its label.
    expect(await screen.findByText(/Supplier cannot make it/)).toBeInTheDocument();
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

  it('Approved shows no "Approved by X on D." banner (owner hand test 9 Nov: the pill says it)', async () => {
    state.data = app({ decided_by_name: 'Approver One', decided_at: '2026-11-02T01:00:00' });
    render(<Page />);
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.queryByText(/Approved by Approver One on /)).toBeNull();
  });
});

describe('the shared PurchasingResponseDialog on the NPA (owner 8 Nov 15:10)', () => {
  const replies = () => state.calls.filter((c) => c.method === 'POST' && /purchasing-response\/reply$/.test(c.url));
  const respBox = (d: HTMLElement) => within(d).getByRole('textbox', { name: /purchasing response/i });
  const fill = (d: HTMLElement, v = 'We can supply it') => fireEvent.change(respBox(d), { target: { value: v } });

  it('opens the same shared component, with the Purchasing response textarea before every NPA field', async () => {
    render(<Page />);
    const dialog = await openDialog();
    expect(screen.getByTestId('purchasing-response-dialog')).toBe(dialog.closest('[data-testid="purchasing-response-dialog"]') ?? dialog);
    expect(within(dialog).getByText('Edit purchasing response')).toBeInTheDocument();
    const box = respBox(dialog);
    const first = within(dialog).getAllByRole('textbox')[0];
    expect(first).toBe(box);
    const radio = within(dialog).getByRole('radio', { name: /link an existing product code/i });
    expect(Boolean(box.compareDocumentPosition(radio) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
    const lead = within(dialog).getByRole('textbox', { name: /lead ?time/i });
    expect(Boolean(box.compareDocumentPosition(lead) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
  });

  it('starts from the saved purchasing response', async () => {
    state.data = app({ purchasing_response: 'Earlier answer' });
    render(<Page />);
    const dialog = await openDialog();
    expect((respBox(dialog) as HTMLTextAreaElement).value).toBe('Earlier answer');
  });

  it('Save only is disabled while the response is blank and enabled once there is text', async () => {
    render(<Page />);
    const dialog = await openDialog();
    const save = within(dialog).getByRole('button', { name: /^save only$/i });
    expect(save).toBeDisabled();
    fill(dialog, '   ');
    expect(save).toBeDisabled();
    fill(dialog);
    expect(save).toBeEnabled();
  });

  it('Save only sends PUT purchasing-response with purchasing_response plus the other keys, and no reply', async () => {
    render(<Page />);
    const dialog = await openDialog();
    fill(dialog, 'We can supply it');
    fireEvent.click(within(dialog).getByRole('radio', { name: /^new product code$/i }));
    fireEvent.change(await within(dialog).findByRole('textbox', { name: /new product code/i }), { target: { value: 'XY-NEW-1' } });
    fireEvent.change(within(dialog).getByRole('textbox', { name: /lead ?time/i }), { target: { value: '3 weeks' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^save only$/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toMatchObject({
      purchasing_response: 'We can supply it',
      outcome: 'new',
      new_code: 'XY-NEW-1',
      lead_time: '3 weeks',
    });
    expect(replies()).toHaveLength(0);
  });

  it('Update & Reply is absent while detail.can_reply is false', async () => {
    state.data = app({ can_reply: false });
    render(<Page />);
    const dialog = await openDialog();
    expect(within(dialog).queryByRole('button', { name: /update & reply/i })).toBeNull();
    expect(within(dialog).getByRole('button', { name: /^save only$/i })).toBeInTheDocument();
  });

  it('Update & Reply is shown when detail.can_reply is true, disabled while the response is blank', async () => {
    state.data = app({ can_reply: true });
    render(<Page />);
    const dialog = await openDialog();
    const reply = within(dialog).getByRole('button', { name: /^update & reply$/i });
    expect(reply).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: /^save only$/i })).toBeDisabled();
    fill(dialog);
    expect(reply).toBeEnabled();
  });

  it('Update & Reply POSTs purchasing-response/reply with the same body as Save only', async () => {
    state.data = app({ can_reply: true });
    render(<Page />);
    const dialog = await openDialog();
    fill(dialog, 'We can supply it');
    fireEvent.change(within(dialog).getByRole('textbox', { name: /lead ?time/i }), { target: { value: '3 weeks' } });
    fireEvent.change(within(dialog).getByLabelText('Cost (MYR)'), { target: { value: '12.50' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^update & reply$/i }));
    await waitFor(() => expect(replies()).toHaveLength(1));
    expect(replies()[0].url).toContain('/api/v1/procurement/new-product-applications/a-1/purchasing-response/reply');
    expect(replies()[0].body).toMatchObject({ purchasing_response: 'We can supply it', lead_time: '3 weeks' });
    expect(Number((replies()[0].body as Record<string, unknown>).cost_price)).toBe(12.5);
    expect(puts()).toHaveLength(0);
  });

  it('the read-only detail shows the saved PURCHASING RESPONSE text', async () => {
    state.data = app({ purchasing_response: 'We can supply it in 3 weeks' });
    render(<Page />);
    expect(await screen.findByText('We can supply it in 3 weeks')).toBeInTheDocument();
    expect(document.body.textContent ?? '').toContain('PURCHASING RESPONSE');
  });
});
