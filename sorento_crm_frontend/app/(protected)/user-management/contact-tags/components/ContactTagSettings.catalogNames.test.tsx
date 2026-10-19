/**
 * TAG-VIEW-BUG: the tag view names each id from the settings catalog, which arrives after the
 * first render. A list of ids must end up showing each name once (no leftover "Removed" badges
 * from the render before the names arrived), never say "Removed" while the names are loading,
 * and say why when they cannot load.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render as rtlRender, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-tags/t1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('../services/contactTagService', () => ({
  updateContactTag: vi.fn(),
  getContactTag: vi.fn(),
  getContactTags: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));

import ContactTagSettings from './ContactTagSettings';

const TYPES = ['a1', 'a2', 'a3', 'a4', 'a5', 'a6'];
const NAMES = ['Type A', 'Type B', 'Type C', 'Type D', 'Type E', 'Type F'];

const catalog = (attachment_types: { value: string; label: string }[]) => ({
  access_types: [],
  brands: [],
  market_segments: [],
  attachment_types,
  field_reveals: [],
  portal_forms: [],
  spec_keys: [],
});

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

function render(settings: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  rtlRender(
    <QueryClientProvider client={client}>
      <ContactTagSettings
        tag={{ id: 't1', name: 'Dealer', description: null, is_active: true, sort_order: 0, settings,
          contact_count: 0, created_at: '', updated_at: '' } as never}
        editing={false}
        onDone={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

const group = (title: string) =>
  screen
    .getAllByTestId('settings-group')
    .find((g) => within(g).getByTestId('settings-group-title').textContent === title)!;

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  apiFetch.mockReset();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => consoleError.mockRestore());

const duplicateKeyWarnings = () =>
  consoleError.mock.calls.filter((c: unknown[]) => String(c[0]).includes('same key'));

describe('ContactTagSettings view: names from the catalog', () => {
  it('a list of six ids shows each name once after the names load, no leftover Removed', async () => {
    apiFetch.mockResolvedValue(ok(catalog(TYPES.map((value, i) => ({ value, label: NAMES[i] })))));
    render({ attachment_types: TYPES });

    expect(await within(group('Attachment types')).findByText('Type F')).toBeInTheDocument();
    const body = group('Attachment types');
    expect(within(body).queryAllByText('Removed')).toHaveLength(0);
    for (const name of NAMES) expect(within(body).getAllByText(name)).toHaveLength(1);
    expect(duplicateKeyWarnings()).toHaveLength(0);
  });

  it('while the names load, a set list group never says Removed', () => {
    apiFetch.mockReturnValue(new Promise(() => {}));
    render({ attachment_types: TYPES });

    expect(within(group('Attachment types')).queryAllByText('Removed')).toHaveLength(0);
  });

  // Every group that names ids from the catalog, each holding two ids it cannot name yet.
  const NAMED: [string, Record<string, unknown>][] = [
    ['Access types', { access_types: ['x1', 'x2'] }],
    ['Brands', { brands: ['b1', 'b2'] }],
    ['Companies', { companies: ['c1', 'c2'] }],
    ['Market segments', { market_segments: ['m1', 'm2'] }],
    ['Field reveals', { field_reveals: { 'r.one': true, 'r.two': false } }],
    ['Chatbot agents', { agents: { g1: true, g2: false } }],
    ['Agent field access', {
      agent_fields: [{ agent_code: 'ag', resource: 'res', field_key: 'f1', is_allowed: true }],
    }],
    ['Attachment types', { attachment_types: ['a1', 'a2'] }],
    ['Stock visibility', { stock_visibility: { warehouse_ids: ['w1', 'w2'] } }],
    ['Spec visibility', { spec_visibility: { spec_keys: ['s1', 's2'] } }],
  ];
  it.each(NAMED)('while the names load, %s never says Removed', (title, settings) => {
    apiFetch.mockReturnValue(new Promise(() => {}));
    render(settings);

    expect(within(group(title)).queryAllByText(/Removed/)).toHaveLength(0);
  });

  it('when the names cannot load, the group shows why instead of Removed', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({ 'content-type': 'text/plain' }),
      text: async () => 'Catalog is down',
    });
    render({ attachment_types: TYPES, outbound_enabled: true });

    expect(await within(group('Attachment types')).findByText('Catalog is down')).toBeInTheDocument();
    expect(within(group('Attachment types')).queryAllByText('Removed')).toHaveLength(0);
    // The rest of the card still renders.
    expect(within(group('Messaging (outbound)')).getByText('On')).toBeInTheDocument();
  });

  it('two ids the catalog no longer holds read Removed twice, without a duplicate-key warning', async () => {
    apiFetch.mockResolvedValue(ok(catalog([{ value: 'a1', label: 'Type A' }])));
    render({ attachment_types: ['gone-1', 'gone-2', 'a1'] });

    expect(await within(group('Attachment types')).findByText('Type A')).toBeInTheDocument();
    expect(within(group('Attachment types')).getAllByText('Removed')).toHaveLength(2);
    expect(duplicateKeyWarnings()).toHaveLength(0);
  });
});
