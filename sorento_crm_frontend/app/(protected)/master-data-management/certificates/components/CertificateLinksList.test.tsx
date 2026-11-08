/**
 * CertificateLinksList (CERT-LINK-CLEANUP card R1-R4): default view, verdict counts, the one-time
 * check request, filters. Same jsdom stand-ins as CertificatesList.test.tsx. Bulk Confirm / Remove are
 * row-selection driven, which the shared DataGrid cannot do under jsdom; the browser pass covers them.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/certificates/links',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

type MenuProps = {
  children?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
};
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuProps) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: MenuProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
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

// Native-select stand-in; aria-label = placeholder. Every filter select in the
// toolbar carries a distinct placeholder, so each is addressable.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    disabled,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

// Validity, Scheme and Status are multi-selects now (FILTER-MULTISELECT PR4): the same native stand-in,
// a multiple <select> labelled by its placeholder.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      multiple
      aria-label={placeholder ?? 'multi'}
      value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const svc = vi.hoisted(() => ({
  getCertificateLinks: vi.fn(),
  checkCertificateLinks: vi.fn(),
  confirmCertificateLinks: vi.fn(),
}));
vi.mock('../services/certificateLinkService', () => svc);
vi.mock('../hooks/useCertificates', () => ({
  useCertificates: () => ({ data: { data: [{ id: 'cert-1', scheme: 'SPAN', certificate_number: 'BPAI/1327-2024' }] } }),
}));
const createPendingAction = vi.hoisted(() => vi.fn());
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...a: unknown[]) => createPendingAction(...a),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import CertificateLinksList from './CertificateLinksList';
import type { CertificateLink, CertificateLinksResponse } from '../types/certificateLink.types';

function link(over: Partial<CertificateLink> = {}): CertificateLink {
  return {
    id: 'link-1',
    certificate_id: 'cert-1',
    scheme: 'SPAN',
    certificate_number: 'BPAI/1327-2024',
    certificate_type: 'Certification',
    certificate_status: 'active',
    product_id: 'p-1',
    product_code: 'BRD7711CP',
    product_name: 'Towel rail',
    model_code: '14A',
    model_code_source: 'ai',
    source: 'ai',
    verdict: 'not_found',
    check_code: '14A',
    checked_at: '2026-11-08T00:00:00',
    ...over,
  };
}

function response(rows: CertificateLink[], summary: Partial<CertificateLinksResponse['summary']> = {}): CertificateLinksResponse {
  return {
    data: rows,
    pagination: { total: rows.length, page: 1, limit: 50 },
    empty: rows.length === 0,
    summary: { found: 2, check: 0, not_found: rows.length, scanned: 0, no_file: 0, pending: 0, ...summary },
    types: [{ id: 'type-1', name: 'Certification' }],
    pending_all: summary.pending ?? 0,
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CertificateLinksList />
    </QueryClientProvider>,
  );
}

describe('CertificateLinksList', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    svc.checkCertificateLinks.mockResolvedValue({ queued: 1 });
    svc.confirmCertificateLinks.mockResolvedValue({ confirmed: 1 });
  });

  it('opens on AI links the certificate text does not back up', async () => {
    svc.getCertificateLinks.mockResolvedValue(response([link()]));
    renderList();
    await waitFor(() => expect(svc.getCertificateLinks).toHaveBeenCalled());
    const params = svc.getCertificateLinks.mock.calls[0][0];
    expect(params.verdicts).toEqual(['not_found', 'check']);
    expect(params.source).toBe('ai');
    expect(params.certificateId).toBeUndefined();
  });

  it('labels each verdict option with its count', async () => {
    svc.getCertificateLinks.mockResolvedValue(response([link()], { found: 7, pending: 0 }));
    renderList();
    expect(await screen.findByRole('option', { name: 'Found (7)' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Not found (1)' })).toBeTruthy();
  });

  it('asks the worker to check once when links are not checked yet', async () => {
    svc.getCertificateLinks.mockResolvedValue(response([link({ verdict: 'pending' })], { pending: 3 }));
    renderList();
    await waitFor(() => expect(svc.checkCertificateLinks).toHaveBeenCalledTimes(1));
  });

  it('asks for a check when links outside the view are unchecked', async () => {
    svc.getCertificateLinks.mockResolvedValue({ ...response([link()]), pending_all: 4 });
    renderList();
    await waitFor(() => expect(svc.checkCertificateLinks).toHaveBeenCalledTimes(1));
  });

  it('does not ask for a check when every link is checked', async () => {
    svc.getCertificateLinks.mockResolvedValue(response([link()]));
    renderList();
    await waitFor(() => expect(svc.getCertificateLinks).toHaveBeenCalled());
    expect(svc.checkCertificateLinks).not.toHaveBeenCalled();
  });

  it('filters by certificate and verdict', async () => {
    svc.getCertificateLinks.mockResolvedValue(response([link()]));
    renderList();
    await screen.findByRole('option', { name: 'Found (2)' });
    fireEvent.change(screen.getByLabelText('Every certificate'), { target: { value: 'cert-1' } });
    await waitFor(() =>
      expect(svc.getCertificateLinks.mock.calls.at(-1)?.[0].certificateId).toBe('cert-1'),
    );
    const verdict = screen.getByLabelText('Every verdict') as HTMLSelectElement;
    for (const option of Array.from(verdict.options)) option.selected = option.value === 'scanned';
    fireEvent.change(verdict);
    await waitFor(() =>
      expect(svc.getCertificateLinks.mock.calls.at(-1)?.[0].verdicts).toEqual(['scanned']),
    );
  });

  it('filters by certificate type and status, with the types the list returned', async () => {
    svc.getCertificateLinks.mockResolvedValue(response([link()]));
    renderList();
    await screen.findByRole('option', { name: 'Certification' });
    const types = screen.getByLabelText('Every type') as HTMLSelectElement;
    for (const option of Array.from(types.options)) option.selected = option.value === 'type-1';
    fireEvent.change(types);
    await waitFor(() => expect(svc.getCertificateLinks.mock.calls.at(-1)?.[0].typeIds).toEqual(['type-1']));
    const status = screen.getByLabelText('Active and archived') as HTMLSelectElement;
    for (const option of Array.from(status.options)) option.selected = option.value === 'archived';
    fireEvent.change(status);
    await waitFor(() => expect(svc.getCertificateLinks.mock.calls.at(-1)?.[0].statuses).toEqual(['archived']));
  });
});
