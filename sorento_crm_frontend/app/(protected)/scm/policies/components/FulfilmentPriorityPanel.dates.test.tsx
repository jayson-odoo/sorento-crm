/**
 * DATE-PICKER-UNIFY slice B: FulfilmentPriorityPanel. "Purchasing covers demand until" and
 * "TBA date from" are two unrelated single dates (not a from/to of one fact), so each is a
 * typeable DatePickerField. Harness copied from FulfilmentPriorityPanel.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const hooks = vi.hoisted(() => ({
  useFulfilmentPriority: vi.fn(),
  useSaveFulfilmentPriority: vi.fn(),
}));
vi.mock('../hooks/usePolicies', () => hooks);

import { FulfilmentPriorityPanel } from './FulfilmentPriorityPanel';

const DATA = {
  name: 'Fair fulfilment priority (delivery date, document date, customer credit)',
  factors: {
    po_document_sequence: 1,
    demand_class: 3,
    need_by_date: 3,
    document_age: 1,
    customer_credit: 1,
  },
  demand_class_weights: { project: 1, retail: 0.4 },
  reorder_coverage_until: '2026-10-31',
  tba_date_from: '2029-01-01',
  transfer_days: 0,
  exists: true,
};

/** The column default of `scm.priority_policy.tba_date_from` (migration 443). */
const DEFAULT_TBA = '2029-01-01';

/** Local calendar day, the way the panel computes "today" for its own mirror check. */
function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function isoDaysFromToday(days: number): string {
  const now = new Date();
  const shifted = new Date(now.getTime() + days * 86400000);
  return new Date(shifted.getTime() - shifted.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}
const mutateAsync = vi.fn();

beforeEach(() => {
  hooks.useFulfilmentPriority.mockReset();
  hooks.useSaveFulfilmentPriority.mockReset();
  mutateAsync.mockReset().mockResolvedValue(DATA);
  hooks.useSaveFulfilmentPriority.mockReturnValue({ mutateAsync, isPending: false });
});


function typeDate(el: HTMLElement, text: string) {
  fireEvent.change(el, { target: { value: text } });
  fireEvent.blur(el);
}

describe('FulfilmentPriorityPanel - dates (DATE-PICKER-UNIFY slice B)', () => {
  it('AC1/AC3: both dates read dd/mm/yyyy and there is no native date input', () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getByLabelText(/Purchasing covers demand until/i)).toHaveValue('31/10/2026');
    expect(screen.getByLabelText(/TBA date from/i)).toHaveValue('01/01/2029');
  });

  it('AC2/AC9: typing the coverage date and blurring saves reorder_coverage_until as YYYY-MM-DD', async () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);
    typeDate(screen.getByLabelText(/Purchasing covers demand until/i), '05/12/2026');
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].reorder_coverage_until).toBe('2026-12-05');
  });

  it('AC2/AC9: typing the TBA date and blurring saves tba_date_from as YYYY-MM-DD', async () => {
    hooks.useFulfilmentPriority.mockReturnValue({ data: DATA, isLoading: false, isError: false });
    render(<FulfilmentPriorityPanel />);
    typeDate(screen.getByLabelText(/TBA date from/i), '05/05/2031');
    fireEvent.click(screen.getByRole('button', { name: /Save fulfilment priority/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].tba_date_from).toBe('2031-05-05');
  });
});
