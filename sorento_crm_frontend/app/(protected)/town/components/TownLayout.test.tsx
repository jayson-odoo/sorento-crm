import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/hooks/useTownSnapshot', () => ({
  useTownSnapshot: () => ({ snapshot: SNAPSHOT, error: null, isLoading: false }),
}));
vi.mock('next/dynamic', () => ({ default: () => () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/town',
  useSearchParams: () => new URLSearchParams(),
}));

import { TownCards } from './TownCards';
import { TownPage } from './TownPage';

const LONG = 'ZZT Fictional Extremely Long Sanitaryware And Ceramics Distribution Company';
const SNAPSHOT = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { amount: '9876543.21', invoice_count: 2202, credit_note_count: 0, customer_count: 2104, dealer_customer_count: 2104 },
  compare: { label: 'Mon 29 Dec', last_week_amount: '8000000.00', last_week_invoice_count: 2000 },
  shops: [{ key: 's1', kind: 'shop', account_label: null, today_docs: 4, rank: 1, name: LONG, today_amount: '1234567.89' }],
  warehouses: [], reorder: { below_count: 3000, set_count: 4000 }, deliveries: { to_deliver: 1500 },
  approvals: { total: 1200, purchase_requests: 1, quotation_documents: 1199 },
};

describe('busy-day layout', () => {
  it('lets a long name truncate and keeps a 7 digit amount on one line', () => {
    render(<TownCards snapshot={SNAPSHOT as never} />);
    const name = screen.getByTitle(/Extremely Long/);
    expect(name.className).toContain('truncate');
    expect(name.className).toContain('min-w-0');
    const amount = screen.getByText('RM 1,234,568');
    expect(amount.className).toContain('whitespace-nowrap');
    expect(amount.className).toContain('tabular-nums');
    expect(amount.className).toContain('shrink-0');
    expect(name.parentElement?.className).toContain('min-w-0');
  });

  it('lets every card shrink inside its column instead of widening the page', () => {
    const { container } = render(<TownCards snapshot={SNAPSHOT as never} />);
    container.querySelectorAll('button').forEach((card) => {
      expect(card.className).toContain('min-w-0');
      expect(card.className).toContain('minmax(0,1fr)');
    });
  });

  it('shows a 4 digit count compactly in the icon tile and exactly in the card', () => {
    const { container } = render(<TownCards snapshot={SNAPSHOT as never} />);
    const tiles = Array.from(container.querySelectorAll('button > span[aria-hidden="true"]')).map((t) => t.textContent);
    expect(tiles).toContain('2.1k');
    expect(tiles).toContain('1.5k');
    expect(tiles).toContain('1.2k');
    tiles.forEach((t) => expect(t?.length ?? 0).toBeLessThanOrEqual(4));
    expect(container.textContent).toContain('2,104 dealers');
    const tile = container.querySelector('button > span[aria-hidden="true"]') as HTMLElement;
    expect(tile.className).toContain('min-w-');
    expect(tile.className).toContain('px-1.5');
  });

  it('puts the page grid in a single shrinkable column below lg', () => {
    const { container } = render(<TownPage />);
    const grid = Array.from(container.querySelectorAll('div')).find((d) => d.className.includes('lg:grid-cols-'));
    expect(grid?.className).toContain('grid-cols-[minmax(0,1fr)]');
    expect(container.querySelector('.min-w-0.lg\\:col-span-2, .min-w-0')).not.toBeNull();
  });
});
