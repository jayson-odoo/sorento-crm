/**
 * FILTER-MULTISELECT PR 2 slice A: the Onboarding requests Status filter takes several values
 * (comma-joined `status_key`), one chip, and an older link with one status still reads.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const url = vi.hoisted(() => ({ search: '' }));
const useRequestsMock = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useOnboardingRequests', () => ({
  useOnboardingRequests: (...a: unknown[]) => useRequestsMock(...a),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/onboarding-requests',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('next-auth/react', () => ({ useSession: () => ({ data: { user: { email: 'admin@zzt.test' } } }) }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('./NewOnboardingRequestDialog', () => ({ NewOnboardingRequestDialog: () => null }));
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

import { OnboardingRequestList } from './OnboardingRequestList';
import { ONBOARDING_STATUS_LABELS } from '@/components/common/onboarding/types';

const KEYS = Object.keys(ONBOARDING_STATUS_LABELS);

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OnboardingRequestList />
    </QueryClientProvider>,
  );
}
const lastParams = () => useRequestsMock.mock.calls[useRequestsMock.mock.calls.length - 1][0] as { statusKey?: string };

beforeEach(() => {
  vi.clearAllMocks();
  url.search = '';
  useRequestsMock.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true },
    isLoading: false, isPlaceholderData: false, refetch: vi.fn(), isFetching: false, error: null,
  });
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
});
afterEach(() => cleanup());

describe('Onboarding requests - multi Status filter', () => {
  it('is a multi control; two statuses go to the hook comma-joined with one chip', async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(await screen.findByRole('button', { name: /^filters/i }));
    const select = await screen.findByLabelText('Status: any');
    expect(select.hasAttribute('multiple')).toBe(true);
    await user.selectOptions(select, [KEYS[0], KEYS[1]]);
    await waitFor(() => expect(lastParams().statusKey).toBe(`${KEYS[0]},${KEYS[1]}`));
    await user.keyboard('{Escape}');
    const label = `Status: ${ONBOARDING_STATUS_LABELS[KEYS[0] as keyof typeof ONBOARDING_STATUS_LABELS]}, ${ONBOARDING_STATUS_LABELS[KEYS[1] as keyof typeof ONBOARDING_STATUS_LABELS]}`;
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it('an older link with one status reads back as a one-value filter', async () => {
    url.search = `status_key=${KEYS[2]}`;
    renderList();
    await waitFor(() => expect(lastParams().statusKey).toBe(KEYS[2]));
    expect(
      await screen.findByText(`Status: ${ONBOARDING_STATUS_LABELS[KEYS[2] as keyof typeof ONBOARDING_STATUS_LABELS]}`),
    ).toBeInTheDocument();
  });
});
