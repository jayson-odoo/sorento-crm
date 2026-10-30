/**
 * TAG-BRAND-CLASS AC-7: the tag Access settings Brands row carries the contact card's
 * "Allowed item classes" picker, with All brands on or off. Empty = not set on the tag.
 * The owner's case: All brands on, allowed "No class, DIY" (SERENE left out).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-tags/t1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const ITEM_CLASSES = [
  { value: '__NONE__', label: 'No class' },
  { value: 'DIY', label: 'SORENTO LITE - DIY' },
  { value: 'SERENE', label: 'SORENTO SERENE SERIES' },
];
const CATALOG = {
  access_types: [], brands: [], item_classes: ITEM_CLASSES, market_segments: [],
  attachment_types: [], field_reveals: [], portal_forms: [], spec_keys: [],
};
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockImplementation(async () => ({ ok: true, status: 200, json: async () => CATALOG })),
}));

const updateContactTag = vi.fn();
vi.mock('../services/contactTagService', () => ({
  updateContactTag: (...a: unknown[]) => updateContactTag(...a),
  getContactTag: vi.fn(),
  getContactTags: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
  }: {
    id?: string;
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <div data-testid={id ?? 'multi'} data-placeholder={placeholder ?? ''} data-value={value.join(',')}>
      {(options ?? []).map((o) => (
        <button key={o.value} type="button" onClick={() => onChange([...value, o.value])}>
          pick {o.label}
        </button>
      ))}
    </div>
  ),
}));

import ContactTagSettings from './ContactTagSettings';

const tag = (settings: Record<string, unknown>) => ({
  id: 't1', name: 'Dealer', description: null, is_active: true, sort_order: 0, settings,
  contact_count: 0, created_at: '', updated_at: '',
});

function render(settings: Record<string, unknown>, editing: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  rtlRender(
    <QueryClientProvider client={client}>
      <ContactTagSettings tag={tag(settings) as never} editing={editing} onDone={vi.fn()} />
    </QueryClientProvider>,
  );
}

const brandsGroup = () =>
  screen
    .getAllByTestId('settings-group')
    .find((g) => within(g).getByTestId('settings-group-title').textContent === 'Brands')!;

beforeEach(() => {
  vi.clearAllMocks();
  updateContactTag.mockResolvedValue(tag({}));
});

describe('tag Brands row: allowed item classes', () => {
  it('with All brands on, the owner sets "No class, DIY" and Save sends item_classes', async () => {
    render({}, true);
    fireEvent.click(within(brandsGroup()).getByRole('switch', { name: /set on this tag/i }));
    const picker = await within(brandsGroup()).findByTestId('tag-item-classes');
    expect(picker).toHaveAttribute('data-placeholder', 'All classes');
    expect(within(brandsGroup()).getByRole('switch', { name: 'All brands' })).toBeChecked();
    fireEvent.click(await within(picker).findByText('pick SORENTO LITE - DIY'));
    await waitFor(() => expect(picker).toHaveAttribute('data-value', '__NONE__,DIY'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
    expect(updateContactTag.mock.calls[0][1]).toEqual({
      settings: { brands: 'all', item_classes: ['__NONE__', 'DIY'] },
    });
  });

  it('the picker shows with brands picked too', async () => {
    render({ brands: ['b1'] }, true);
    expect(await within(brandsGroup()).findByTestId('tag-item-classes')).toBeInTheDocument();
  });

  it('no class picked leaves item_classes off the tag', async () => {
    render({}, true);
    fireEvent.click(within(brandsGroup()).getByRole('switch', { name: /set on this tag/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
    expect(updateContactTag.mock.calls[0][1]).toEqual({ settings: { brands: 'all' } });
  });

  it('view mode names the allowed classes and never shows SERENE', async () => {
    render({ brands: 'all', item_classes: ['__NONE__', 'DIY'] }, false);
    const g = brandsGroup();
    expect(await within(g).findByText('SORENTO LITE - DIY')).toBeInTheDocument();
    expect(within(g).getByText('No class')).toBeInTheDocument();
    expect(within(g).getByText('All brands')).toBeInTheDocument();
    expect(within(g).queryByText('SORENTO SERENE SERIES')).toBeNull();
  });

  it('switching the Brands row off drops item_classes too', async () => {
    render({ brands: 'all', item_classes: ['DIY'] }, true);
    fireEvent.click(within(brandsGroup()).getByRole('switch', { name: /set on this tag/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
    expect(updateContactTag.mock.calls[0][1]).toEqual({ settings: {} });
  });
});
