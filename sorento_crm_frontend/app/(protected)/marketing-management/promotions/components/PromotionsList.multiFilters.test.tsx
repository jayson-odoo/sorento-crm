/**
 * FILTER-MULTISELECT PR3: the Promotions list's Access level and Attachment state filters take several
 * values (OR within a filter, AND across). They are URL-persisted (`user_type`, `attachment_state`), so a
 * comma-joined link and an older single-value link both read back. Active / Inactive stays single.
 * Harness mirrors PromotionsList.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/marketing-management/promotions',
  useSearchParams: () => new URLSearchParams(url.search),
}));
const getPromotions = vi.fn();
vi.mock('../services/promotionService', () => ({ getPromotions: (...a: unknown[]) => getPromotions(...a) }));
vi.mock('../hooks/usePromotions', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, useCompilePromotionsPdf: () => ({ mutate: vi.fn(), isPending: false }) };
});
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: new Set(['marketing']), isLoading: false }),
}));
vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({
    data: [{ code: 'dealer', name: 'ZZT Dealer' }, { code: 'end_user', name: 'ZZT End user' }, { code: 'office', name: 'ZZT Office' }],
  }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import PromotionsList from './PromotionsList';

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastArgs = () => {
  const calls = getPromotions.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
  url.search = '';
  getPromotions.mockReset();
  getPromotions.mockResolvedValue({ data: [], pagination: { total: 0 } });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromotionsList />
    </QueryClientProvider>,
  );
}
async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderIt();
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Promotions - multi Access level and Attachment state filters', () => {
  it('are two multi controls, Access level then Attachment state', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two access levels reach the service, never with the All placeholder', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [levels] = await screen.findAllByRole('listbox');
    await user.selectOptions(levels, ['dealer', 'end_user']);
    await waitFor(() => expect(asList(lastArgs().user_type)).toEqual(['dealer', 'end_user']));
    expect(asList(lastArgs().user_type)).not.toContain('all');
  });

  it('two attachment states reach the service', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[1], ['unlinked', 'linked_to_trashed']);
    await waitFor(() => expect(asList(lastArgs().attachment_state)).toEqual(['unlinked', 'linked_to_trashed']));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[0], ['dealer', 'office']);
    await user.selectOptions(boxes[1], ['unlinked']);
    await waitFor(() => {
      expect(asList(lastArgs().user_type)).toEqual(['dealer', 'office']);
      expect(asList(lastArgs().attachment_state)).toEqual(['unlinked']);
    });
  });

  it('a comma-joined link reads back into both filters', async () => {
    url.search = 'user_type=dealer%2Cend_user&attachment_state=unlinked%2Clinked_to_trashed';
    renderIt();
    await waitFor(() => {
      expect(asList(lastArgs().user_type)).toEqual(['dealer', 'end_user']);
      expect(asList(lastArgs().attachment_state)).toEqual(['unlinked', 'linked_to_trashed']);
    });
  });

  it('an older link with one access level and one state reads back as one-value filters (guard)', async () => {
    url.search = 'user_type=dealer&attachment_state=unlinked';
    renderIt();
    await waitFor(() => {
      expect(asList(lastArgs().user_type)).toEqual(['dealer']);
      expect(asList(lastArgs().attachment_state)).toEqual(['unlinked']);
    });
  });
});
