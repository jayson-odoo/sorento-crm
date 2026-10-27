/**
 * FILTER-MULTISELECT PR4: a class label containing a comma ("Sink, Undermount") picked in the "Seen in products"
 * Class filter reaches the data hook intact (an array of exact labels, never split). REAL SearchableMultiSelect.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/product-specifications/finish',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../hooks/useSpecRegistryMutations', () => ({
  useSpecRegistryMutations: () => ({ reread: { mutate: vi.fn(), isPending: false } }),
}));
const useQ = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/useSpecKeyProductsQuery', () => ({
  useSpecKeyProductsQuery: (specKey: string, params: unknown) => useQ(specKey, params),
}));

import { SeenInProductsTab } from './SeenInProductsTab';

const CLASS = 'Sink, Undermount';
const DATA = {
  spec_key: 'finish', label: 'Finish', total: 2,
  by_value: [{ value: 'Chrome', count: 2 }],
  by_class: [{ class: CLASS, count: 2 }, { class: 'Tap', count: 1 }],
  by_source: [{ source: 'derived', count: 3 }],
  products: [],
};

const lastParams = () => useQ.mock.calls[useQ.mock.calls.length - 1][1] as Record<string, unknown>;
const asList = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v == null || v === '' ? [] : [String(v)]);

async function pickClass(user: ReturnType<typeof userEvent.setup>, text: RegExp) {
  if (!document.querySelector('[data-slot="searchable-multi-select-trigger"]')) {
    fireEvent.pointerDown(screen.getByRole('button', { name: /Filters/i }), { button: 0 });
  }
  const triggers = await waitFor(() => {
    const els = document.querySelectorAll('[data-slot="searchable-multi-select-trigger"]');
    if (els.length < 2) throw new Error('no Class trigger');
    return els;
  });
  // The popover stays open after a pick; clicking the trigger again would close it.
  if (!document.querySelector('[role="option"]')) await user.click(triggers[1] as HTMLElement);
  const option = await waitFor(() => {
    const el = [...document.querySelectorAll('[role="option"]')].find((o) => text.test(o.textContent ?? ''));
    if (!el) throw new Error('option not offered');
    return el as HTMLElement;
  });
  await user.click(option);
}

beforeEach(() => {
  useQ.mockReset();
  useQ.mockReturnValue({ data: DATA, isLoading: false, isFetching: false });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

function renderTab() {
  render(<QueryClientProvider client={new QueryClient()}><SeenInProductsTab specKey="finish" label="Finish" /></QueryClientProvider>);
}

describe('Seen in products - a class label containing a comma', () => {
  it('reaches the data hook whole, as one label', async () => {
    const user = userEvent.setup();
    renderTab();
    await pickClass(user, /Undermount/);
    await waitFor(() => expect(asList(lastParams().classLabel)).toEqual([CLASS]));
  });

  it('together with a plain label it reaches the hook as two labels', async () => {
    const user = userEvent.setup();
    renderTab();
    await pickClass(user, /Undermount/);
    await pickClass(user, /^Tap/);
    await waitFor(() => expect(asList(lastParams().classLabel).sort()).toEqual([CLASS, 'Tap'].sort()));
  });
});
