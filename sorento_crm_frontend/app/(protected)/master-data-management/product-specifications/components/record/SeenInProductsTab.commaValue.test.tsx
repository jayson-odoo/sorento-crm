/**
 * FILTER-MULTISELECT PR4 review round: a spec value that itself contains a comma (a multi-value key reads back
 * like `["Gold", "Matt Black"]`) must reach the data hook intact, never split into pieces, and the filter's
 * trigger must show it whole. Uses the REAL SearchableMultiSelect. Hook mocked, as in the sibling tests.
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

const COMMA = '["Gold", "Matt Black"]';
const DATA = {
  spec_key: 'finish', label: 'Finish', total: 2,
  by_value: [{ value: COMMA, count: 2 }, { value: 'Chrome', count: 1 }],
  by_class: [{ class: 'ZZT Sink', count: 3 }],
  by_source: [{ source: 'derived', count: 3 }],
  products: [],
};

const lastParams = () => useQ.mock.calls[useQ.mock.calls.length - 1][1] as Record<string, unknown>;
const asList = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v == null || v === '' ? [] : [String(v)]);

async function pickByText(user: ReturnType<typeof userEvent.setup>, text: RegExp) {
  fireEvent.pointerDown(screen.getByRole('button', { name: /Filters/i }), { button: 0 });
  const trigger = await waitFor(() => {
    const el = document.querySelector('[data-slot="searchable-multi-select-trigger"]');
    if (!el) throw new Error('no multi trigger');
    return el as HTMLElement;
  });
  await user.click(trigger);
  const option = await waitFor(() => {
    const el = [...document.querySelectorAll('[role="option"]')].find((o) => text.test(o.textContent ?? ''));
    if (!el) throw new Error('option not offered');
    return el as HTMLElement;
  });
  await user.click(option);
  return trigger;
}

beforeEach(() => {
  useQ.mockReset();
  useQ.mockReturnValue({ data: DATA, isLoading: false, isFetching: false });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

describe('Seen in products - a value containing a comma', () => {
  it('reaches the data hook whole, as one value, not split on the comma', async () => {
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient()}><SeenInProductsTab specKey="finish" label="Finish" /></QueryClientProvider>);
    await pickByText(user, /Matt Black/);
    await waitFor(() => expect(asList(lastParams().value)).toEqual([COMMA]));
  });

  it('the trigger shows the value whole', async () => {
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient()}><SeenInProductsTab specKey="finish" label="Finish" /></QueryClientProvider>);
    await pickByText(user, /Matt Black/);
    await waitFor(() => {
      const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]') as HTMLElement;
      expect(trigger.textContent).toMatch(/Gold.*Matt Black/);
    });
  });

  it('a comma value and a plain value together reach the hook as two values', async () => {
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient()}><SeenInProductsTab specKey="finish" label="Finish" /></QueryClientProvider>);
    await pickByText(user, /Matt Black/);
    const option = await waitFor(() => {
      const el = [...document.querySelectorAll('[role="option"]')].find((o) => /Chrome/.test(o.textContent ?? ''));
      if (!el) throw new Error('Chrome not offered');
      return el as HTMLElement;
    });
    await user.click(option);
    await waitFor(() => expect(asList(lastParams().value).sort()).toEqual(['Chrome', COMMA].sort()));
  });
});
