/**
 * FILTER-MULTISELECT PR2: the Translations Language filter takes several values (OR within the
 * filter), comma-joined to the list hook. Nothing chosen sends no language. Harness mirrors
 * TranslationsList.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/translations',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
const hooks = vi.hoisted(() => ({ useTranslations: vi.fn(), useUpdateTranslation: vi.fn() }));
vi.mock('../hooks/useTranslations', () => hooks);
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import TranslationsList from './TranslationsList';

const lastArgs = () => {
  const calls = hooks.useTranslations.mock.calls;
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
  vi.clearAllMocks();
  hooks.useUpdateTranslation.mockReturnValue({ mutate: vi.fn(), isPending: false });
  hooks.useTranslations.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true },
    isLoading: false, isError: false, error: null,
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TranslationsList />
    </QueryClientProvider>,
  );
}
const control = () => within(screen.getByTestId('translations-language-filter'));

describe('Translations - multi Language filter', () => {
  it('is a multi control', async () => {
    renderIt();
    expect((await control().findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two languages go to the hook comma-joined', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.selectOptions(await control().findByRole('listbox'), ['en', 'zh']);
    await waitFor(() => expect(lastArgs().targetLang).toBe('en,zh'));
  });

  it('nothing chosen sends no language', async () => {
    renderIt();
    await control().findByRole('listbox');
    expect(['', undefined]).toContain(lastArgs().targetLang);
  });
});
