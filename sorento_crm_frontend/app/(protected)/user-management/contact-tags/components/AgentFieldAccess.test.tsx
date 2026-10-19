/**
 * AGENT-FIELD-MULTI (20 Oct), UAC AC-1..AC-7: the tag's "Agent field access" group is two
 * multi-selects, Allow and Deny, with readable field names and a remove x per chip; a field
 * stored twice shows and saves once. Plan: documentation/plans/contacts/PLAN-agent-field-multi-20oct.md.
 * Assumed: the two lists sit in `agent-fields-allow` / `agent-fields-deny` (view and edit), each
 * holding a SearchableMultiSelect in edit; the catalog's agent_fields options carry `label`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-tags/t1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
}));

const AGENT = 'incoming_stock_enquiries';
const field = (field_key: string, label: string) => ({ agent_code: AGENT, resource: 'incoming_stock', field_key, label });
const CATALOG = {
  access_types: [], brands: [], market_segments: [], attachment_types: [], field_reveals: [],
  portal_forms: [], spec_keys: [],
  agents: [{ value: 'a1', label: 'Incoming Stock Enquiries', code: AGENT }],
  agent_fields: [
    field('estimated_arrival_date', 'ETA'),
    field('eta_delay_date', 'ETA delay'),
    field('informed_collection_date', 'Collection informed'),
    field('gatepass_date', 'Gatepass'),
  ],
};

vi.mock('../services/contactTagSettingsCatalogService', async (orig) => ({
  ...(await orig<object>()),
  getSettingsCatalog: () => Promise.resolve(CATALOG),
}));

const updateContactTag = vi.fn();
vi.mock('../services/contactTagService', () => ({
  updateContactTag: (...a: unknown[]) => updateContactTag(...a),
  getContactTag: vi.fn(),
  getContactTags: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));

import ContactTagSettings from './ContactTagSettings';

const entry = (field_key: string, is_allowed = true) => ({
  agent_code: AGENT, resource: 'incoming_stock', field_key, is_allowed,
});
// The owner's tag: ETA stored twice (the duplicate nobody could delete), plus one Deny.
const STORED = [
  entry('eta_delay_date'),
  entry('estimated_arrival_date'),
  entry('estimated_arrival_date'),
  entry('informed_collection_date', false),
];

const tag = (settings: Record<string, unknown>) => ({
  id: 't1', name: 'Dealer', description: null, is_active: true, sort_order: 0, settings,
  contact_count: 0, created_at: '', updated_at: '',
});

function render(settings: Record<string, unknown>, editing: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  rtlRender(
    <QueryClientProvider client={client}>
      <ContactTagSettings tag={tag(settings) as never} editing={editing} onDone={vi.fn()} />
    </QueryClientProvider>,
  );
}

const list = (which: 'allow' | 'deny') => screen.findByTestId(`agent-fields-${which}`);
const savedFields = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
  return (updateContactTag.mock.calls[0][1] as { settings: { agent_fields: unknown[] } }).settings.agent_fields;
};

beforeEach(() => {
  vi.clearAllMocks();
  updateContactTag.mockResolvedValue(tag({}));
});

describe('Agent field access, view', () => {
  it('shows Allow and Deny with readable names, each field once', async () => {
    render({ agent_fields: STORED }, false);
    const allow = await list('allow');
    expect(await within(allow).findAllByText('Incoming Stock Enquiries: ETA')).toHaveLength(1);
    expect(within(allow).getByText('Incoming Stock Enquiries: ETA delay')).toBeInTheDocument();
    expect(within(await list('deny')).getByText('Incoming Stock Enquiries: Collection informed')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/estimated_arrival_date|eta_delay_date|informed_collection_date/);
  });

  it('leaves out an empty list', async () => {
    render({ agent_fields: [entry('eta_delay_date')] }, false);
    await list('allow');
    expect(screen.queryByTestId('agent-fields-deny')).toBeNull();
  });
});

describe('Agent field access, edit', () => {
  it('renders the stored fields as chips in their list, the duplicate once', async () => {
    render({ agent_fields: STORED }, true);
    const allow = await list('allow');
    await waitFor(() =>
      expect(within(allow).getAllByRole('button', { name: 'Remove Incoming Stock Enquiries: ETA' })).toHaveLength(1),
    );
    expect(within(allow).getByRole('button', { name: 'Remove Incoming Stock Enquiries: ETA delay' })).toBeInTheDocument();
    expect(
      within(await list('deny')).getByRole('button', { name: 'Remove Incoming Stock Enquiries: Collection informed' }),
    ).toBeInTheDocument();
  });

  it('saving untouched collapses the duplicate to one entry', async () => {
    render({ agent_fields: STORED }, true);
    await list('allow');
    const sent = await savedFields();
    expect(sent).toHaveLength(3);
    expect(sent).toEqual(
      expect.arrayContaining([
        entry('estimated_arrival_date'),
        entry('eta_delay_date'),
        entry('informed_collection_date', false),
      ]),
    );
  });

  it('the chip x removes the field and Save sends it gone', async () => {
    render({ agent_fields: STORED }, true);
    const allow = await list('allow');
    const x = await within(allow).findByRole('button', { name: 'Remove Incoming Stock Enquiries: ETA' });
    fireEvent.pointerDown(x);
    const sent = await savedFields();
    expect(sent).toEqual(
      expect.arrayContaining([entry('eta_delay_date'), entry('informed_collection_date', false)]),
    );
    expect(sent).toHaveLength(2);
  });

  it('a field picked under Allow is not offered under Deny; picking one there saves it as denied', async () => {
    render({ agent_fields: STORED }, true);
    const deny = await list('deny');
    await within(await list('allow')).findByRole('button', { name: 'Remove Incoming Stock Enquiries: ETA' });
    fireEvent.click(deny.querySelector('[data-slot="searchable-multi-select-trigger"]')!);
    const gate = await screen.findByRole('option', { name: /Gatepass/ });
    expect(screen.queryByRole('option', { name: /^Incoming Stock Enquiries: ETA$/ })).toBeNull();
    expect(screen.queryByRole('option', { name: /ETA delay/ })).toBeNull();
    fireEvent.click(gate);
    const sent = await savedFields();
    expect(sent).toEqual(expect.arrayContaining([entry('gatepass_date', false)]));
    expect(sent).toHaveLength(4);
  });
});
