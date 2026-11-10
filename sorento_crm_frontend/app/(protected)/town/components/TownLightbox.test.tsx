import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { TownSnapshot } from '@/types/town.types';
import { TownLightbox } from './TownLightbox';

type Row = { shipment_number: string; container: string | null; supplier?: string | null; eta: string | null; products: number; quantity: number; late: boolean };

const BASE = {
  schema: 1, company_id: 'c', day: '2026-11-05', as_of: '2026-11-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { amount: '100.00', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [{ key: 's1', kind: 'shop', account_label: null, today_docs: 1, rank: 3 }],
  warehouses: [], reorder: { below_count: 7, set_count: 20 }, deliveries: { to_deliver: 2 },
  approvals: { total: 1, purchase_requests: 1, quotation_documents: 0 },
};

const row = (n: string, over: Partial<Row> = {}): Row => ({
  shipment_number: n, container: 'CONT-' + n, supplier: 'Acme Trading', eta: '2026-11-09', products: 2, quantity: 40, late: false, ...over,
});

function snap(incoming?: unknown): TownSnapshot {
  return { ...BASE, ...(incoming ? { incoming } : {}) } as unknown as TownSnapshot;
}

const noop = () => undefined;

describe('TownLightbox', () => {
  it('opens a dialog named for the shop, not a side sheet', () => {
    render(<TownLightbox snapshot={snap()} target={{ kind: 'shop', key: 's1' }} onClose={noop} />);
    expect(screen.getByRole('dialog', { name: 'Shop #3' })).toBeTruthy();
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<TownLightbox snapshot={snap()} target={{ kind: 'low' }} onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('renders no dialog when there is no target', () => {
    render(<TownLightbox snapshot={snap()} target={null} onClose={noop} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  describe('port', () => {
    const incoming = {
      incoming: 2, late: 1, next_eta: '2026-11-09',
      shipments: [row('ZZT-SHIP-1'), row('ZZT-SHIP-2', { eta: null, supplier: 'Beta Foods' }), row('ZZT-SHIP-LATE', { eta: '2026-11-01', late: true })],
    };

    it('lists incoming and late shipments with supplier and the packing list link', () => {
      render(<TownLightbox snapshot={snap(incoming)} target={{ kind: 'port' }} onClose={noop} />);
      expect(screen.getByRole('dialog', { name: 'Incoming shipments' })).toBeTruthy();
      expect(screen.getAllByRole('heading').some((h) => /Incoming/.test(h.textContent ?? '') && h.textContent !== 'Incoming shipments')).toBe(true);
      expect(screen.getAllByRole('heading').some((h) => /Late/.test(h.textContent ?? ''))).toBe(true);
      for (const n of ['ZZT-SHIP-1', 'ZZT-SHIP-2', 'ZZT-SHIP-LATE']) expect(screen.getByText(n)).toBeTruthy();
      expect(screen.getAllByText(/Acme Trading/).length).toBeGreaterThan(0);
      expect(screen.getByText(/Beta Foods/)).toBeTruthy();
      expect(screen.getByRole('link', { name: 'Open packing lists' }).getAttribute('href')).toBe('/procurement-management/packing-lists');
    });

    it('shows no supplier text and does not crash when the rows are redacted', () => {
      const redacted = { ...incoming, shipments: incoming.shipments.map(({ supplier: _s, ...r }) => r) };
      render(<TownLightbox snapshot={snap(redacted)} target={{ kind: 'port' }} onClose={noop} />);
      expect(screen.getByText('ZZT-SHIP-1')).toBeTruthy();
      expect(screen.queryByText(/Acme Trading/)).toBeNull();
      expect(screen.queryByText(/undefined|null/)).toBeNull();
    });

    it('says nothing is on the way when empty', () => {
      render(<TownLightbox snapshot={snap({ incoming: 0, late: 0, next_eta: null, shipments: [] })} target={{ kind: 'port' }} onClose={noop} />);
      expect(screen.getByText('Nothing on the way')).toBeTruthy();
    });

    it('shows how many incoming shipments the list leaves out', () => {
      const rows = Array.from({ length: 30 }, (_, i) => row(`ZZT-N${String(i).padStart(2, '0')}`));
      render(<TownLightbox snapshot={snap({ incoming: 35, late: 0, next_eta: '2026-11-09', shipments: rows })} target={{ kind: 'port' }} onClose={noop} />);
      expect(screen.getByText('+ 5 more')).toBeTruthy();
    });
  });
});
