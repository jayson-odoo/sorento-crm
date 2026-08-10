import { describe, expect, it } from 'vitest';
import {
  PRICE_ADVICE_SORT,
  describeLastPurchase,
  describePriceAdvice,
  humanAge,
  priceFootnotes,
  priceKey,
  type PriceAdvice,
} from './priceAdvice';

/**
 * The wording layer over `price_history_service.py`.
 *
 * The rule every test below is protecting: nothing this screen says may be a claim about
 * the market. The buyer set that boundary themselves ("we are blind to market condition"),
 * so a sentence that implies we know today's price is a defect, not a nicety.
 */

const base: PriceAdvice = {
  advice: 'recent',
  last: { po_number: '202012-S0048', issue_date: '2020-12-15', unit_cost: 20.37, currency: 'USD', qty: 38 },
  previous: null,
  age_days: 40,
  movement_pct: null,
  currency_changed: false,
  standing_cost: 20.37,
  standing_currency: 'USD',
  standing_gap_pct: 0,
  free_of_charge_lines: 0,
};

describe('humanAge', () => {
  it('says days while days still mean something', () => {
    expect(humanAge(1)).toBe('1 day ago');
    expect(humanAge(40)).toBe('40 days ago');
  });

  it('switches to months, then years, because 2064 days is not a readable number', () => {
    expect(humanAge(180)).toBe('6 months ago');
    expect(humanAge(2064)).toMatch(/^5 years/);
  });

  it('has no age for a purchase with no date', () => {
    expect(humanAge(null)).toBeNull();
  });
});

describe('describeLastPurchase', () => {
  it('carries the receipt with the number', () => {
    expect(describeLastPurchase(base.last)).toBe('USD 20.37, on 202012-S0048, 2020-12-15');
  });

  it('is null when we never bought it, rather than a zero', () => {
    expect(describeLastPurchase(null)).toBeNull();
  });
});

describe('describePriceAdvice', () => {
  it('never claims to know what the item is worth today', () => {
    for (const advice of ['zero_cost', 'no_history', 'unknown_age', 'stale', 'moving', 'recent'] as const) {
      const text = describePriceAdvice({ ...base, advice, movement_pct: 12, age_days: 2064 }, 180);
      expect(text).not.toMatch(/market|worth|going rate|current price of/i);
    }
  });

  it('leads a zero-costed line with the fact that it is costing nothing', () => {
    const text = describePriceAdvice({ ...base, advice: 'zero_cost', standing_cost: 0 }, 180);

    expect(text).toMatch(/costing this at zero/i);
    // and hands over the real figure to correct it with
    expect(text).toContain('USD 20.37');
  });

  it('tells a never-bought supplier to quote, without implying a number exists', () => {
    const text = describePriceAdvice({ ...base, advice: 'no_history', last: null, age_days: null }, 180);

    expect(text).toMatch(/no purchase from this supplier/i);
    expect(text).not.toContain('20.37');
  });

  it('states the stale rule it applied rather than asserting a bare verdict', () => {
    const text = describePriceAdvice({ ...base, advice: 'stale', age_days: 2064 }, 180);

    expect(text).toMatch(/6 month/);
    expect(text).toMatch(/fresh quote/i);
  });

  it('names the direction a price moved, in our own records', () => {
    const up = describePriceAdvice({ ...base, advice: 'moving', movement_pct: 12.5 }, 180);
    const down = describePriceAdvice({ ...base, advice: 'moving', movement_pct: -12.5 }, 180);

    expect(up).toMatch(/rose 12\.5%/);
    expect(down).toMatch(/fell 12\.5%/);
    expect(up).toMatch(/from the purchase before it/);
  });

  it('says a recent price can be reused, which is the whole point of asking', () => {
    expect(describePriceAdvice(base, 180)).toMatch(/recent enough to reuse/i);
  });

  it('has no opinion when it has no facts', () => {
    expect(describePriceAdvice(undefined, 180)).toMatch(/no price information/i);
  });
});

describe('priceFootnotes', () => {
  it('shows the purchase before last, so the movement can be checked', () => {
    const notes = priceFootnotes({
      ...base,
      previous: { po_number: 'PO-1', issue_date: '2020-06-01', unit_cost: 18.0, currency: 'USD', qty: 10 },
      movement_pct: 13.2,
    });

    expect(notes.join(' ')).toContain('USD 18.00');
    expect(notes.join(' ')).toContain('+13.2%');
  });

  it('explains an absent movement rather than leaving it looking like missing data', () => {
    const notes = priceFootnotes({ ...base, currency_changed: true });

    expect(notes.join(' ')).toMatch(/different currencies/);
  });

  it('reports the gap between the plan cost and what we paid, in the right direction', () => {
    // last paid sits 20% ABOVE the plan's cost, so the plan is costing 20% below it
    const notes = priceFootnotes({ ...base, standing_gap_pct: 20 });

    expect(notes.join(' ')).toMatch(/20\.0% below what we last paid/);
  });

  it('says nothing about a gap of zero, which is the common case and not news', () => {
    expect(priceFootnotes(base)).toEqual([]);
  });

  it('accounts for the zero-value lines it left out of the price', () => {
    const notes = priceFootnotes({ ...base, free_of_charge_lines: 2 });

    expect(notes.join(' ')).toMatch(/2 lines .* recorded no charge/);
  });
});

describe('priceKey', () => {
  it('needs both halves, because a price belongs to a product AND a supplier', () => {
    expect(priceKey('p1', 'S-01')).toBe('p1:S-01');
    expect(priceKey('p1', null)).toBeNull();
    expect(priceKey(null, 'S-01')).toBeNull();
  });
});

describe('PRICE_ADVICE_SORT', () => {
  it('puts a zero-costed line above everything, and a healthy price last', () => {
    expect(PRICE_ADVICE_SORT.zero_cost).toBeLessThan(PRICE_ADVICE_SORT.stale);
    expect(PRICE_ADVICE_SORT.stale).toBeLessThan(PRICE_ADVICE_SORT.no_history);
    expect(PRICE_ADVICE_SORT.recent).toBeGreaterThan(PRICE_ADVICE_SORT.no_history);
  });
});
