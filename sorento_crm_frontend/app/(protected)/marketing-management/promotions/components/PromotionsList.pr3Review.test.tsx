/**
 * FILTER-MULTISELECT PR3 review: the Promotions export and advanced-filter payloads carry the same quick
 * filters the list does, so an export is never wider than the list: Attachment state (comma-joined) and
 * the access levels. The toolbar is stood in for so its `getPayload` callbacks can be read.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
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
const toolbar = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));
vi.mock('@/components/ui/data-grid-list-toolbar', () => ({
  DataGridListToolbar: (props: Record<string, unknown>) => {
    toolbar.props = props;
    return null;
  },
}));

import PromotionsList from './PromotionsList';

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
const lastArgs = () => {
  const calls = getPromotions.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
type Cfg = { getPayload: () => Record<string, unknown> };

describe('Promotions - the export and filter payloads match the list', () => {
  it('the export payload carries Attachment state and the access levels', async () => {
    url.search = 'user_type=dealer%2Cend_user&attachment_state=unlinked%2Clinked_to_trashed';
    renderIt();
    await waitFor(() => expect(getPromotions).toHaveBeenCalled());
    await waitFor(() => expect(lastArgs().attachment_state).toBeTruthy());
    const payload = (toolbar.props!.exportConfig as Cfg).getPayload();
    expect(payload.promotion_attachment_state).toBe('unlinked,linked_to_trashed');
    expect(String(payload.promotion_access_level)).toBe('dealer,end_user');
  });

  it('the advanced-filter payload carries Attachment state too', async () => {
    url.search = 'attachment_state=unlinked';
    renderIt();
    await waitFor(() => expect(lastArgs().attachment_state).toBeTruthy());
    const payload = (toolbar.props!.filters as Cfg).getPayload();
    expect(payload.promotion_attachment_state).toBe('unlinked');
  });

  it('with no Attachment state the key is absent (guard)', async () => {
    renderIt();
    await waitFor(() => expect(getPromotions).toHaveBeenCalled());
    const payload = (toolbar.props!.exportConfig as Cfg).getPayload();
    expect(payload.promotion_attachment_state).toBeUndefined();
  });
});
