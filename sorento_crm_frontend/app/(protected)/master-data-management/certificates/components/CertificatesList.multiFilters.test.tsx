/**
 * FILTER-MULTISELECT PR4: the Certificates list's Validity, Scheme and Status filters take several
 * values (OR within a filter, AND across), comma-joined to the data hook and in the page URL. An older
 * link holding one value reads back as a one-value filter. Review and Expiring within stay single.
 * Harness mirrors CertificatesList.test.tsx (hook mocked, dropdown menu inline).
 */
import React from 'react';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/certificates',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

type MenuProps = { children?: React.ReactNode; onClick?: () => void; disabled?: boolean };
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuProps) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: MenuProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>{children}</button>
  ),
  DropdownMenuCheckboxItem: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuSub: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: MenuProps) => <div>{children}</div>,
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, onChange, options, placeholder }: {
    value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'select'} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

const hooks = vi.hoisted(() => ({ useCertificates: vi.fn() }));
vi.mock('../hooks/useCertificates', () => ({
  useCertificates: (...a: unknown[]) => hooks.useCertificates(...a),
  useBulkDeleteCertificates: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCertificate: () => ({ data: undefined, isLoading: false }),
  useCreateCertificate: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCertificate: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import CertificatesList from './CertificatesList';

const ROW = {
  id: 'cert-1', scheme: 'PPS', certifying_body: 'SIRIM QAS', certificate_number: 'ZZT PPS 1/2026', issuer: 'SIRIM',
  title: 'ZZT Sanitary ware', status: 'active', validity_state: 'valid', is_expired: false, valid_from: '2026-01-01',
  valid_until: '2027-09-01', days_until_expiry: 300, covered_product_count: 3, needs_review: false, review_reasons: [],
  possible_duplicate_of_certificate_id: null, possible_duplicate_of: null, current_revision: null,
  created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
};

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => {
  const calls = hooks.useCertificates.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CertificatesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  hooks.useCertificates.mockReturnValue({
    data: { data: [ROW], empty: false, pagination: { page: 1, total: 1 } },
    isLoading: false, isFetching: false, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('Certificates - multi Validity, Scheme and Status filters', () => {
  it('Validity, Scheme and Status are multi controls', async () => {
    renderList();
    expect((await box('expired')).hasAttribute('multiple')).toBe(true);
    expect((await box('PPS')).hasAttribute('multiple')).toBe(true);
    expect((await box('archived')).hasAttribute('multiple')).toBe(true);
  });

  it('two validity states reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('expired'), ['expired', 'unknown']);
    await waitFor(() => expect(setOf(lastParams().validity_state)).toEqual(['expired', 'unknown']));
    expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument();
  });

  it('two schemes and two statuses reach the hook as sets of two', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('PPS'), ['PPS', 'SPAN']);
    await user.selectOptions(await box('archived'), ['active', 'archived']);
    await waitFor(() => {
      expect(setOf(lastParams().scheme)).toEqual(['PPS', 'SPAN']);
      expect(setOf(lastParams().status)).toEqual(['active', 'archived']);
    });
  });

  it('filters AND across: several validity states with a scheme', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('expired'), ['valid', 'expired']);
    await user.selectOptions(await box('PPS'), ['SPAN']);
    await waitFor(() => {
      expect(setOf(lastParams().validity_state)).toEqual(['expired', 'valid']);
      expect(setOf(lastParams().scheme)).toEqual(['SPAN']);
    });
  });

  it('the Any validity / All schemes sentinels are never sent', async () => {
    renderList();
    await box('expired');
    const p = lastParams();
    expect(setOf(p.validity_state)).toEqual([]);
    expect(setOf(p.scheme)).toEqual([]);
    expect(setOf(p.status)).toEqual([]);
  });

  it('Clear filters drops every multi filter', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('PPS'), ['PPS', 'SPAN']);
    await waitFor(() => expect(setOf(lastParams().scheme)).toEqual(['PPS', 'SPAN']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(setOf(lastParams().scheme)).toEqual([]));
  });

  it('a link with several values restores the controls and the request', async () => {
    url.search = 'validity_state=expired%2Cunknown&scheme=PPS%2CSPAN&status=active%2Carchived';
    renderList();
    await waitFor(() => {
      expect(setOf(lastParams().validity_state)).toEqual(['expired', 'unknown']);
      expect(setOf(lastParams().scheme)).toEqual(['PPS', 'SPAN']);
      expect(setOf(lastParams().status)).toEqual(['active', 'archived']);
    });
    expect(selected(await box('expired'))).toEqual(['expired', 'unknown']);
    expect(selected(await box('PPS'))).toEqual(['PPS', 'SPAN']);
  });

  it('an older link with one value per filter reads back as one-value filters', async () => {
    url.search = 'validity_state=expired&scheme=SPAN&status=archived';
    renderList();
    await waitFor(() => {
      expect(setOf(lastParams().validity_state)).toEqual(['expired']);
      expect(setOf(lastParams().scheme)).toEqual(['SPAN']);
      expect(setOf(lastParams().status)).toEqual(['archived']);
    });
    expect(selected(await box('expired'))).toEqual(['expired']);
  });
});
