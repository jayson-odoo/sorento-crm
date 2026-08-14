/**
 * ============================================================================
 * SCM M5 Part A - SEMANTIC-LAYER MOCK STORE  (Phase 1 only)
 * ============================================================================
 * Synthetic-but-realistic mocks for the LLM narrator that sits ON TOP of the
 * frozen deterministic recommendation: a one-sentence explanation, a bounded
 * Q&A answerer, and an optional market advisory. It exists ONLY so the Phase-1
 * prototype can demonstrate the explanation + Ask + advisory UX inside the
 * "How this recommendation was reached" dialog WITHOUT any backend / LLM.
 *
 * Phase 2 flips `USE_M5_MOCKS` to false in `services/explainerService.ts`; the
 * same three operations then hit the real endpoints documented there. This file
 * is deleted at that point.
 *
 * Two hard rules mirrored from the real contract (they define the feature):
 *   1. Every number spoken here is READ from the frozen recommendation - nothing
 *      is recomputed and no figure is invented.
 *   2. When a question needs a number the recommendation doesn't carry, the
 *      answer is EXACTLY `REFUSAL` - never a fabricated value.
 *
 * Deterministic by construction: no `Math.random`, no `Date.now`. The advisory
 * fires for ~half the SKUs, chosen by a stable hash of the SKU (so the same row
 * always shows / hides the same signal across reloads).
 * ============================================================================
 */
import { EM_DASH, fmtInt, fmtMoney } from '../../lib/format';
import type { ReorderRecommendation } from '../types/reorder.types';

/** Phase-1 flag - mirrors `USE_SLICE_B_MOCKS`. Phase 2: wired to the real
 *  explainer endpoints (GET explanation / POST ask / GET advisory). */
export const USE_M5_MOCKS = false;

/** The one and only answer when a question can't be grounded in the rec's data.
 *  Kept as a shared constant so the UI can style the refusal turn distinctly and
 *  Phase-2 tests can assert on the exact bytes. */
export const REFUSAL = "I can't compute that from this recommendation's data.";

/** Compact decimal - trims trailing zeros so 11.0 reads "11" (matches the dialog's `dec`). */
function dec(v: number | null | undefined): string {
  if (v === null || v === undefined) return EM_DASH;
  return Number(v.toFixed(2)).toLocaleString('en-MY', { maximumFractionDigits: 2 });
}

/** Stable non-negative hash of a string - drives the deterministic advisory gate. */
function skuHash(sku: string): number {
  let h = 0;
  for (let i = 0; i < sku.length; i += 1) {
    h = (h * 31 + sku.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

const PRODUCT_SUFFIX = (rec: ReorderRecommendation) =>
  rec.product_name ? ` (${rec.product_name})` : '';

// ── 1) Explanation ───────────────────────────────────────────────────────────

/** The trigger noun + the frozen level it fired against, per policy type. */
function triggerContext(rec: ReorderRecommendation): { noun: string; level: number | null } {
  if (rec.policy_type === 'min_max') return { noun: 'minimum level', level: rec.min_qty };
  if (rec.policy_type === 'periodic_review')
    return { noun: 'order-up-to target', level: rec.order_up_to };
  return { noun: 'reorder point', level: rec.reorder_point };
}

/**
 * One generated-sounding sentence built ENTIRELY from the rec's frozen numbers.
 * Deliberately phrased differently from the deterministic headline (`summaryText`
 * in the dialog) so it reads as narrated prose, not the same asserted line - but
 * it speaks only figures the engine already stored.
 */
export function mockExplanation(rec: ReorderRecommendation): string {
  const name = PRODUCT_SUFFIX(rec);

  if (rec.type === 'exception') {
    return `${rec.sku}${name} has crossed its reorder threshold (net position ${dec(
      rec.net_position,
    )}), but no supplier is linked to source it - link one before this can become a purchase order.`;
  }

  const { noun, level } = triggerContext(rec);
  const qty = rec.order_qty != null ? `${fmtInt(rec.order_qty)} units` : 'a replenishment';
  const coverClause =
    rec.days_of_cover != null
      ? ` and at about ${dec(rec.forecast_daily_demand)} units/day that leaves roughly ${fmtInt(
          rec.days_of_cover,
        )} days of cover`
      : '';
  const cashClause = rec.cash_impact != null ? `, tying up about ${fmtMoney(rec.cash_impact)}` : '';

  return `You should order ${qty} of ${rec.sku}${name}: its net position of ${dec(
    rec.net_position,
  )} has dropped to or below the ${noun} of ${dec(level)}${coverClause}${cashClause}.`;
}

// ── 2) Bounded Q&A ───────────────────────────────────────────────────────────

/** Question fragments that ask for a figure the frozen rec never carries → refuse. */
const OUT_OF_SCOPE = [
  'profit',
  'margin',
  'revenue',
  'competitor',
  'discount',
  'tax',
  'next year',
  'forecast next',
  'weather',
  'exchange rate',
];

/**
 * Bounded answerer over the rec's frozen fields. Recognised intents map to the
 * matching stored number; anything out-of-scope, or an intent whose field is
 * null (uncosted / not derivable), returns the exact `REFUSAL` - a mock LLM that
 * NEVER fabricates a figure it wasn't given.
 */
export function mockAsk(rec: ReorderRecommendation, question: string): string {
  const q = question.toLowerCase();

  if (OUT_OF_SCOPE.some((t) => q.includes(t))) return REFUSAL;

  // Answer helper: a null frozen field is unanswerable → refuse (never a fake 0).
  const answerNum = (value: number | null | undefined, sentence: (v: string) => string): string =>
    value === null || value === undefined ? REFUSAL : sentence(dec(value));

  if (q.includes('lead time') || q.includes('leadtime')) {
    return answerNum(
      rec.lead_time_days,
      (v) => `The lead time used is ${v} days${rec.lead_time_source ? ` (${rec.lead_time_source})` : ''}.`,
    );
  }
  if (q.includes('safety')) {
    return answerNum(rec.safety_stock, (v) => `The safety stock baked in is ${v} units.`);
  }
  if (q.includes('reorder point') || q.includes(' rop') || q.startsWith('rop')) {
    return answerNum(rec.reorder_point, (v) => `The reorder point is ${v}.`);
  }
  if (q.includes('stockout') || q.includes('run out') || q.includes('stock out')) {
    return answerNum(rec.days_to_stockout, (v) => `At the forecast demand this SKU stocks out in about ${v} days.`);
  }
  if (q.includes('cover') || (q.includes('days') && !q.includes('lead'))) {
    return answerNum(
      rec.days_of_cover,
      (v) => `The net position gives about ${v} days of cover at the forecast demand.`,
    );
  }
  if (q.includes('demand') || q.includes('usage') || q.includes('per day') || q.includes('/day')) {
    return answerNum(rec.forecast_daily_demand, (v) => `Forecast demand is about ${v} units/day.`);
  }
  if (q.includes('unit cost')) {
    return answerNum(rec.unit_cost, () => `The landed unit cost is ${fmtMoney(rec.unit_cost)}.`);
  }
  if (q.includes('cost') || q.includes('cash') || q.includes('spend') || q.includes('how much')) {
    return answerNum(rec.cash_impact, () => `This buy ties up about ${fmtMoney(rec.cash_impact)}.`);
  }
  if (q.includes('net') || q.includes('position')) {
    return answerNum(rec.net_position, (v) => `The net position is ${v} (on hand + on order − committed).`);
  }
  if (q.includes('supplier') || q.includes('who')) {
    return rec.supplier
      ? `The chosen supplier is ${rec.supplier.supplier_name}.`
      : 'No supplier is linked to this SKU yet, so it cannot be sourced.';
  }
  if (q.includes('rank') || q.includes('priority')) {
    return rec.rank != null ? `This buy is ranked #${rec.rank} for funding.` : REFUSAL;
  }
  if (q.includes('confidence')) {
    return rec.confidence
      ? `Confidence is ${rec.confidence} (based on a sample of ${fmtInt(rec.sample_size)}).`
      : REFUSAL;
  }
  if (
    q.includes('how many') ||
    q.includes('quantity') ||
    q.includes('qty') ||
    q.includes('order') ||
    q.includes('units')
  ) {
    return answerNum(rec.order_qty, () => `The recommended order quantity is ${fmtInt(rec.order_qty)} units.`);
  }

  // Unrecognised intent → refuse rather than guess.
  return REFUSAL;
}

// ── 3) Market advisory ───────────────────────────────────────────────────────

/** Synthetic market signals. In Phase 2 these come from a real market-research
 *  lookup keyed to the SKU's category; here we round-robin by SKU hash. */
const ADVISORY_TEMPLATES = [
  'Ceramic-tile prices are trending +8% on FX moves; consider ordering sooner to lock in current pricing.',
  'Freight rates on this supplier’s lane have eased ~5% this month - timing favours a larger consolidated order.',
  'Raw-material costs for this category are forecast to rise next quarter; front-loading this buy may hedge the increase.',
  'Regional demand for this line is picking up ahead of the festive season - a slightly deeper buy lowers stockout risk.',
  'A key supplier in this category has flagged capacity constraints; ordering earlier protects the lead time.',
];

/**
 * A market advisory for ~half the SKUs (even hash), null for the rest - so the
 * prototype exercises BOTH the "signal present" callout and the "no signal"
 * (line hidden) state. Deterministic per SKU.
 */
export function mockAdvisory(rec: ReorderRecommendation): string | null {
  const h = skuHash(rec.sku);
  if (h % 2 !== 0) return null;
  return ADVISORY_TEMPLATES[h % ADVISORY_TEMPLATES.length];
}
