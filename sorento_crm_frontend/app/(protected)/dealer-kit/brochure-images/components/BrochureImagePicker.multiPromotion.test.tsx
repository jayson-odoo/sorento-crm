/**
 * FILTER-MULTISELECT PR3: the Brochure images picker's Promotion filter takes several promotions (OR
 * within the filter), comma-joined to the list service. Harness mirrors BrochureImagePicker.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../services/brochureImageService', () => ({
  BROCHURE_IMAGE_PAGE_SIZE: 25,
  PROMOTION_PAGE_SIZE: 50,
  listBrochureImages: vi.fn(),
  listBrochureImagePromotionOptions: vi.fn(),
  adoptSingleBrochureImages: vi.fn(),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productBrochureImageService', () => ({
  setBrochureImage: vi.fn(),
  clearBrochureImage: vi.fn(),
}));
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

import { listBrochureImages, listBrochureImagePromotionOptions } from '../../services/brochureImageService';
import { BrochureImagePicker } from './BrochureImagePicker';

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastArgs = () => {
  const calls = vi.mocked(listBrochureImages).mock.calls;
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
  vi.mocked(listBrochureImages).mockReset();
  vi.mocked(listBrochureImages).mockResolvedValue({
    items: [], total: 0, page: 1, limit: 25, pages: 1, summary: {},
  } as never);
  vi.mocked(listBrochureImagePromotionOptions).mockReset();
  vi.mocked(listBrochureImagePromotionOptions).mockResolvedValue({
    items: [{ value: 'promo-1', label: 'ZZT Flyer One' }, { value: 'promo-2', label: 'ZZT Flyer Two' }],
    total: 2,
  } as never);
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BrochureImagePicker />
    </QueryClientProvider>,
  );
}

describe('Brochure images - multi Promotion filter', () => {
  it('is a multi control', async () => {
    renderIt();
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two promotions go to the service comma-joined', async () => {
    const user = userEvent.setup();
    renderIt();
    const box = await screen.findByRole('listbox');
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(box, ['promo-1', 'promo-2']);
    await waitFor(() => expect(asList(lastArgs().promotionId)).toEqual(['promo-1', 'promo-2']));
  });

  it('nothing chosen sends no promotion', async () => {
    renderIt();
    await screen.findByRole('listbox');
    expect(asList(lastArgs().promotionId)).toEqual([]);
  });
});
