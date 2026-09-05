/**
 * Settings -> General -> "Default supplier (new products)" while its saved value is
 * still resolving (M5-02 review S7).
 *
 * The saved supplier id can be missing from the (paged) select list - a supplier
 * outside the first page, say - so the page fires a one-off lookup to fill in its
 * name. While that lookup is in flight, the select used to synthesise a FAKE,
 * SELECTABLE option (`{ supplier_name: 'Loading supplier…' }`): a picker choice
 * that read as data rather than a loading state. Now nothing extra is added to the
 * option list at all - the id genuinely is not resolvable yet - so the select falls
 * back to its placeholder until the lookup resolves one way or the other.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
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
Element.prototype.scrollIntoView = vi.fn();

const mockSettings: Record<string, unknown> = {
  id: 's1',
  name: 'Sorento',
  active: true,
  supportEmail: 'ops@sorento.test',
  language: 'en',
  timezone: 'Asia/Kuala_Lumpur',
  currency: 'MYR',
  currencyFormat: 'RM {value}',
  defaultUomId: null,
  defaultProductSupplierId: 'sup-not-yet-loaded',
};
vi.mock('./components/settings-context', () => ({
  useSettings: () => ({ settings: mockSettings, roles: [] }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/purchaseRequestService',
  () => ({ getUsersForApproverSelect: vi.fn().mockResolvedValue([]) }),
);

vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({ data: [], isLoading: false }),
}));

// Same native-control stub `page.deferredWindows.test.tsx` and `page.defaultUom.test.tsx`
// use: the `placeholder` becomes the accessible name, so each field is addressed by it.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import SettingsGeneralPage from './page';

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const supplierSelect = () => screen.getByLabelText('Select supplier') as HTMLSelectElement;

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  apiFetch.mockImplementation((url: string) => {
    if (url === '/api/procurement/suppliers/select') {
      // The saved id is not on this page - the fallback lookup below is what
      // resolves it.
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    if (url === '/api/procurement/suppliers/sup-not-yet-loaded') {
      // Never resolves within the test - `isFetching` stays true throughout,
      // which is the exact window the synthetic row used to appear in.
      return new Promise(() => {});
    }
    return Promise.resolve({ ok: true, json: async () => ({ message: 'ok' }) });
  });
});

describe('Settings - default supplier while its saved value is still resolving', () => {
  it('offers no option whose text says Loading while the fallback lookup is in flight', async () => {
    wrap(<SettingsGeneralPage />);

    // The list settles at "Automatic" only - the saved-but-unresolved supplier
    // contributes no row at all while its own lookup is still in flight.
    await screen.findByLabelText('Select supplier');
    const optionTexts = Array.from(supplierSelect().options).map((o) => o.textContent ?? '');
    expect(optionTexts).toEqual(['Automatic']);
    expect(optionTexts.some((text) => text.includes('Loading'))).toBe(false);
  });
});
