import { describe, expect, it } from 'vitest';
import {
  clampForecastQty,
  forecastAddOn,
  forecastQtyCap,
  lineBreachStatus,
  roundBuyQty,
  roundOrderQty,
} from './orderQtyLedger';
import type { TrajectoryEntry } from './trajectory';

/**
 * Pure-math coverage for the two order-qty-ledger follow-ups (user feedback, 2026-08-12):
 *
 *  - `lineBreachStatus`: a covered row above its own line must never read a bogus
 *    "Gap to line" figure.
 *  - `forecastAddOn`: the forecast add-on's horizon must name its source, and follow the
 *    SAME trajectory verdict as the row's own Trend pill.
 */

const trend = (over: Partial<TrajectoryEntry> = {}): TrajectoryEntry => ({
  verdict: 'rising',
  recent_qty: 120,
  previous_qty: 90,
  change_pct: 33.33,
  year_ago_qty: null,
  year_change_pct: null,
  window_months: 12,
  months: [],
  customers: [],
  agents: [],
  agents_available: false,
  ...over,
});

describe('roundOrderQty - byte-for-byte parity with reorder_engine.round_order_qty (Fix 6, 2026-08-12)', () => {
  it('a plain qty with no MOQ or multiple passes through unchanged', () => {
    expect(roundOrderQty(23, null, null)).toBe(23);
    expect(roundOrderQty(23, undefined, undefined)).toBe(23);
  });

  it('floors up to the MOQ when below it', () => {
    expect(roundOrderQty(20, 50, null)).toBe(50);
  });

  it('leaves qty alone when it already meets or exceeds the MOQ', () => {
    expect(roundOrderQty(50, 50, null)).toBe(50);
    expect(roundOrderQty(80, 50, null)).toBe(80);
  });

  it('rounds UP to the nearest order multiple', () => {
    expect(roundOrderQty(23, null, 10)).toBe(30);
    expect(roundOrderQty(20, null, 10)).toBe(20); // already exact
  });

  it('applies the MOQ floor THEN the multiple, matching the backend\'s order', () => {
    // 20 -> floored to 50 (MOQ) -> rounded up to 60 (nearest multiple of 12).
    expect(roundOrderQty(20, 50, 12)).toBe(60);
  });

  it('a qty of 0 with NO moq/multiple stays 0', () => {
    expect(roundOrderQty(0, null, null)).toBe(0);
  });

  it('a qty of 0 with a POSITIVE moq set floors UP to the moq - the backend does not ' +
    'special-case zero, and neither may this function (the caller decides "nothing to ' +
    'buy" before calling this, exactly as reorder_engine.order_qty does)', () => {
    expect(roundOrderQty(0, 5, null)).toBe(5);
  });

  it('moq of 0 is a real config value (`moq is not None`, not `moq > 0`, on the backend) - ' +
    'it participates in the comparison but never raises a positive qty', () => {
    expect(roundOrderQty(23, 0, null)).toBe(23); // 23 is already >= 0, moq is a no-op here
    expect(roundOrderQty(0, 0, null)).toBe(0);
  });

  it('moq null/undefined is skipped entirely, same as order_multiple null/undefined', () => {
    expect(roundOrderQty(5, null, null)).toBe(5);
    expect(roundOrderQty(5, undefined, undefined)).toBe(5);
  });

  it('order_multiple of 0 or negative is a no-op (falsy on the backend\'s own ' +
    '`order_multiple and order_multiple > 0` check)', () => {
    expect(roundOrderQty(23, null, 0)).toBe(23);
  });

  it('multiple rounding steps in one call: MOQ floor + multiple, several fixtures', () => {
    expect(roundOrderQty(1, 100, 25)).toBe(100); // floors to 100, already a multiple of 25
    expect(roundOrderQty(110, 100, 25)).toBe(125); // above MOQ, rounds up to next multiple
    expect(roundOrderQty(164, null, 1)).toBe(164); // multiple of 1 is always a no-op
  });
});

/**
 * The ONE rounding every recorded buy goes through, whichever control typed it (review
 * finding 1, round 2): the ledger rounded and the Accept / Adjust paths did not, so the SAME
 * row recorded 14 or 20 depending on where the buyer clicked.
 */
describe('roundBuyQty - one rounding rule for every recorded buy', () => {
  it('rounds the remainder up to the order multiple', () => {
    expect(roundBuyQty(14, { moq: null, order_multiple: 10 })).toBe(20);
  });

  it('floors to the MoQ, and takes both rules in the engine order', () => {
    expect(roundBuyQty(14, { moq: 50, order_multiple: 12 })).toBe(60);
  });

  it('a buy of nothing stays nothing, so a MoQ can never invent an order', () => {
    // `reorder_engine.order_qty` returns 0 BEFORE it rounds, for exactly this reason.
    expect(roundBuyQty(0, { moq: 100, order_multiple: 25 })).toBe(0);
    expect(roundBuyQty(-4, { moq: 100, order_multiple: 25 })).toBe(0);
  });

  it('passes a legal figure through untouched', () => {
    expect(roundBuyQty(20, { moq: null, order_multiple: 10 })).toBe(20);
    expect(roundBuyQty(23, { moq: null, order_multiple: null })).toBe(23);
  });
});

describe('lineBreachStatus', () => {
  it('manual mode: net above the level reads as not breached', () => {
    const status = lineBreachStatus(
      { policy_type: 'reorder_level', reorder_level: 120 },
      135,
    );
    expect(status).toEqual({ breached: false, basisLabel: 'level', basisValue: 120 });
  });

  it('manual mode: net at or below the level reads as breached (the real-gap case)', () => {
    expect(lineBreachStatus({ policy_type: 'reorder_level', reorder_level: 120 }, 120).breached).toBe(true);
    expect(lineBreachStatus({ policy_type: 'reorder_level', reorder_level: 120 }, 90).breached).toBe(true);
  });

  it('manual mode falls back to the AutoCount master level when no buyer level is set', () => {
    const status = lineBreachStatus(
      { policy_type: 'reorder_level', reorder_level: null, master_reorder_level: 100 },
      150,
    );
    expect(status).toEqual({ breached: false, basisLabel: 'level', basisValue: 100 });
  });

  it('auto mode: net above the reorder point reads as not breached', () => {
    const status = lineBreachStatus({ policy_type: 'reorder_point', reorder_point: 74 }, 100);
    expect(status).toEqual({ breached: false, basisLabel: 'reorder point', basisValue: 74 });
  });

  it('auto mode: net at or below the reorder point still reads as breached', () => {
    expect(lineBreachStatus({ policy_type: 'reorder_point', reorder_point: 74 }, 74).breached).toBe(true);
  });

  it('with no basis on file, reads breached rather than asserting a status it cannot support', () => {
    expect(lineBreachStatus({ policy_type: 'reorder_point', reorder_point: null }, 100)).toEqual({
      breached: true,
      basisLabel: null,
      basisValue: null,
    });
  });

  it('with no net figure at all, reads breached', () => {
    expect(
      lineBreachStatus({ policy_type: 'reorder_level', reorder_level: 120 }, null).breached,
    ).toBe(true);
  });
});

describe('forecastAddOn - names its source', () => {
  it('manual mode: the horizon comes from the level suggestion cover-months', () => {
    const addOn = forecastAddOn({
      policy_type: 'reorder_level',
      forecast_daily_demand: 20,
      suggestion_basis: { cover_months: 2 },
    });
    expect(addOn).toMatchObject({
      qty: 1200,
      horizonDays: 60,
      ratePerDay: 20,
      sourceLabel: 'cover window per policy',
      trendNote: null,
    });
  });

  it('auto mode: the horizon comes from the policy review window', () => {
    const addOn = forecastAddOn({
      policy_type: 'reorder_point',
      forecast_daily_demand: 20,
      review_days: 30,
    });
    expect(addOn).toMatchObject({
      qty: 600,
      horizonDays: 30,
      ratePerDay: 20,
      sourceLabel: 'review period per policy',
      trendNote: null,
    });
  });

  it('no measurable demand -> no add-on at all (not even a zeroed one)', () => {
    expect(forecastAddOn({ policy_type: 'reorder_point', forecast_daily_demand: null, review_days: 30 })).toBeNull();
    expect(forecastAddOn({ policy_type: 'reorder_point', forecast_daily_demand: 0, review_days: 30 })).toBeNull();
  });
});

describe('forecastAddOn - trend-aware (Fix3)', () => {
  const base = { policy_type: 'reorder_point' as const, forecast_daily_demand: 20, review_days: 30 };
  // flat = 20 * 30 = 600

  it('rising: bumps the flat proposal up by the SAME %-of-buy math as the row advisory', () => {
    const addOn = forecastAddOn(base, trend({ verdict: 'rising', change_pct: 33.33 }));
    // 33.33% of 600 = 199.98 -> ceil 200 -> 800
    expect(addOn).toMatchObject({ qty: 800, trendNote: 'orders rising +33%' });
  });

  it('falling: reduces proportionally by change_pct, floored at 0', () => {
    const addOn = forecastAddOn(base, trend({ verdict: 'falling', change_pct: -25 }));
    // 25% of 600 = 150 -> 600 - 150 = 450
    expect(addOn).toMatchObject({ qty: 450, trendNote: 'orders falling -25%' });
  });

  it('falling hard enough to fully consume the add-on floors at 0, never negative', () => {
    const addOn = forecastAddOn(base, trend({ verdict: 'falling', change_pct: -100 }));
    expect(addOn).toMatchObject({ qty: 0, trendNote: 'orders falling -100%' });
  });

  it('holding, quiet, and no_history all leave the flat proposal unchanged', () => {
    for (const verdict of ['holding', 'quiet', 'no_history'] as const) {
      const addOn = forecastAddOn(base, trend({ verdict }));
      expect(addOn).toMatchObject({ qty: 600, trendNote: null });
    }
  });

  it('no trend data at all leaves the flat proposal unchanged', () => {
    expect(forecastAddOn(base, undefined)).toMatchObject({ qty: 600, trendNote: null });
  });
});

describe('forecastQtyCap and clampForecastQty (Fix A, user feedback, 2026-08-12)', () => {
  it('caps at 10x the proposal', () => {
    expect(forecastQtyCap(60)).toBe(600);
    expect(forecastQtyCap(1200)).toBe(12000);
  });

  it('falls back to a flat sane ceiling when there is no proposal to scale', () => {
    expect(forecastQtyCap(0)).toBe(99_999);
  });

  it('clamps a typed quantity to the cap', () => {
    expect(clampForecastQty(1500, forecastQtyCap(60))).toBe(600);
    expect(clampForecastQty(500, forecastQtyCap(60))).toBe(500);
  });

  it('floors a negative or non-finite entry at zero', () => {
    expect(clampForecastQty(-5, 600)).toBe(0);
    expect(clampForecastQty(Number.NaN, 600)).toBe(0);
  });

  it('rounds a fractional entry to the nearest integer', () => {
    expect(clampForecastQty(59.6, 600)).toBe(60);
  });
});
