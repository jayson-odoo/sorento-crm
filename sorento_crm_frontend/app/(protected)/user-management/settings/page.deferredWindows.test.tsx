/**
 * Settings -> General -> the two deferred-action windows (D16, S6-04).
 *
 * The product asks for no confirmation: a delete or a status change parks on the
 * server and a countdown is the way back, so its LENGTH is the only thing left to
 * decide - ten seconds to catch a delete, five for something that can be set back.
 * Those two numbers are columns rather than constants so they are tuned here
 * rather than in a deploy.
 *
 * Scoped to the two fields. A new settings column reaches the server only if it is
 * on the schema, the mapper AND the save body, and this is where that chain is
 * checked from the form's end.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  deferredDeleteSeconds: 10,
  deferredActionSeconds: 5,
};
vi.mock('./components/settings-context', () => ({
  useSettings: () => ({ settings: mockSettings, roles: [] }),
}));

vi.mock('sonner', () => ({
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
  mockSettings.deferredDeleteSeconds = 10;
  mockSettings.deferredActionSeconds = 5;
  apiFetch.mockImplementation(async (url: string) => {
    if (url === '/api/procurement/suppliers/select') {
      return { ok: true, json: async () => [] };
    }
    return { ok: true, json: async () => ({ message: 'ok' }) };
  });
});



/** The two window inputs, by their labels. */
const deleteWindow = () =>
  screen.getByLabelText('Delete countdown (seconds)') as HTMLInputElement;
const changeWindow = () =>
  screen.getByLabelText('Change countdown (seconds)') as HTMLInputElement;

describe('Settings - the deferred-action windows', () => {
  it('offers both fields, at ten seconds and five', () => {
    wrap(<SettingsGeneralPage />);

    expect(deleteWindow().value).toBe('10');
    expect(changeWindow().value).toBe('5');
  });

  it('shows what the admin has already saved', () => {
    mockSettings.deferredDeleteSeconds = 20;
    mockSettings.deferredActionSeconds = 8;
    wrap(<SettingsGeneralPage />);

    expect(deleteWindow().value).toBe('20');
    expect(changeWindow().value).toBe('8');
  });

  it('saves both windows under the names the backend column carries', async () => {
    wrap(<SettingsGeneralPage />);

    fireEvent.change(deleteWindow(), { target: { value: '15' } });
    fireEvent.change(changeWindow(), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    const saved = await savedBody();
    expect(saved.deferred_delete_seconds).toBe(15);
    expect(saved.deferred_action_seconds).toBe(3);
  });
});
