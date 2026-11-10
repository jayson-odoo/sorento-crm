import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TownCards } from './TownCards';

/** TOWN-V2: the sixth card, "What is coming in?", from the snapshot's `incoming` block. */
const BASE = {
  schema: 1, company_id: 'c', day: '2026-11-03', as_of: '2026-11-03T15:42:00+08:00', data_as_of: null, phase: 'day',
  today: { amount: '100.00', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [], warehouses: [], reorder: { below_count: 1, set_count: 2 }, deliveries: { to_deliver: 1 },
  approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
};

describe('TownCards, incoming shipments', () => {
  it('asks what is coming in, with the incoming and late counts, after the five questions', () => {
    const snapshot = { ...BASE, incoming: { incoming: 29, late: 70, next_eta: '2026-11-11', shipments: [] } };
    const { container } = render(<TownCards snapshot={snapshot as never} />);
    expect(screen.getByText('What is coming in?')).toBeTruthy();
    expect(screen.getByText('29 incoming')).toBeTruthy();
    expect(screen.getByText(/70 late/)).toBeTruthy();
    const text = container.textContent ?? '';
    expect(text.indexOf('What needs a decision?')).toBeLessThan(text.indexOf('What is coming in?'));
  });

  it('opens the port lightbox', () => {
    const onOpen = vi.fn();
    const snapshot = { ...BASE, incoming: { incoming: 2, late: 0, next_eta: null, shipments: [] } };
    render(<TownCards snapshot={snapshot as never} onOpen={onOpen} />);
    fireEvent.click(screen.getByText('What is coming in?'));
    expect(onOpen).toHaveBeenCalledWith({ kind: 'port' });
  });

  it('says nothing is on the way at zero', () => {
    const snapshot = { ...BASE, incoming: { incoming: 0, late: 0, next_eta: null, shipments: [] } };
    render(<TownCards snapshot={snapshot as never} />);
    expect(screen.getByText('Nothing on the way')).toBeTruthy();
  });

  it('has no sixth card on a snapshot built before shipments existed', () => {
    render(<TownCards snapshot={BASE as never} />);
    expect(screen.queryByText('What is coming in?')).toBeNull();
  });
});
