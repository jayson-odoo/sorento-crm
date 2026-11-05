/**
 * PRICETAG-COMBO-FORMAT fix round 1, R12: setting a template's price type from the list goes
 * through a hook (`useSetTemplatePriceType`) that invalidates the tag template queries and the
 * product / combo link queries, so a product page open elsewhere does not keep the old type.
 *
 * Written test-FIRST: the list calls the service directly and invalidates nothing. The hook's
 * module path is not named by the ruling, so the test watches the QueryClient it runs under.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/dealer-kit/tag-templates',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: vi.fn(() => 'x'),
  dismissDeferredToast: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('./TagTemplateDialog', () => ({ TagTemplateDialog: () => null }));
vi.mock('./AssignTemplateDialog', () => ({ AssignTemplateDialog: () => null }));
vi.mock('@/components/common/SearchableSelect', () => ({ SearchableSelect: () => null }));

const listTemplates = vi.fn();
const setTemplatePriceType = vi.fn();
vi.mock('../../services/tagTemplateService', () => ({
  listTemplates: (...a: unknown[]) => listTemplates(...a),
  setTemplatePriceType: (...a: unknown[]) => setTemplatePriceType(...a),
  createTemplate: vi.fn(),
}));

import { TagTemplatesList } from './TagTemplatesList';

const row = {
  id: 'b',
  name: 'Bathroom Furniture SP',
  family: 'ala_carte',
  doc: { layers: [], width_mm: 85, height_mm: 58 },
  print_size: { width_mm: 85, height_mm: 58 },
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  published_version_id: null,
  published_version_no: null,
  price_type: null,
};

beforeEach(() => {
  listTemplates.mockReset().mockResolvedValue([row]);
  setTemplatePriceType.mockReset().mockResolvedValue({ ...row, price_type: 'selling' });
});

describe('price type set from the list invalidates the caches (R12)', () => {
  it('R12: saves through the service and invalidates tag-templates, product and combo links', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    render(
      <QueryClientProvider client={client}>
        <TagTemplatesList />
      </QueryClientProvider>,
    );
    await screen.findByText('Bathroom Furniture SP');

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Change price type of Bathroom Furniture SP' }));
    await user.click(await screen.findByRole('menuitem', { name: 'SP' }));

    await waitFor(() => expect(setTemplatePriceType).toHaveBeenCalledWith('b', 'selling'));
    await waitFor(() => {
      const keys = invalidate.mock.calls.map((call) => JSON.stringify((call[0] as { queryKey?: unknown })?.queryKey));
      expect(keys).toContain(JSON.stringify(['tag-templates']));
      expect(keys).toContain(JSON.stringify(['product-tag-templates']));
      expect(keys).toContain(JSON.stringify(['combo-tag-templates']));
    });
  });
});
