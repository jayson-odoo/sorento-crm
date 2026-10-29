/**
 * LOOKUP-EMBED-CENTRAL slice 5, AC-LEC-24: an alias-set option's value is picked from the master records (a
 * SearchableSelect over GET /lookup-sets/{id}/alias-targets) and an option whose code no longer exists shows an
 * Orphaned badge. Mocked at `@/lib/api` so only the route contract is assumed. Assumed prop (the coder adds it):
 * `OptionFormDialog` gets `setKey` (the set's set_key).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

Element.prototype.scrollIntoView = vi.fn();
(Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import OptionFormDialog from '../components/OptionFormDialog';
import OptionsSection from '../components/OptionsSection';

const SET_ID = '7d2c4e3a-3333-4444-8555-b66677778888';
const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });

function wrap(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>,
  );
}

const option = (value: string, orphaned: boolean) => ({
  id: crypto.randomUUID(), set_id: SET_ID, value, label: value, sort_order: 0, is_active: true, description: null,
  keywords: [], created_at: '2026-10-29T00:00:00Z', updated_at: null, orphaned,
});

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/alias-targets')) return json([{ value: 'ZZ Photo', label: 'ZZ Photo' }, { value: 'ZZ Drawing', label: 'ZZ Drawing' }]);
    if (String(url).includes('/options')) {
      return json({ data: [option('ZZ Photo', false), option('ZZ Deleted Type', true)], pagination: { page: 1, limit: 100, total: 2, total_pages: 1 }, empty: false });
    }
    return json({});
  });
});
afterEach(() => cleanup());

describe('option dialog of an alias set', () => {
  it('offers the alias targets in a select instead of a free value box', async () => {
    wrap(<OptionFormDialog open onOpenChange={() => {}} setId={SET_ID} setKey="attachment_type_alias" editing={null} />);
    const select = await screen.findByRole('combobox');
    fireEvent.click(select);
    expect(await screen.findByText('ZZ Drawing')).toBeInTheDocument();
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes(`/lookup-sets/${SET_ID}/alias-targets`))).toBe(true);
  });

  it('keeps a plain value box and asks for no targets on an ordinary set', async () => {
    wrap(<OptionFormDialog open onOpenChange={() => {}} setId={SET_ID} setKey="priority" editing={null} />);
    expect(await screen.findByText('Add option')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('combobox')).toBeNull());
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('/alias-targets'))).toBe(false);
  });
});

describe('options list', () => {
  it('shows an Orphaned badge on an option whose code no longer exists, and only there', async () => {
    wrap(<OptionsSection setId={SET_ID} />);
    expect((await screen.findAllByText('ZZ Deleted Type')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/orphaned/i)).toHaveLength(1);
  });
});
