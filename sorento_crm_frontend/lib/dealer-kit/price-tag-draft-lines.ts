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
  PriceMode,
  PriceTagLineType,
  PriceTagRequestLineInput,
  ProductComboOption,
  ProductTagTemplateOption,
  VariantMemberOption,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
import { formatTagPrice } from '@/lib/dealer-kit/price-badge';
import { comboShape, fitReason, groupIndexOf } from '@/lib/dealer-kit/combo-slots';
import type { LinePricingResult } from '@/lib/dealer-kit/line-pricing-types';
import { defaultOptionFor, fittingOptions, lineTypeLabel, templateFitsLine } from '@/lib/dealer-kit/template-price-type';

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
  /** Ordered picks for a group the chosen template needs 2 or more from (K5). */
  product_ids?: string[];
  /** The part's product is discontinued (a fixed part cannot be swapped, AC-C6). */
  is_discontinued?: boolean;
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
  // ---- PRICETAG-TEMPLATE-PER-PRODUCT ----
  /** The salesperson's template pick, or the product's single link. Null = none. */
  tag_template_id?: string | null;
  /** The product's published templates, answered once per product. */
  tag_templates?: ProductTagTemplateOption[];
  /** Which product `tag_templates` was answered for; anything else = not asked yet. */
  tag_templates_for?: string | null;
  /** PRICETAG-LPSP: which combo `tag_templates` was answered for (null = none). */
  tag_templates_combo?: string | null;
  /** PRICETAG-LPSP: this line's own LP or SP. Absent = the header's mode. */
  price_type?: PriceMode | null;
  /** R13: the template and LP/SP a LOADED line was saved with. While both are unchanged the
   *  template is kept (AC-37): no "No SP template linked" pill, eye enabled, no Submit reason. */
  kept_template?: { id: string; price_type: PriceMode } | null;
  // ---- PRICETAG-UPGRADE-VARIANTS ----
  /** The product's variant members, answered once per product. Absent = not asked yet. */
  variant_members?: VariantMemberOption[];
  /** Which product `variant_members` was answered for. */
  variant_members_for?: string | null;
  /** The line product's own list price, for the "Variants price differently" warning. */
  own_list_price?: number | null;
  /** The members UNTICKED for this tag; a member added later joins ticked. */
  excluded_variant_ids?: string[];
}

/** The combo the line is asked for as, once the combos lookup has answered. */
export function comboOfLine(line: Pick<DraftLine, 'combo_id' | 'combos'>): ProductComboOption | undefined {
  return line.combo_id ? line.combos.find((c) => c.combo_id === line.combo_id) : undefined;
}

/** The line's effective LP/SP: its own, else the request's mode. */
export function linePriceType(line: Pick<DraftLine, 'price_type'>, priceMode: PriceMode): PriceMode {
  return line.price_type ?? priceMode;
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
  tag_template_id?: string | null;
  price_type?: PriceMode | null;
  excluded_variant_ids?: string[] | null;
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
    if (part.is_upgrade) continue;
    if (!part.choice_group) {
      out.push({
        key: newPartKey(),
        product_id: part.product_id,
        code: part.code,
        name: part.name,
        role: null,
        candidates: [],
        is_discontinued: part.is_discontinued ?? false,
      });
      continue;
    }
    if (seen.has(part.choice_group)) continue;
    seen.add(part.choice_group);
    const candidates = combo.parts
      .filter((p) => !p.is_upgrade && p.choice_group === part.choice_group)
      .map((p) => ({
        product_id: p.product_id,
        code: p.code,
        name: p.name,
        is_discontinued: p.is_discontinued ?? false,
      }));
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
  // AC-3.5: upgrades are offered, never included. One open `Upgrade` row, even with a
  // single candidate (no D17 auto-resolve), so an unanswered upgrade adds nothing.
  const upgrades = combo.parts.filter((p) => p.is_upgrade);
  if (upgrades.length > 0) {
    out.push({
      key: newPartKey(),
      product_id: null,
      code: '',
      name: '',
      role: 'Upgrade',
      candidates: upgrades.map((p) => ({
        product_id: p.product_id,
        code: p.code,
        name: p.name,
        topup_amount: p.topup_amount ?? null,
      })),
    });
  }
  return out;
}

/** Whether a line row is the one the combo row `row` describes: a group or the upgrade by role, a fixed part by product. */
function isSameComboRow(held: DraftPart, row: DraftPart): boolean {
  return row.role ? held.role === row.role : !held.role && held.product_id === row.product_id;
}

/**
 * The combo's own rows the line does not hold (P2), each with a stable id and the label the Add
 * part select shows: a choice group or "Upgrade" by name, a fixed part by code. The rows are the
 * ones `partsFromCombo` builds, in combo order.
 */
export function missingComboRows(line: DraftLine): { id: string; label: string; row: DraftPart }[] {
  const combo = comboOfLine(line);
  if (!combo) return [];
  return partsFromCombo(combo)
    .filter((row) => !line.parts.some((held) => isSameComboRow(held, row)))
    .map((row) => ({
      id: row.role ? `role:${row.role}` : `part:${row.product_id}`,
      label: row.role ?? row.code,
      row,
    }));
}

/** The line's parts with the missing combo row `id` back at its combo position (an a la carte part stays after). */
export function insertComboRow(line: DraftLine, id: string): DraftPart[] {
  const combo = comboOfLine(line);
  const missing = missingComboRows(line).find((m) => m.id === id);
  if (!combo || !missing) return line.parts;
  const order = partsFromCombo(combo);
  const placeOf = (part: DraftPart) => {
    const at = order.findIndex((row) => isSameComboRow(part, row));
    return at < 0 ? Infinity : at;
  };
  const mine = order.findIndex((row) => isSameComboRow(missing.row, row));
  const before = line.parts.findIndex((held) => placeOf(held) > mine);
  const parts = [...line.parts];
  parts.splice(before < 0 ? parts.length : before, 0, missing.row);
  return parts;
}

/**
 * The package warning, computed exactly as the server computes it at submit
 * (D2) so the row says the same thing before and after. Submit is never refused
 * for a package reason - this only tells the salesperson what marketing will see.
 */
export function packageWarningFor(line: DraftLine): string | null {
  if (line.line_type !== 'product' || !line.product_id) return null;
  if (!line.combos_loaded) return null;
  if (!line.combo_id) {
    // Whether a package is expected at all is the server's call (guarded families only).
    if (!line.host_guarded) return null;
    return line.combos.length === 0 ? 'No package defined' : 'No package chosen';
  }
  // A chosen package says what it holds, on any host: removing a part of it is always worth a note.
  const combo = comboOfLine(line);
  if (!combo) return null;
  const missing: string[] = [];
  for (const part of combo.parts) {
    if (part.choice_group || part.is_upgrade) continue;
    if (!line.parts.some((row) => row.product_id === part.product_id)) {
      missing.push(part.code);
    }
  }
  const groups: string[] = [];
  for (const part of combo.parts) {
    if (part.is_upgrade) continue;
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
  return line.parts.some((part) => isOpenPart(part) && part.candidates.length > 0);
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
    excluded_variant_ids: [],
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

/** Two or more resolved parts sharing a role are one multi-pick row, where the first sat. */
function foldPicks(parts: DraftPart[]): DraftPart[] {
  const out: DraftPart[] = [];
  for (const part of parts) {
    const same = part.role && part.product_id ? out.find((p) => p.role === part.role && p.product_id !== null) : undefined;
    if (!same) {
      out.push(part);
      continue;
    }
    same.product_ids = [...(same.product_ids ?? [same.product_id as string]), part.product_id as string];
  }
  return out;
}

/**
 * A reopened multi-pick row has no candidates (the server stores the picks only). Once the combos
 * lookup answers, give it back its group's options, the same source `partsFromCombo` uses, so it
 * renders as the multi-select it was.
 */
export function restoreGroupCandidates(parts: DraftPart[], combo: ProductComboOption | undefined): DraftPart[] {
  if (!combo) return parts;
  return parts.map((part) => {
    if (!part.role || part.candidates.length > 0 || (part.product_ids?.length ?? 0) < 2) return part;
    const candidates = combo.parts
      .filter((p) => !p.is_upgrade && p.choice_group === part.role)
      .map((p) => ({ product_id: p.product_id, code: p.code, name: p.name, is_discontinued: p.is_discontinued ?? false }));
    return candidates.length > 0 ? { ...part, candidates } : part;
  });
}

export function lineToDraft(line: DraftLineSource, requestMode?: PriceMode): DraftLine {
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
    parts: foldPicks(
      (line.parts ?? []).map((part) => ({
        key: part.id,
        product_id: part.product_id,
        code: part.code ?? '',
        name: part.name ?? '',
        role: part.role,
        candidates: part.candidates ?? [],
      })),
    ),
    // D1 (Phase 2, not wired yet): a server that already carries these wins;
    // a pre-migration server (Phase 1) leaves them null and the line waits
    // for `lookupLinePricing`'s auto pick like a brand new line does.
    promotion_id: line.promotion_id ?? null,
    promotion_locked: line.promotion_id != null,
    manual_sell_price: line.manual_sell_price ?? null,
    pricing: null,
    // The templates lookup answers the options once the line is on screen.
    tag_template_id: line.tag_template_id ?? null,
    kept_template:
      line.tag_template_id && (line.price_type ?? requestMode)
        ? { id: line.tag_template_id, price_type: (line.price_type ?? requestMode) as PriceMode }
        : null,
    tag_templates: [],
    tag_templates_for: null,
    // The server stores an explicit type on every line, so a line whose type equals the
    // request's mode is read as FOLLOWING Preferred Default (price_type null); only a line that
    // differs keeps its own.
    price_type: line.price_type && line.price_type !== requestMode ? line.price_type : null,
    // The members lookup answers `variant_members` once the line is on screen.
    excluded_variant_ids: line.excluded_variant_ids ?? [],
  };
}

/**
 * PRICETAG-TEMPLATE-PER-PRODUCT: the Template field's state for a line.
 * `none` = no field (no published link, or a set line), `single` = shown as
 * text, `many` = the salesperson picks; `loading` until the lookup answered
 * for this line's current product.
 */
export type LineTemplateState =
  | { kind: 'none' }
  | { kind: 'loading' }
  | { kind: 'single'; template: ProductTagTemplateOption }
  | { kind: 'many'; options: ProductTagTemplateOption[]; picked: ProductTagTemplateOption | null }
  /** The item has links, but none fits this line's LP / SP: "No SP template linked". */
  | { kind: 'mismatch'; priceType: 'list' | 'selling' };

function comboShapeOf(line: DraftLine) {
  const combo = comboOfLine(line);
  return combo ? comboShape(combo.parts) : null;
}

export function lineTemplateState(line: DraftLine, priceMode?: PriceMode | null): LineTemplateState {
  if (line.line_type !== 'product' || !line.product_id) return { kind: 'none' };
  if (
    line.tag_templates_for !== line.product_id ||
    (line.tag_templates_combo ?? null) !== (line.combo_id ?? null)
  ) {
    return { kind: 'loading' };
  }
  // AC-B4: only templates that fit the line's combo are offered.
  const shape = comboShapeOf(line);
  const options = (line.tag_templates ?? []).filter(
    (t) => !shape || !t.needs || fitReason(t.needs, shape) === null,
  );
  if (options.length === 0) return { kind: 'none' };
  // PRICETAG-COMBO-FORMAT: only the templates that fit the line's LP / SP are offered.
  const lineType = line.price_type ?? priceMode ?? null;
  let fitting = fittingOptions(options, lineType);
  // R6 (AC-37): a loaded line keeps the template it was saved with even when it stopped fitting;
  // it shows by name and is re-sent. Only a user change (pick or LP/SP flip) re-filters.
  const saved = options.find((o) => o.id === line.tag_template_id);
  if (saved && !fitting.includes(saved)) fitting = [...fitting, saved];
  if (fitting.length === 0) return { kind: 'mismatch', priceType: lineType as 'list' | 'selling' };
  if (fitting.length === 1) return { kind: 'single', template: fitting[0] };
  return {
    kind: 'many',
    options: fitting,
    picked: fitting.find((o) => o.id === line.tag_template_id) ?? null,
  };
}

/**
 * The line's type when the item has linked templates but none fits it ("No SP template linked").
 * Unlike `lineTemplateState` this ignores a kept saved pick (R6): the saved template still shows
 * and prints, but the gap is still worth saying.
 */
export function unfittedPriceType(line: DraftLine, priceMode?: PriceMode | null): 'list' | 'selling' | null {
  if (line.line_type !== 'product' || !line.product_id) return null;
  if (
    line.tag_templates_for !== line.product_id ||
    (line.tag_templates_combo ?? null) !== (line.combo_id ?? null)
  ) {
    return null;
  }
  const shape = comboShapeOf(line);
  const options = (line.tag_templates ?? []).filter(
    (t) => !shape || !t.needs || fitReason(t.needs, shape) === null,
  );
  const lineType = line.price_type ?? priceMode ?? null;
  if (options.length === 0 || !lineType) return null;
  // R13: a loaded line still holding its saved template and type raises nothing.
  const kept = line.kept_template;
  if (kept && kept.id === line.tag_template_id && kept.price_type === lineType) return null;
  return fittingOptions(options, lineType).length === 0 ? lineType : null;
}

/** "SRTBF11416: No SP template linked" (a combo line is named by the combo). */
export function noTemplateForTypeMessage(line: DraftLine, priceType: 'list' | 'selling'): string {
  const label = comboOfLine(line)?.name || line.code || line.name;
  return `${label}: No ${lineTypeLabel(priceType)} template linked`;
}

/** The Submit-time check (AC-10, client side): a many-template line needs a pick. */
export const EMPTY_LINE = 'Pick a set or a product for this line.';

export const MISSING_TAG_TEMPLATE = 'Pick a tag template for this line.';

export function lineNeedsTemplate(line: DraftLine, priceMode?: PriceMode | null): boolean {
  const state = lineTemplateState(line, priceMode);
  return state.kind === 'many' && state.picked === null;
}

/** The parts as the server takes them: a multi-pick row becomes one resolved part per pick, in order. */
export function partsPayload(parts: DraftPart[]) {
  return parts.flatMap((part) =>
    part.product_ids && part.product_ids.length > 0
      ? part.product_ids.map((product_id) => ({ product_id, role: part.role, candidates: [] as string[] }))
      : [
          {
            product_id: part.product_id,
            role: part.role,
            candidates: part.product_id ? [] : part.candidates.map((candidate) => candidate.product_id),
          },
        ],
  );
}

/**
 * The note after a save that dropped a line's promotion: the server drops one a narrowed pick no
 * longer touches (PRICETAG-DISCONTINUED-PICK, it prices nothing there). Null when none was dropped.
 */
export function droppedPromotionNote(
  sent: Array<{ promotion_id?: string | null }>,
  saved: Array<{ promotion_id?: string | null; sort_order: number }> | undefined,
): string | null {
  if (!saved) return null;
  const ordered = [...saved].sort((a, b) => a.sort_order - b.sort_order);
  const lines = sent.flatMap((line, index) =>
    line.promotion_id && ordered[index] && !ordered[index].promotion_id ? [index + 1] : [],
  );
  if (lines.length === 0) return null;
  return `Promotion removed from ${lines.length === 1 ? 'line' : 'lines'} ${lines.join(', ')}: it does not cover the option picked.`;
}

/** Every product the parts have resolved so far, picks included. */
export function pickedProductIds(parts: DraftPart[]): string[] {
  return parts.flatMap((p) => (p.product_ids?.length ? p.product_ids : p.product_id ? [p.product_id] : []));
}

/** A row is still open while nothing is picked from it. */
export function isOpenPart(part: DraftPart): boolean {
  return !part.product_id && !part.product_ids?.length;
}

/** AC-S2-8. `alternatives` is gone; `combo_id` and the part rows go in its
 *  place, in display order. A resolved part sends its product, an open one
 *  sends the candidate ids it is still choosing between. */
export function draftLinesPayload(
  lines: DraftLine[],
  priceMode?: PriceMode,
): PriceTagRequestLineInput[] {
  return lines.map((l) => ({
    line_type: l.line_type,
    product_id: l.product_id,
    product_set_id: l.product_set_id,
    combo_id: l.combo_id,
    quantity: l.quantity as number,
    included_accessories: l.included_accessories || null,
    remarks: l.remarks || null,
    product_class: null,
    parts: partsPayload(l.parts),
    // D1/D2 (S6): the line's own price basis - built here for create,
    // update AND revise, the one function all three send through, so the
    // server never sees a line missing what `choosePromotion`/
    // `setManualSellPrice` already set on it.
    promotion_id: l.promotion_id,
    // PRICETAG-LPSP: a typed price only means something on an SP line with no promotion; the
    // server refuses it anywhere else.
    // An untyped line follows Preferred Default: it is saved with the header's value now.
    price_type: l.price_type ?? priceMode ?? null,
    manual_sell_price:
      (l.price_type ?? priceMode) === 'list' || l.promotion_id ? null : l.manual_sell_price,
    tag_template_id: l.line_type === 'product' ? (l.tag_template_id ?? null) : null,
    excluded_variant_ids: l.line_type === 'product' ? (l.excluded_variant_ids ?? []) : [],
  }));
}

/**
 * PRICETAG-UPGRADE-VARIANTS: the line once the members lookup answered for `productId`. An unticked
 * id that is no longer a member (re-parented or re-coded since it was unticked) is dropped, so it
 * can never block a save with NOT_A_VARIANT; the chooser could not show it to clear it.
 */
export function withVariantMembers(
  line: DraftLine,
  productId: string,
  answer: { members?: VariantMemberOption[] | null; own_list_price?: number | null } | null | undefined,
): DraftLine {
  // An answer without a list (an older server, a stand-in) reads as no members, and says nothing
  // about the saved unticked ids, so they are left as they were.
  const known = Array.isArray(answer?.members);
  const members = known ? (answer?.members as VariantMemberOption[]) : [];
  const current = new Set(members.map((m) => m.product_id));
  return {
    ...line,
    variant_members: members,
    variant_members_for: productId,
    own_list_price: answer?.own_list_price ?? null,
    excluded_variant_ids: known
      ? (line.excluded_variant_ids ?? []).filter((id) => current.has(id))
      : (line.excluded_variant_ids ?? []),
  };
}

/** PRICETAG-UPGRADE-VARIANTS Q5: "Variants price differently: RM x to RM y" over the line product
 *  and its ticked live members, or null when they all list the same (or nothing is known). */
export function variantPriceWarning(
  line: Pick<DraftLine, 'variant_members' | 'own_list_price' | 'excluded_variant_ids'>,
): string | null {
  const unticked = new Set(line.excluded_variant_ids ?? []);
  const prices = [
    line.own_list_price,
    ...(line.variant_members ?? [])
      .filter((m) => !m.is_discontinued && !unticked.has(m.product_id))
      .map((m) => m.list_price),
  ].filter((price): price is number => price != null);
  if (prices.length < 2) return null;
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  return low === high ? null : `Variants price differently: ${formatTagPrice(low)} to ${formatTagPrice(high)}`;
}

/** The template the line prints with: its pick, or the lone link. Null when not decided. */
function chosenTemplate(line: DraftLine, priceMode?: PriceMode | null): ProductTagTemplateOption | null {
  const state = lineTemplateState(line, priceMode);
  if (state.kind === 'single') return state.template;
  return state.kind === 'many' ? state.picked : null;
}

/** How many picks the chosen template reads from this part's group (0 when it reads none). */
export function picksNeeded(line: DraftLine, role: string | null, priceMode?: PriceMode | null): number {
  const needs = chosenTemplate(line, priceMode)?.needs;
  const combo = comboOfLine(line);
  if (!needs || !combo || !role) return 0;
  const index = groupIndexOf(role, comboShape(combo.parts));
  return index < 0 ? 0 : (needs.groups[index] ?? 0);
}

/** AC-C4: a template that needs fewer keeps the first picks; one pick goes back to a plain row. */
export function trimPicksToTemplate(line: DraftLine): DraftLine {
  return {
    ...line,
    parts: line.parts.map((part) => {
      if (!part.product_ids || part.product_ids.length === 0) return part;
      const keep = Math.max(picksNeeded(line, part.role), 1);
      if (part.product_ids.length <= keep && keep >= 2) return part;
      const ids = part.product_ids.slice(0, keep);
      if (ids.length >= 2) return { ...part, product_ids: ids };
      const rest = { ...part };
      delete rest.product_ids;
      const chosen = part.candidates.find((c) => c.product_id === ids[0]);
      return { ...rest, product_id: ids[0], code: chosen?.code ?? part.code, name: chosen?.name ?? part.name };
    }),
  };
}

type PricingByKey = Record<
  string,
  Partial<Pick<LinePricingResult, 'list_price' | 'sell_price'>> | null | undefined
>;

/**
 * The facts that block Approve for one line (AC-C5, AC-C6, AC-D2), worded as facts only: nothing
 * here tells the user what to do. Shown on the line when Approve is clicked, not before.
 */
export function lineProblemsOf(
  line: DraftLine,
  pricing: PricingByKey[string],
  priceMode: PriceMode = 'list',
): string[] {
  const out: string[] = [];
  const combo = comboOfLine(line);
  const templateState = lineTemplateState(line, priceMode);
  const unfitted = unfittedPriceType(line, priceMode);
  if (unfitted) out.push(noTemplateForTypeMessage(line, unfitted));
  const needs = chosenTemplate(line, priceMode)?.needs;
  const heldPicks = (role: string) =>
    line.parts
      .filter((part) => part.role === role)
      .reduce((n, part) => n + (part.product_ids?.length ?? (part.product_id ? 1 : 0)), 0);
  // N1: what the chosen template reads, not the rows present: a deleted group row still owes its picks.
  if (needs && combo) {
    const shape = comboShape(combo.parts);
    shape.groups.forEach((group, index) => {
      const k = needs.groups[index] ?? 0;
      if (k > 0 && !line.parts.some((part) => part.role === group.role) && heldPicks(group.role) < k) {
        out.push(`${group.role}: pick ${k - heldPicks(group.role)} more.`);
      }
    });
    const fixedParts = combo.parts.filter((p) => !p.is_upgrade && !p.choice_group);
    for (let i = 0; i < Math.min(needs.fixed, fixedParts.length); i += 1) {
      if (!line.parts.some((part) => part.product_id === fixedParts[i].product_id)) {
        out.push(`Template needs ${fixedParts[i].code}.`);
      }
    }
  }
  for (const part of line.parts) {
    const picked = part.product_ids?.length ? part.product_ids : part.product_id ? [part.product_id] : [];
    const k = picksNeeded(line, part.role, priceMode);
    if (k >= 2 && picked.length < k) out.push(`${part.role}: pick ${k - picked.length} more.`);
    // Owner, 7 Nov: a discontinued product never stops Approve, picked or fixed. Its row's
    // "Discontinued" badge is the warning.
  }
  if (line.combo_id && pricing) {
    if (linePriceType(line, priceMode) === 'list') {
      if (pricing.list_price == null) out.push('No combo list price.');
    } else if (pricing.sell_price === null && line.manual_sell_price == null) {
      // An SP line prints the stored or option price, else the typed one, else nothing (AC-D3).
      out.push('No combo selling price.');
    }
  }
  return out;
}

/** `lineProblemsOf` for every line, flattened in line order. */
export function linePickProblems(
  lines: DraftLine[],
  pricingByKey: PricingByKey,
  priceMode: PriceMode = 'list',
): string[] {
  return lines.flatMap((line) => lineProblemsOf(line, pricingByKey[line.key], priceMode));
}

/** The messages the Approve click writes on a line; a server refusal is none of these. */
function isCheckMessage(message: string): boolean {
  return (
    message === EMPTY_LINE ||
    message === MISSING_TAG_TEMPLATE ||
    message === 'No tag template yet.' ||
    message.startsWith('Template needs ') ||
    /^No combo (list|selling) price\.$/.test(message) ||
    /: pick \d+ more\.$/.test(message) ||
    / template linked$/.test(message)
  );
}

/**
 * A line's click-time message with the facts that no longer hold taken out (A): `holding` is what
 * is wrong with the line right now. It only removes; a new problem waits for the next click.
 */
export function pruneGuardError(guardError: string | null, holding: string[]): string | null {
  if (!guardError) return null;
  const kept = guardError.split('\n').filter((message) => !isCheckMessage(message) || holding.includes(message));
  return kept.length > 0 ? kept.join('\n') : null;
}

/**
 * What flipping a line to `mode` does to its template: a pick that still fits is kept (nothing
 * changes); otherwise it moves to that type's default, or is cleared when the item has none.
 */
export function templateAfterFlip(line: DraftLine, mode: PriceMode): { tag_template_id?: string | null } {
  const options = line.tag_templates ?? [];
  if (options.length === 0) return {};
  const current = options.find((option) => option.id === line.tag_template_id);
  if (current && templateFitsLine(current.price_type, mode)) return {};
  return { tag_template_id: defaultOptionFor(options, mode)?.id ?? null };
}
