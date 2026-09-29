/**
 * Fix round 5 (owner, 29 Sep, on the portal landing as the salesperson): "customer asks
 * should be own tab like price tag request, and can be controlled per contact".
 *
 * Customer asks is one kind in the landing's selector, offered only when the server's
 * `visible_form_types` carries it (the per-contact switch, and a linked sales agent - both
 * resolved server-side), with its open count as the badge. No separate card on the landing.
 * Mocking pattern mirrors `PortalLanding.salesOpportunity.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const push = vi.fn();
const replace = vi.fn();
const router = { push, replace };
let searchParams = new URLSearchParams('');
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
  usePathname: () => '/portal/c/ah-lim',
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMeWithGrace: vi.fn(),
    fetchSubmissions: vi.fn(),
    fetchSubmission: vi.fn(),
    portalLogout: vi.fn(),
    readPortalToken: vi.fn(() => 'tok-123'),
  };
});

vi.mock('../lib/price-tag-request-service', () => ({
  listRequestsAsSummaries: vi.fn(),
}));

const listCustomerAsks = vi.fn();
const getCustomerAsksTodo = vi.fn();
vi.mock('../lib/customer-asks-service', async () => {
  const actual = await vi.importActual<typeof import('../lib/customer-asks-service')>(
    '../lib/customer-asks-service',
  );
  return {
    ...actual,
    listCustomerAsks: (...a: unknown[]) => listCustomerAsks(...a),
    getCustomerAsksTodo: (...a: unknown[]) => getCustomerAsksTodo(...a),
  };
});

import { fetchMeWithGrace, fetchSubmissions } from '../lib/portal-client';
import { listRequestsAsSummaries } from '../lib/price-tag-request-service';
import { PortalLanding } from './PortalLanding';
import { LANDING_KINDS, portalFormKindLabel } from '@/lib/portal-form-kinds';

const ME = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'Agent Lim',
  phone_number: '60123456789',
  expires_at: '2026-10-01T00:00:00Z',
  portal_slug: 'ah-lim',
};

const ASK = {
  id: 'ask-1',
  customer_name: 'Hock Lee Trading',
  contact_name: 'Ah Seng',
  product_code: 'SRT5674',
  product_name: 'Wiper Blade 24in',
  quantity: 150,
  branch: 'no_incoming',
  answer_summary: 'SRT5674 x 150: no stock and no incoming at the moment, please refer to your salesman.',
  notified_agent: true,
  notify_skip_reason: null,
  state: 'open',
  note: null,
  source: 'live',
  created_at: '2026-09-24T07:05:00',
  updated_at: null,
};

function mockContact(visible: string[]) {
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue({
    ...ME,
    visible_form_types: visible,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams('');
  window.localStorage.clear();
  (fetchSubmissions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listRequestsAsSummaries as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  getCustomerAsksTodo.mockResolvedValue({
    today_start: '2026-09-28T16:00:00Z',
    open: [ASK],
    done_today: [],
    truncated: false,
  });
  listCustomerAsks.mockImplementation((p: { state?: string }) =>
    Promise.resolve(
      p.state === 'open'
        ? { data: [ASK], pagination: { total: 4, page: 1, limit: 1 } }
        : { data: [ASK], pagination: { total: 1, page: 1, limit: 20 } },
    ),
  );
});

describe('portal form kinds - Customer asks is one more landing kind', () => {
  it('is in LANDING_KINDS after Sales Opportunity, labelled Customer asks', () => {
    expect(LANDING_KINDS.slice(-2)).toEqual(['sales_opportunity', 'customer_asks']);
    // The CRM contact page's Portal forms row reads the same label.
    expect(portalFormKindLabel('customer_asks')).toBe('Customer asks');
  });
});

describe('PortalLanding - Customer asks is one kind in the selector (fix round 5)', () => {
  it('offers Customer asks beside Price Tag Request, badged with the open count', async () => {
    mockContact(['price_tag_request', 'customer_asks']);
    render(<PortalLanding slug="ah-lim" />);
    const trigger = await screen.findByRole('combobox');
    await waitFor(() =>
      expect(listCustomerAsks).toHaveBeenCalledWith(expect.objectContaining({ state: 'open', limit: 1 })),
    );
    trigger.click();
    const option = await screen.findByText('Customer asks');
    expect(option.parentElement?.textContent).toContain('4');
  });

  it('has no separate Customer asks card or link above the search box any more', async () => {
    mockContact(['price_tag_request', 'customer_asks']);
    render(<PortalLanding slug="ah-lim" />);
    await screen.findByRole('combobox');
    await waitFor(() => expect(listCustomerAsks).toHaveBeenCalled());
    expect(screen.queryByRole('link', { name: /customer asks/i })).toBeNull();
  });

  it('is not offered, and nothing is fetched, when the switch is off for this contact', async () => {
    mockContact(['price_tag_request']);
    render(<PortalLanding slug="ah-lim" />);
    const trigger = await screen.findByRole('combobox');
    await waitFor(() => expect(listRequestsAsSummaries).toHaveBeenCalled());
    trigger.click();
    expect((await screen.findAllByText('Price Tag Request')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Customer asks')).toBeNull();
    expect(listCustomerAsks).not.toHaveBeenCalled();
  });

  it('shows the to-do in the kind: the card with a Done button, ONE toolbar, no New button (AC-ST304, AC-ST305)', async () => {
    searchParams = new URLSearchParams('type=customer_asks');
    mockContact(['price_tag_request', 'customer_asks']);
    render(<PortalLanding slug="ah-lim" />);
    expect(await screen.findByText('Hock Lee Trading')).toBeInTheDocument();
    await waitFor(() => expect(getCustomerAsksTodo).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('radio', { name: 'Board view' }));
    expect(screen.getByText(/Asked:\s*SRT5674 x 150/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument();
    expect(screen.queryByTestId('ask-todo-counts')).toBeNull(); // the counts line is gone
    expect(screen.queryByLabelText('State for SRT5674')).toBeNull(); // the State select is gone
    expect(screen.queryByLabelText('Note for SRT5674')).toBeNull(); // the note lives in the opened card
    expect(screen.getAllByRole('button', { name: 'Filter' })).toHaveLength(1);
    expect(screen.getAllByLabelText('View mode')).toHaveLength(1);
    expect(screen.queryByRole('link', { name: /New Customer asks/ })).toBeNull();
    // The landing's own search box is the one search, not a second one inside the kind.
    expect(screen.getAllByRole('textbox', { name: /search/i })).toHaveLength(1);
  });

  it('narrows the to-do with the landing search box', async () => {
    searchParams = new URLSearchParams('type=customer_asks');
    mockContact(['customer_asks']);
    getCustomerAsksTodo.mockResolvedValue({
      today_start: '2026-09-28T16:00:00Z',
      open: [ASK, { ...ASK, id: 'ask-2', customer_name: 'Seng Heng Motor', product_code: 'SRT9999' }],
      done_today: [],
      truncated: false,
    });
    render(<PortalLanding slug="ah-lim" />);
    await screen.findByText('Hock Lee Trading');
    const box = screen.getByRole('textbox', { name: /search/i });
    fireEvent.change(box, { target: { value: 'seng heng' } });
    await waitFor(() => expect(screen.queryByText('Hock Lee Trading')).toBeNull());
    expect(screen.getByText('Seng Heng Motor')).toBeInTheDocument();
  });
});
