/**
 * A price tag request's lines while they are being written (PLAN-price-tag-combos D2, line pricing
 * D1-D4): the client-side line and part rows, the package rules, and the payload they save as.
 *
 * Shared by the portal's price tag form and the CRM request page a salesperson edits their own
 * request on (PORTAL-P4-REQUESTS S7b), so both build the same line and send the same payload.
 * Moved out of `app/(auth)/portal/components/PriceTagRequestForm.tsx` unchanged.
 */

import type {
  LinePartCandidate,
  PriceTagLineType,
  PriceTagRequestLineInput,
  ProductComboOption,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { LinePricingResult } from '@/lib/dealer-kit/line-pricing-types';

/**
 * One part row under a draft line (D2).
 *
 * Resolved: `product_id` is set - a specific product goes on the tag. Open:
 * `product_id` is null and `candidates` holds the group's options, which is the
 * salesperson saying "any of these, you choose". `candidates` is kept on a
 * resolved row too, so clearing the select reopens the row (AC-S2-3).
 */
export interface DraftPart {
  key: string;
  product_id: string | null;
  code: string;
  name: string;
  /** The choice group this row answers. Null on a fixed or hand-added part. */
  role: string | null;
  candidates: LinePartCandidate[];
}

export interface DraftLine {
  key: string; // client-side key for React
  line_type: 'product' | 'product_set';
  product_id: string | null;
  product_set_id: string | null;
  name: string;
  code: string;
  /** null while the field is empty; checked on Save / Submit. */
  quantity: number | null;
  included_accessories: string;
  /** Free-text note on the line (D6). */
  remarks: string;
  guard_error: string | null;
  /** The catalogue package this line is asked for as (D2). Null = none chosen. */
  combo_id: string | null;
  /** What the picked product is sold as. Answered by the combos lookup, which
   *  runs once per product on the line - so an empty list before `combos_loaded`
   *  means "not asked yet", not "no package". */
  combos: ProductComboOption[];
  combos_loaded: boolean;
  /** The product's class is in the guarded list, so a missing package is worth
   *  a warning. Answered by the same lookup. */
  host_guarded: boolean;
  parts: DraftPart[];
  // ---- D1/D2/S1: line-level promotion and price (Phase 1, mocked pricing). ----
  /** Null = no promotion chosen (either nothing covers this line yet, or the
   *  salesperson explicitly cleared it - see `promotion_locked`). */
  promotion_id: string | null;
  /** Set the first time the salesperson interacts with the line's Promotion
   *  select (pick OR clear), so the one-time auto pick (AC-S1-4) never
   *  overwrites a deliberate choice, including "none" (AC-S1-7). */
  promotion_locked: boolean;
  /** A hand-typed selling price, only meaningful while `promotion_id` is
   *  null (AC-S1-6). Mutually exclusive with `promotion_id` (AC-S1-7). */
  manual_sell_price: number | null;
  /** The last `lookupLinePricing` answer for this line's key, or null before
   *  the first response lands. */
  pricing: LinePricingResult | null;
}

/**
 * A saved line as the server answers it, read the way `lineToDraft` needs it. The portal's
 * `PriceTagRequestLine` and the Dealer Kit detail line both carry this.
 */
export interface DraftLineSource {
  id: string;
  line_type: PriceTagLineType;
  product_id: string | null;
  product_set_id: string | null;
  name: string;
  code: string;
  quantity: number;
  included_accessories?: string | null;
  remarks?: string | null;
  combo_id?: string | null;
  parts?: Array<{
    id: string;
    product_id: string | null;
    code: string | null;
    name: string | null;
    role: string | null;
    candidates?: LinePartCandidate[] | null;
  }>;
  promotion_id?: string | null;
  manual_sell_price?: number | null;
}

let partKeySeq = 0;
export function newPartKey(): string {
  partKeySeq += 1;
  return `part-${Date.now()}-${partKeySeq}`;
}

/**
 * The part rows a combo fills in on pick (AC-S2-1): every fixed part as its own
 * resolved row, and ONE open row per choice group, in the order the group first
 * appears - so the package reads down the row the way the catalogue page lists it.
 */
export function partsFromCombo(combo: ProductComboOption): DraftPart[] {
  const out: DraftPart[] = [];
  const seen = new Set<string>();
  for (const part of combo.parts) {
    if (!part.choice_group) {
      out.push({
        key: newPartKey(),
        product_id: part.product_id,
        code: part.code,
        name: part.name,
        role: null,
        candidates: [],
      });
      continue;
    }
    if (seen.has(part.choice_group)) continue;
    seen.add(part.choice_group);
    const candidates = combo.parts
      .filter((p) => p.choice_group === part.choice_group)
      .map((p) => ({ product_id: p.product_id, code: p.code, name: p.name }));
    // D17 (AC-S12-1): one candidate is not a choice - the group resolves on
    // the spot, same as a fixed part. `candidates` is kept (not cleared) so
    // the row still knows what it came from if it is ever removed and
    // restored (D19), the same reason a genuinely open row keeps it.
    const only = candidates.length === 1 ? candidates[0] : null;
    out.push({
      key: newPartKey(),
      product_id: only?.product_id ?? null,
      code: only?.code ?? '',
      name: only?.name ?? '',
      role: part.choice_group,
      candidates,
    });
  }
  return out;
}

/**
 * The package warning, computed exactly as the server computes it at submit
 * (D2) so the row says the same thing before and after. Submit is never refused
 * for a package reason - this only tells the salesperson what marketing will see.
 */
export function packageWarningFor(line: DraftLine): string | null {
  if (line.line_type !== 'product' || !line.product_id) return null;
  if (!line.combos_loaded || !line.host_guarded) return null;
  if (!line.combo_id) {
    return line.combos.length === 0 ? 'No package defined' : 'No package chosen';
  }
  const combo = line.combos.find((c) => c.combo_id === line.combo_id);
  if (!combo) return null;
  const missing: string[] = [];
  for (const part of combo.parts) {
    if (part.choice_group) continue;
    if (!line.parts.some((row) => row.product_id === part.product_id)) {
      missing.push(part.code);
    }
  }
  const groups: string[] = [];
  for (const part of combo.parts) {
    if (part.choice_group && !groups.includes(part.choice_group)) {
      groups.push(part.choice_group);
    }
  }
  for (const group of groups) {
    // Neither a resolved nor an open row answers this group.
    if (!line.parts.some((row) => row.role === group)) missing.push(group);
  }
  return missing.length > 0 ? `Missing: ${missing.join(', ')}` : null;
}

/** AC-S1-2: an unresolved choice group prices as nothing, and the List price
 *  cell says so rather than silently under-counting. */
export function hasOpenGroup(line: DraftLine): boolean {
  return line.parts.some((part) => !part.product_id && part.candidates.length > 0);
}

/** RM amounts round to whole ringgit everywhere on this form (mock pricing
 *  never produces sen). */
export function formatRM(value: number | null | undefined): string {
  if (value == null) return '-';
  return `RM ${value.toLocaleString('en-MY')}`;
}

/** AC-S1-8: "the cell's title reads which parts are at list" - the codes a
 *  promotion did not cover, resolved from the line's own part rows (plus the
 *  host itself, which a title never needs to name since the cell it sits in
 *  already says the line is not fully covered by naming what IS missing). */
export function partsAtListTitle(
  line: DraftLine,
  pricing: LinePricingResult | null | undefined,
): string | undefined {
  if (!pricing || pricing.parts_at_list.length === 0) return undefined;
  const codes = pricing.parts_at_list
    .map((productId) => line.parts.find((p) => p.product_id === productId)?.code)
    .filter((code): code is string => !!code);
  return codes.length > 0 ? `At list price: ${codes.join(', ')}` : undefined;
}

/**
 * A new row starts empty and TYPELESS in spirit: the Item picker decides whether
 * it is a product or a set (D47), so the dealer never has to. `product` is only
 * the placeholder until they pick, and an unpicked row blocks Submit either way.
 */
export function emptyDraftLine(): DraftLine {
  return {
    key: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    line_type: 'product',
    product_id: null,
    product_set_id: null,
    name: '',
    code: '',
    quantity: 1,
    included_accessories: '',
    remarks: '',
    guard_error: null,
    combo_id: null,
    combos: [],
    combos_loaded: false,
    host_guarded: false,
    parts: [],
    promotion_id: null,
    promotion_locked: false,
    manual_sell_price: null,
    pricing: null,
  };
}

/** The Item picker's option value: kind and id together, so one dropdown can
 *  answer for two tables without either half guessing which it got. */
export function itemValue(line: DraftLine): string {
  if (line.line_type === 'product_set') {
    return line.product_set_id ? `product_set:${line.product_set_id}` : '';
  }
  return line.product_id ? `product:${line.product_id}` : '';
}

export function lineToDraft(line: DraftLineSource): DraftLine {
  return {
    key: line.id,
    line_type: line.line_type,
    product_id: line.product_id,
    product_set_id: line.product_set_id,
    name: line.name,
    code: line.code,
    // show_promo_price is read-only server state, not form state: it is
    // derived from the header's price_mode on every save (D5), so the draft
    // never carries or resends it (review fix).
    quantity: line.quantity,
    included_accessories: line.included_accessories ?? '',
    remarks: line.remarks ?? '',
    guard_error: null,
    combo_id: line.combo_id ?? null,
    // Not on the line payload: the combos lookup answers both, once per product,
    // from the line editor's effect - which is also what re-arms the Package
    // select and the warning on a draft reopened from the server (AC-S2-9).
    combos: [],
    combos_loaded: false,
    host_guarded: false,
    parts: (line.parts ?? []).map((part) => ({
      key: part.id,
      product_id: part.product_id,
      code: part.code ?? '',
      name: part.name ?? '',
      role: part.role,
      candidates: part.candidates ?? [],
    })),
    // D1 (Phase 2, not wired yet): a server that already carries these wins;
    // a pre-migration server (Phase 1) leaves them null and the line waits
    // for `lookupLinePricing`'s auto pick like a brand new line does.
    promotion_id: line.promotion_id ?? null,
    promotion_locked: line.promotion_id != null,
    manual_sell_price: line.manual_sell_price ?? null,
    pricing: null,
  };
}

/** AC-S2-8. `alternatives` is gone; `combo_id` and the part rows go in its
 *  place, in display order. A resolved part sends its product, an open one
 *  sends the candidate ids it is still choosing between. */
export function draftLinesPayload(lines: DraftLine[]): PriceTagRequestLineInput[] {
  return lines.map((l) => ({
    line_type: l.line_type,
    product_id: l.product_id,
    product_set_id: l.product_set_id,
    combo_id: l.combo_id,
    quantity: l.quantity as number,
    included_accessories: l.included_accessories || null,
    remarks: l.remarks || null,
    product_class: null,
    parts: l.parts.map((part) => ({
      product_id: part.product_id,
      role: part.role,
      candidates: part.product_id
        ? []
        : part.candidates.map((candidate) => candidate.product_id),
    })),
    // D1/D2 (S6): the line's own price basis - built here for create,
    // update AND revise, the one function all three send through, so the
    // server never sees a line missing what `choosePromotion`/
    // `setManualSellPrice` already set on it.
    promotion_id: l.promotion_id,
    manual_sell_price: l.manual_sell_price,
  }));
}
