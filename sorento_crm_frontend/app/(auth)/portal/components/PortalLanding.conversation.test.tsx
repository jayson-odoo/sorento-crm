/**
 * Lane SALES-CONVO (owner 30 Sep): Conversation is one kind in the landing's selector, offered
 * only when the server's `visible_form_types` carries it (the per-contact switch and a linked
 * sales agent, both resolved server-side), badged with the row count. Its body is
 * `ConversationList`: no New button, the landing's own toolbar and search (AC-CV1, AC-CV10).
 * Mocking pattern mirrors `PortalLanding.customerAsks.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function render(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return rtlRender(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
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
  const original =
    await importOriginal<typeof import('../lib/portal-client')>();
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

const listConversations = vi.fn();
vi.mock('../lib/conversations-service', async () => {
  const actual = await vi.importActual<
    typeof import('../lib/conversations-service')
  >('../lib/conversations-service');
  return {
    ...actual,
    listConversations: (...a: unknown[]) => listConversations(...a),
  };
});

import { fetchMeWithGrace, fetchSubmissions } from '../lib/portal-client';
import { listRequestsAsSummaries } from '../lib/price-tag-request-service';
import { PortalLanding } from './PortalLanding';
import {
  ADDITIONAL_LANDING_KINDS,
  LANDING_KINDS,
  portalFormKindLabel,
} from '@/lib/portal-form-kinds';

const ME = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'Agent Lim',
  phone_number: '60123456789',
  expires_at: '2026-10-01T00:00:00Z',
  portal_slug: 'ah-lim',
};

const ROW = {
  contact_id: 'c-chin',
  customer_name: 'Chin Chun Hardware',
  customer_code: 'CCH',
  contact_name: 'Mr. Chin',
  contact_phone: '+60123456789',
  last_message_at: '2026-09-30T01:14:00',
  last_message_snippet: 'Boss, the 60x60 grey tile got stock or not?',
  last_message_direction: 'incoming' as const,
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
  listConversations.mockImplementation((p: { limit?: number }) =>
    Promise.resolve(
      p.limit === 1
        ? { data: [ROW], pagination: { total: 5, page: 1, limit: 1 } }
        : { data: [ROW], pagination: { total: 1, page: 1, limit: 200 } },
    ),
  );
});

describe('portal form kinds - Conversation is one more landing kind', () => {
  it('is the last kind in LANDING_KINDS, after Customer asks, labelled Conversation', () => {
    expect(LANDING_KINDS.slice(-2)).toEqual(['customer_asks', 'conversation']);
    // The CRM contact page's Portal forms row and the market segment admin read the same label.
    expect(portalFormKindLabel('conversation')).toBe('Conversation');
    expect(ADDITIONAL_LANDING_KINDS).toContain('conversation');
  });
});

describe('PortalLanding - Conversation is one kind in the selector', () => {
  it('offers Conversation beside the other kinds, badged with the row count (AC-CV1)', async () => {
    mockContact(['price_tag_request', 'customer_asks', 'conversation']);
    render(<PortalLanding slug="ah-lim" />);
    const trigger = await screen.findByRole('combobox');
    await waitFor(() =>
      expect(listConversations).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, limit: 1 }),
      ),
    );
    trigger.click();
    const option = await screen.findByText('Conversation');
    expect(option.parentElement?.textContent).toContain('5');
  });

  it('is not offered, and nothing is fetched, when the contact was not granted it (AC-CV2/AC-CV3)', async () => {
    mockContact(['price_tag_request']);
    render(<PortalLanding slug="ah-lim" />);
    const trigger = await screen.findByRole('combobox');
    await waitFor(() => expect(listRequestsAsSummaries).toHaveBeenCalled());
    trigger.click();
    expect(
      (await screen.findAllByText('Price Tag Request')).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText('Conversation')).toBeNull();
    expect(listConversations).not.toHaveBeenCalled();
  });

  it('shows the list in the kind: the card, ONE toolbar, no New button, the landing search only (AC-CV10)', async () => {
    searchParams = new URLSearchParams('type=conversation');
    mockContact(['price_tag_request', 'conversation']);
    render(<PortalLanding slug="ah-lim" />);
    expect(await screen.findByText('Chin Chun Hardware')).toBeInTheDocument();
    expect(
      screen.getByText('Boss, the 60x60 grey tile got stock or not?'),
    ).toBeInTheDocument();
    expect(screen.getByText('Customer wrote last')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Filter' })).toHaveLength(1);
    expect(screen.getAllByLabelText('View mode')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Sort' })).toHaveTextContent(
      'Last message',
    );
    expect(screen.queryByRole('link', { name: /New Conversation/ })).toBeNull();
    expect(screen.getAllByRole('textbox', { name: /search/i })).toHaveLength(1);
  });

  it('passes the landing search box to the list read (AC-CV9)', async () => {
    searchParams = new URLSearchParams('type=conversation');
    mockContact(['conversation']);
    render(<PortalLanding slug="ah-lim" />);
    await screen.findByText('Chin Chun Hardware');
    const box = screen.getByRole('textbox', { name: /search/i });
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.change(box, { target: { value: 'chin' } });
    await waitFor(() =>
      expect(listConversations).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'chin', limit: 200 }),
      ),
    );
  });
});
