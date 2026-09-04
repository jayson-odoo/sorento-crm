/**
 * Settings -> General -> "Default unit of measure".
 *
 * The unit a product gets when nobody states one. It was a constant in the backend (`EA`,
 * and before that whatever unit the database happened to return first, which is how 11,415
 * products ended up stamped `L`), so the only way to correct it was a backfill script
 * guessing what an admin could simply say. This field is that statement, and the product
 * import reads it.
 *
 * Scoped to this one field: the rest of the general settings form is unchanged and has its
 * own behaviour, and a test that re-asserted the whole form would fail on every future
 * field somebody adds to it.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

// The units master, as `GET /master-data/units-of-measure/select` serves it. Eight rows in
// the real database, which is why the picker is a static list rather than a searched one.
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: [
      { id: 'uom-ea', uom_code: 'EA', uom_name: 'Each' },
      { id: 'uom-l', uom_code: 'L', uom_name: 'Litre' },
      { id: 'uom-ctn', uom_code: 'CTN', uom_name: 'Carton' },
    ],
    isLoading: false,
  }),
}));

// Stubbed as a deterministic native control (the same technique as
// `product-discontinued-scope-editor.test.tsx`), so picking an option is a plain
// `fireEvent.change` rather than a Radix popover interaction in jsdom. The `placeholder`
// becomes the accessible name, which is how this field is addressed below.
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

/** The body of the save this page POSTs, once it has been made. */
async function savedBody(): Promise<Record<string, unknown>> {
  const call = await waitFor(() => {
    const found = apiFetch.mock.calls.find(
      ([url]) => url === '/api/user-management/settings/general',
    );
    if (!found) throw new Error('the page has not saved yet');
    return found;
  });
  return JSON.parse((call[1] as { body: string }).body);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockSettings.defaultUomId = null;
  apiFetch.mockImplementation(async (url: string) => {
    if (url === '/api/procurement/suppliers/select') {
      return { ok: true, json: async () => [] };
    }
    return { ok: true, json: async () => ({ message: 'ok' }) };
  });
});

/** The Default unit of measure control, by the accessible name its placeholder gives it. */
const unitSelect = () => screen.getByLabelText('Select unit') as HTMLSelectElement;

describe('Settings - the default unit of measure', () => {
  it('offers the field, and reads Automatic when nobody has chosen one', () => {
    wrap(<SettingsGeneralPage />);

    expect(screen.getByText('Default unit of measure')).toBeInTheDocument();
    // "Automatic" rather than a blank: the backend still has a fallback, and a blank would
    // read as "products get no unit at all".
    // Scoped to this select: the default-supplier picker beside it offers a choice of the
    // same name, for the same reason.
    expect(unitSelect().value).toBe('__none__');
    expect(within(unitSelect()).getByText('Automatic')).toBeInTheDocument();
  });

  it('shows every unit by CODE and name, never by its id', () => {
    mockSettings.defaultUomId = 'uom-ctn';
    wrap(<SettingsGeneralPage />);

    expect(unitSelect().value).toBe('uom-ctn');
    // No UUIDs in the UI: the id is the option's value attribute, never its text.
    expect(
      Array.from(unitSelect().options).map((o) => o.textContent),
    ).toEqual(['Automatic', 'EA - Each', 'L - Litre', 'CTN - Carton']);
  });

  it('saves the picked unit as its id', async () => {
    wrap(<SettingsGeneralPage />);

    fireEvent.change(unitSelect(), { target: { value: 'uom-ea' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    expect((await savedBody()).default_uom_id).toBe('uom-ea');
  });

  it('saves null when the admin puts it back to Automatic', async () => {
    mockSettings.defaultUomId = 'uom-l';
    wrap(<SettingsGeneralPage />);

    fireEvent.change(unitSelect(), { target: { value: '__none__' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    // `null`, not the sentinel: the column is nullable and null is what "let the backend
    // decide" means on the wire.
    expect((await savedBody()).default_uom_id).toBeNull();
  });
});
