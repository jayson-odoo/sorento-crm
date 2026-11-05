/**
 * PRICETAG-DESIGNER-GAPS item 3 (F6): an icon asset in the library tab offers "Show when"
 * (spec + value(s)) saved through the asset service; a non-icon asset does not.
 *
 * Names the tests fix for the coder: `setAssetShowWhen(assetId, { spec_key, values })` in
 * `services/assetService`, and a per-asset button whose accessible name is "Show when" plus
 * the asset name (e.g. aria-label "Show when: Hot").
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const { setAssetShowWhen } = vi.hoisted(() => ({
  setAssetShowWhen: vi.fn(async (id: string, body: { spec_key: string | null; values: string[] }) => ({
    id,
    name: 'Hot',
    kind: 'icon',
    tags: [],
    url: null,
    mime_type: 'image/png',
    show_when_spec_key: body.spec_key,
    show_when_values: body.spec_key ? body.values : null,
  })),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => [
    { id: 'icon1', name: 'Hot', kind: 'icon', tags: [], url: 'https://cdn.test/hot.png', mime_type: 'image/png' },
    { id: 'badge1', name: 'Rimless', kind: 'badge', tags: [], url: 'https://cdn.test/b.png', mime_type: 'image/png' },
  ]),
  uploadAsset: vi.fn(),
  setAssetShowWhen,
}));
// S1 (fix round 1): the editor reads the dealer-kit spec vocabulary, never the master-data
// registry route (gated on a permission marketing does not hold).
vi.mock('../../services/tagDataService', () => ({
  listSpecKeys: vi.fn(async () => [
    {
      key: 'water_supply',
      label: 'Water supply',
      unit: null,
      data_type: 'enum',
      allowed_values: ['cold_only', 'mixer'],
      value_labels: { cold_only: 'Cold only', mixer: 'Mixer' },
    },
  ]),
}));
vi.mock(
  '@/app/(protected)/master-data-management/product-specifications/services/productSpecService',
  () => ({
    getSpecRegistry: vi.fn(async () => {
      throw new Error('the master-data registry must not be read here');
    }),
  }),
);
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
    placeholder?: string;
  }) => (
    <select
      aria-label={props['aria-label'] ?? props.placeholder ?? 'select'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
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
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
  }) => (
    <fieldset aria-label="Values">
      {(props.options ?? []).map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            checked={props.value.includes(o.value)}
            onChange={(e) =>
              props.onChange(
                e.target.checked ? [...props.value, o.value] : props.value.filter((v) => v !== o.value),
              )
            }
          />
          {o.label}
        </label>
      ))}
    </fieldset>
  ),
}));

import { AssetPickerDialog } from './AssetPickerDialog';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AssetPickerDialog open productImages={[]} allowProductPhotos={false} onCancel={vi.fn()} onPick={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('AssetPickerDialog show-when', () => {
  it('offers "Show when" on an icon and not on a badge', async () => {
    mount();
    await waitFor(() => expect(screen.getByTitle('Hot')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /show when.*hot/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show when.*rimless/i })).toBeNull();
  });

  it('saves the chosen spec and values through the asset service', async () => {
    mount();
    await waitFor(() => expect(screen.getByTitle('Hot')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /show when.*hot/i }));

    const select = await screen.findByRole('combobox');
    await screen.findByRole('option', { name: 'Water supply' });
    fireEvent.change(select, { target: { value: 'water_supply' } });

    fireEvent.click(await screen.findByLabelText('Mixer'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() =>
      expect(setAssetShowWhen).toHaveBeenCalledWith('icon1', {
        spec_key: 'water_supply',
        values: ['mixer'],
      }),
    );
  });
});
