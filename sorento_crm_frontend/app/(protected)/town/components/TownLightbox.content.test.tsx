import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TownLightbox } from './TownLightbox';

const SNAPSHOT = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { amount: '100.00', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [], warehouses: [], reorder: { below_count: 7, set_count: 20 }, deliveries: { to_deliver: 2 },
  approvals: { total: 1, purchase_requests: 1, quotation_documents: 0 },
};

describe('TownLightbox', () => {
  it('shows the target, links to the existing screen, and says nothing more about the figure', () => {
    render(<TownLightbox snapshot={SNAPSHOT as never} target={{ kind: 'low' }} onClose={() => undefined} />);
    expect(screen.getByText('7 products low')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open reorder planning' }).getAttribute('href')).toBe('/scm/reorder');
  });

  it('names the last week row as the whole day', () => {
    const withCompare = { ...SNAPSHOT, compare: { label: 'Tue 27 Oct', last_week_amount: '50.00', last_week_invoice_count: 1 } };
    render(<TownLightbox snapshot={withCompare as never} target={{ kind: 'sales' }} onClose={() => undefined} />);
    expect(screen.getByText('vs all of Tue 27 Oct')).toBeTruthy();
  });

  it('has no explanatory line under the sales title', () => {
    render(<TownLightbox snapshot={SNAPSHOT as never} target={{ kind: 'sales' }} onClose={() => undefined} />);
    expect(screen.queryByText(/Same figure as the sales report/)).toBeNull();
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<TownLightbox snapshot={SNAPSHOT as never} target={{ kind: 'low' }} onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('gives the dialog a description, so Radix has nothing to warn about', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(<TownLightbox snapshot={SNAPSHOT as never} target={{ kind: 'sales' }} onClose={() => undefined} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy();
    const logged = [...warn.mock.calls, ...error.mock.calls].flat().join(' ');
    expect(logged).not.toMatch(/Missing `Description`/);
    warn.mockRestore();
    error.mockRestore();
  });
});
