/**
 * DATE-PICKER-UNIFY slice B: CurrencyRatesPanel "As at" is a typeable DatePickerField that
 * still saves as_of as YYYY-MM-DD. Harness copied from CurrencyRatesPanel.test.tsx.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
/* The grace window is the server's; what this file proves is that the row parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'currency_rate.delete',
  entity_type: 'currency_rate',
  entity_id: 'USD',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getCurrencyRates = vi.fn();
const saveCurrencyRate = vi.fn();
const deleteCurrencyRate = vi.fn();

vi.mock('../../services/currencyRateService', () => ({
  getCurrencyRates: (...a: unknown[]) => getCurrencyRates(...a),
  saveCurrencyRate: (...a: unknown[]) => saveCurrencyRate(...a),
  deleteCurrencyRate: (...a: unknown[]) => deleteCurrencyRate(...a),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

import { CurrencyRatesPanel } from './CurrencyRatesPanel';

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CurrencyRatesPanel />
    </QueryClientProvider>,
  );
}

const loaded = {
  base_currency: 'MYR',
  rates: [
    {
      currency: 'USD',
      rate_to_base: 4.4,
      as_of: '2026-08-01',
      note: 'bank rate',
      updated_at: '2026-08-01T00:00:00',
    },
  ],
  missing: ['CNY'],
};

beforeEach(() => {
  vi.clearAllMocks();
  getCurrencyRates.mockResolvedValue(loaded);
  saveCurrencyRate.mockResolvedValue(undefined);
  deleteCurrencyRate.mockResolvedValue(undefined);
});


describe('CurrencyRatesPanel - As at date (DATE-PICKER-UNIFY slice B)', () => {
  it('AC1/AC3: editing a rate shows the stored As at as dd/mm/yyyy, no native input', async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /^Edit USD$/i }));
    expect(await screen.findByLabelText('As at')).toHaveValue('01/08/2026');
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
  });

  it('AC2/AC9: typing 05/11/2026 and blurring saves as_of 2026-11-05', async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /^Edit USD$/i }));
    const asAt = await screen.findByLabelText('As at');
    fireEvent.change(asAt, { target: { value: '05/11/2026' } });
    fireEvent.blur(asAt);
    fireEvent.click(screen.getByRole('button', { name: /^Save currency rate$/i }));
    await waitFor(() =>
      expect(saveCurrencyRate).toHaveBeenCalledWith(
        'USD',
        expect.objectContaining({ as_of: '2026-11-05' }),
      ),
    );
  });
});
