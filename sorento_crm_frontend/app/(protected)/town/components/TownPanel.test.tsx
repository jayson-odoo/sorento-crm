import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TownPanel } from './TownPanel';

const SNAPSHOT = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { amount: '100.00', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [], warehouses: [], reorder: { below_count: 7, set_count: 20 }, deliveries: { to_deliver: 2 },
  approvals: { total: 1, purchase_requests: 1, quotation_documents: 0 },
};

describe('TownPanel', () => {
  it('shows the target, links to the existing screen, and says nothing more about the figure', () => {
    render(<TownPanel snapshot={SNAPSHOT as never} target={{ kind: 'low' }} onClose={() => undefined} />);
    expect(screen.getByText('7 products low')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open reorder list' }).getAttribute('href')).toBe('/scm/reorder');
  });

  it('has no explanatory line under the sales title', () => {
    render(<TownPanel snapshot={SNAPSHOT as never} target={{ kind: 'sales' }} onClose={() => undefined} />);
    expect(screen.queryByText(/Same figure as the sales report/)).toBeNull();
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<TownPanel snapshot={SNAPSHOT as never} target={{ kind: 'low' }} onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
