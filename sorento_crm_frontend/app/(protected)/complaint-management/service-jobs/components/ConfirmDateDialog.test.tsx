/**
 * AFTER-SALES-P1 red tests (UAC D4, C1 on the client): Confirm date dialog.
 *
 * Contract: `./ConfirmDateDialog` default export, props
 *   { open: boolean; onOpenChange: (open: boolean) => void;
 *     initialScheduledFrom?: string;            // ISO, pre-fills the date for the test and for re-confirm
 *     onSubmit: (v: { scheduled_from: string; scheduled_to: string | null; customer_agreed_by: string }) => void;
 *     isPending?: boolean }
 * Fields: shared DatePicker with time (dd/mm/yyyy), text field labelled "Agreed by".
 * Submit button is named "Confirm date".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

import ConfirmDateDialog from './ConfirmDateDialog';

function setup(over: Record<string, unknown> = {}) {
  const onSubmit = vi.fn();
  render(
    <ConfirmDateDialog open onOpenChange={() => {}} onSubmit={onSubmit}
      initialScheduledFrom="2026-11-20T10:00:00+08:00" {...over} />,
  );
  return onSubmit;
}

describe('ConfirmDateDialog (D4)', () => {
  it('opens as a centred dialog', () => {
    setup();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('uses no browser-native date input', () => {
    setup();
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelector('input[type="date"], input[type="datetime-local"], input[type="time"]')).toBeNull();
  });

  it('shows the date as dd/mm/yyyy', () => {
    setup();
    expect(screen.getByRole('dialog').textContent).toMatch(/20\/11\/2026/);
  });

  it('refuses to submit without who agreed (C1)', async () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm date' }));
    await waitFor(() => expect(screen.getByRole('dialog').textContent).toMatch(/agreed by/i));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('refuses a blank (spaces only) agreed-by', async () => {
    const onSubmit = setup();
    fireEvent.change(screen.getByLabelText(/Agreed by/i), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm date' }));
    await new Promise((r) => setTimeout(r, 30));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits date and trimmed agreed-by', async () => {
    const onSubmit = setup();
    fireEvent.change(screen.getByLabelText(/Agreed by/i), { target: { value: ' Ms Lim ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm date' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const v = onSubmit.mock.calls[0][0];
    expect(v.customer_agreed_by).toBe('Ms Lim');
    expect(typeof v.scheduled_from).toBe('string');
    expect(v.scheduled_to ?? null).toBeNull();
  });

  it('refuses to submit without a date (C1)', async () => {
    const onSubmit = setup({ initialScheduledFrom: undefined });
    fireEvent.change(screen.getByLabelText(/Agreed by/i), { target: { value: 'Ms Lim' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm date' }));
    await new Promise((r) => setTimeout(r, 30));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
