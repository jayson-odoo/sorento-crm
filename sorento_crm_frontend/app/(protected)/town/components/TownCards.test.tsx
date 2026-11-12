import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

/**
 * SORENTO-TOWN Phase 1: the five 2D cards (plan "Mock v3 approved"; the approved mock's
 * `renderCards`). They are the only view without WebGL or with reduced motion.
 *
 * Assumed export and prop: `import { TownCards } from './TownCards'`, `<TownCards snapshot={...} />`,
 * where `snapshot` is the API body: a full snapshot, a redacted one (no amount keys, anonymous
 * shops keyed s1..sN with no name/code/rank) or `{ pending: true }`.
 */
import { TownCards } from './TownCards';

const FULL = {
  schema: 1,
  company_id: '00000000-0000-0000-0000-000000000001',
  day: '2026-11-03',
  as_of: '2026-11-03T15:42:00+08:00',
  data_as_of: null,
  phase: 'day',
  today: {
    amount: '560000.00',
    invoice_count: 321,
    credit_note_count: 2,
    customer_count: 140,
    dealer_customer_count: 88,
  },
  compare: { label: 'Tue 27 Oct', last_week_amount: '500000.00', last_week_invoice_count: 201 },
  shops: [
    {
      key: '5f0c2c1e-8a4b-4f6e-9a57-1f3f7b0a9c11',
      code: 'ZZT-S001',
      name: 'ZZT Tiling One SDN BHD [A/C II]',
      account_label: 'A/C II',
      kind: 'shop',
      rank: 1,
      ninety_day_amount: '150000.00',
      today_amount: '30000.00',
      today_docs: 3,
    },
    {
      key: '6a1d3d2f-9b5c-4a7f-8b68-2a4a8c1b0d22',
      code: 'ZZT-S002',
      name: 'ZZT Quiet Dealer SDN BHD',
      account_label: null,
      kind: 'shop',
      rank: 2,
      ninety_day_amount: '90111.11',
      today_amount: '0.00',
      today_docs: 0,
    },
    {
      key: '7b2e4e30-ac6d-4b80-9c79-3b5b9d2c1e33',
      code: 'ZZT-S099',
      name: 'ZZT Stall Three ENTERPRISE',
      account_label: null,
      kind: 'stall',
      rank: null,
      ninety_day_amount: null,
      today_amount: '333.33',
      today_docs: 1,
    },
  ],
  warehouses: [{ pool: 'ZZT-WH01', on_hand: 800000, available: 790000, locations: 24 }],
  reorder: { below_count: 1234, set_count: 9876 },
  deliveries: { to_deliver: 17 },
  approvals: { total: 1, purchase_requests: 1, quotation_documents: 0 },
};

/** What the server sends a user without sales.reports.view (redact(): no amount, anonymous shops). */
const REDACTED = {
  ...FULL,
  today: { invoice_count: 321, credit_note_count: 2, customer_count: 140, dealer_customer_count: 88 },
  compare: { label: 'Tue 27 Oct', last_week_invoice_count: 201 },
  shops: [
    { key: 's1', account_label: 'A/C II', kind: 'shop', today_docs: 3 },
    { key: 's2', account_label: null, kind: 'shop', today_docs: 0 },
    { key: 's3', account_label: null, kind: 'stall', today_docs: 1 },
  ],
};

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/** Everything a person could read: text plus the attributes screen readers and tooltips expose. */
function visible(container: HTMLElement): string {
  const attrs = Array.from(container.querySelectorAll('[title],[aria-label],[alt]')).map(
    (el) => `${el.getAttribute('title') ?? ''} ${el.getAttribute('aria-label') ?? ''} ${el.getAttribute('alt') ?? ''}`,
  );
  return `${container.textContent ?? ''} ${attrs.join(' ')}`;
}

const QUESTIONS = [
  'How much did we sell today?',
  'Who bought today?',
  'What stock is low?',
  'What must go out?',
  'What needs a decision?',
];

describe('TownCards, full snapshot', () => {
  it('renders the five questions, in order', () => {
    const { container } = render(<TownCards snapshot={FULL as never} />);
    for (const q of QUESTIONS) expect(screen.getByText(q)).toBeTruthy();
    const text = container.textContent ?? '';
    const positions = QUESTIONS.map((q) => text.indexOf(q));
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });

  it('shows the RM amount, the invoice count and the change against the compare label', () => {
    const { container } = render(<TownCards snapshot={FULL as never} />);
    const text = container.textContent ?? '';
    expect(text).toMatch(/RM\s?560,000\.00/);
    expect(text).toMatch(/321\s+invoices/);
    expect(text).toMatch(/\+12%/); // (560000 - 500000) / 500000
    expect(text).toContain('vs all of Tue 27 Oct');
  });

  it('shows a fall as a negative percentage', () => {
    const lower = { ...FULL, compare: { ...FULL.compare, last_week_amount: '666666.67' } };
    const { container } = render(<TownCards snapshot={lower as never} />);
    expect(container.textContent).toMatch(/-16%/);
  });

  it('names only the shops that bought today (lit); a grey shop stays out', () => {
    const { container } = render(<TownCards snapshot={FULL as never} />);
    const text = container.textContent ?? '';
    expect(text).toContain('Tiling One');
    expect(text).toContain('Stall Three');
    expect(text).not.toContain('Quiet Dealer');
    expect(text).toMatch(/88\s+dealers/);
  });

  it('shows the low-stock count, the to-deliver count and the approvals total', () => {
    const { container } = render(<TownCards snapshot={FULL as never} />);
    const text = container.textContent ?? '';
    expect(text).toMatch(/1,234\s+products/);
    expect(text).toMatch(/17\s+to deliver/);
    expect(text).toMatch(/1\s+waiting/);
  });

  it('says All clear at zero approvals instead of hiding the card', () => {
    const clear = { ...FULL, approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 } };
    const { container } = render(<TownCards snapshot={clear as never} />);
    expect(screen.getByText('What needs a decision?')).toBeTruthy();
    expect(container.textContent).toContain('All clear');
    expect(container.textContent).not.toMatch(/0\s+waiting/);
  });

  it('renders no UUID-looking string, in text or in tooltips and labels', () => {
    const { container } = render(<TownCards snapshot={FULL as never} />);
    expect(visible(container)).not.toMatch(UUID);
  });

  it('shows no RM zero when the change cannot be computed (no compare)', () => {
    const noCompare = { ...FULL, compare: undefined };
    const { container } = render(<TownCards snapshot={noCompare as never} />);
    expect(container.textContent).not.toMatch(/NaN|Infinity|undefined/);
  });
});

describe('TownCards, redacted snapshot (no sales.reports.view)', () => {
  it('shows no RM text anywhere and no dealer name or code', () => {
    const { container } = render(<TownCards snapshot={REDACTED as never} />);
    const text = visible(container);
    expect(text).not.toMatch(/RM/);
    expect(text).not.toMatch(/\d[\d,]*\.\d{2}/); // no money-shaped figure either
    for (const leak of ['ZZT', 'Tiling', 'Stall Three', 'Quiet Dealer']) expect(text).not.toContain(leak);
  });

  it('still shows every count', () => {
    const { container } = render(<TownCards snapshot={REDACTED as never} />);
    for (const q of QUESTIONS) expect(screen.getByText(q)).toBeTruthy();
    const text = container.textContent ?? '';
    expect(text).toMatch(/321\s+invoices/);
    expect(text).toMatch(/1,234\s+products/);
    expect(text).toMatch(/17\s+to deliver/);
    expect(text).toMatch(/1\s+waiting/);
    expect(text).toMatch(/88\s+dealers/);
  });

  it('renders no UUID-looking string', () => {
    const { container } = render(<TownCards snapshot={REDACTED as never} />);
    expect(visible(container)).not.toMatch(UUID);
  });
});

describe('TownCards, pending snapshot', () => {
  it('shows an empty-state heading and no button, and none of the cards', () => {
    const { container } = render(<TownCards snapshot={{ pending: true } as never} />);
    expect(screen.getAllByRole('heading').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button')).toBeNull();
    expect(container.textContent).not.toContain('How much did we sell today?');
    expect(container.textContent).not.toMatch(/RM/);
  });
});
