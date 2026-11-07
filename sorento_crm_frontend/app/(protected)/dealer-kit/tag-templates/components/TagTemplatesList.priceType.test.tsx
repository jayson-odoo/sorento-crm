/**
 * PRICETAG-COMBO-FORMAT AC-29: the template list shows a "Set price type" badge on a template with
 * no price type, and filters by price type including "Not set" (the request carries
 * `price_type=unset`).
 *
 * Written test-FIRST. Contract read literally: filter labelled "Price type" with options LP, SP,
 * LP & SP, Not set. The filter is located by its aria-label / placeholder through a native-select
 * stand-in for `SearchableSelect`; the request is asserted on the `listTemplates` call arguments
 * (whichever form the implementation passes them in, the value `unset` must be in them).
 * Mocks follow `TagTemplatesList.test.tsx`.
 */
import { render, screen } from '@testing-library/react';
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

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
  }) => (
    <select
      aria-label={props['aria-label'] ?? props.placeholder ?? ''}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const listTemplates = vi.fn();
vi.mock('../../services/tagTemplateService', () => ({
  listTemplates: (...a: unknown[]) => listTemplates(...a),
  createTemplate: vi.fn(),
}));

import { TagTemplatesList } from './TagTemplatesList';

const tpl = (id: string, name: string, price_type: string | null) => ({
  id,
  name,
  family: 'ala_carte',
  doc: { layers: [], width_mm: 85, height_mm: 58 },
  print_size: { width_mm: 85, height_mm: 58 },
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  published_version_id: null,
  published_version_no: null,
  price_type,
});

function draw() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TagTemplatesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listTemplates.mockReset();
  listTemplates.mockResolvedValue([
    tpl('a', 'Small Price Tag LP', 'list'),
    tpl('b', 'Bathroom Furniture SP', null),
  ]);
});

describe('TagTemplatesList price type (AC-29)', () => {
  it('AC-29: a template with no price type carries the "Set price type" badge; a typed one does not', async () => {
    draw();
    await screen.findByText('Bathroom Furniture SP');
    expect(screen.getAllByText('Set price type')).toHaveLength(1);
    const badge = screen.getByText('Set price type');
    expect(badge.closest('tr')).toHaveTextContent('Bathroom Furniture SP');
    expect(screen.getByText('Small Price Tag LP').closest('tr')).not.toHaveTextContent('Set price type');
  });

  // The Price type filter moved into the standard toolbar's Filters menu and went multi-select
  // (TAG-TEMPLATE-DUPLICATE item 5): `TagTemplatesList.toolbar.test.tsx` owns it now, the
  // "Not set" -> `price_type=unset` request included.
});
