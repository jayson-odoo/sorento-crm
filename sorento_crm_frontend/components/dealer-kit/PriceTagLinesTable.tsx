'use client';

/**
 * The price tag request's lines table while it is being written: the Item picker, quantity, the
 * line's List price / Promotion / Selling price, remarks, and under each line its Package select,
 * part rows ("Not sure, any of N" for an open group), Add part and the package warning.
 *
 * Shared by the portal's price tag form and the CRM request page (PORTAL-P4-REQUESTS S7b); the
 * behaviour lives in `usePriceTagLineEditor`, which the caller passes in as `editor`. Moved out of
 * `app/(auth)/portal/components/PriceTagRequestForm.tsx` unchanged.
 */

import { Fragment } from 'react';
import { Eye, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { PriceModeToggle } from '@/components/dealer-kit/PriceModeToggle';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { numberFieldError } from '@/lib/number-field';
import { promotionOptionLabel, type LinePricingResult } from '@/lib/dealer-kit/line-pricing-types';
import { comboShape, needsText } from '@/lib/dealer-kit/combo-slots';
import { distinctName, sameDisplayText } from '@/lib/product-display';
import type { LinePartCandidate, PriceMode, ProductComboOption } from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { PriceTagLineEditor } from '@/hooks/usePriceTagLineEditor';
import {
  formatRM,
  hasOpenGroup,
  isOpenPart,
  itemValue,
  linePriceType,
  lineTemplateState,
  type LineTemplateState,
  packageWarningFor,
  comboOfLine,
  partsAtListTitle,
  picksNeeded,
  type DraftLine,
  type DraftPart,
} from '@/lib/dealer-kit/price-tag-draft-lines';

interface PriceTagLinesTableProps {
  lines: DraftLine[];
  priceMode: PriceMode;
  /** Below the mobile breakpoint, List price/Promotion/Selling price stack
   *  under the Item cell instead of living in their own columns (AC-S1-11). */
  isMobile: boolean;
  editor: PriceTagLineEditor;
  /** True once a Save / Submit found a bad number: rows then show their message. */
  showNumberErrors: boolean;
  /** PRICETAG-LPSP: the row's eye icon; the caller owns the lightbox. */
  onPreviewLine?: (key: string) => void;
}

export function PriceTagLinesTable({
  lines,
  priceMode,
  isMobile,
  editor,
  showNumberErrors,
  onPreviewLine,
}: PriceTagLinesTableProps) {
  // PRICETAG-LPSP: LP or SP is per line, so the Promotion / Selling price columns appear as
  // soon as any line is SP, not only under a Selling header.
  const anySelling = lines.some((l) => linePriceType(l, priceMode) === 'selling');
  return (
    <div className="overflow-x-auto">
      {/* `table-fixed` on purpose: a product name can run to sixty
          characters, and with auto layout the Item column swallowed
          the whole width and pushed Qty and the rest off screen.
          Fixed columns let the picker's trigger truncate instead, and
          the min-width keeps every cell usable while the wrapper
          scrolls on a phone, which is the Purchase Request pattern. */}
      <table className="w-full min-w-[560px] table-fixed text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="w-7 px-2 py-2 text-left">#</th>
            <th
              className={
                isMobile
                  ? 'w-[40%] px-2 py-2 text-left'
                  : anySelling
                    ? 'w-[24%] px-2 py-2 text-left'
                    : 'w-[36%] px-2 py-2 text-left'
              }
            >
              Item
            </th>
            <th
              className={
                // The min-width floor belongs on the header cell, not
                // the input: `table-fixed` sizes every column from the
                // FIRST row (this one), so a min-width on the `<td>`'s
                // own Input is never honoured once the column is
                // narrower than it.
                isMobile
                  ? 'w-[13%] min-w-[3.5rem] px-2 py-2 text-left'
                  : anySelling
                    ? 'w-[8%] min-w-[3.5rem] px-2 py-2 text-left'
                    : 'w-[10%] min-w-[3.5rem] px-2 py-2 text-left'
              }
            >
              Qty (tags)
            </th>
            {!isMobile && <th className="w-[9%] min-w-[5rem] px-2 py-2 text-left">Price</th>}
            {!isMobile && (
              <th
                className={anySelling ? 'w-[11%] px-2 py-2 text-left' : 'w-[14%] px-2 py-2 text-left'}
              >
                List price
              </th>
            )}
            {!isMobile && anySelling && (
              <>
                <th className="w-[13%] px-2 py-2 text-left">Promotion</th>
                <th className="w-[11%] px-2 py-2 text-left">Selling price</th>
              </>
            )}
            <th
              className={
                isMobile
                  ? 'w-[35%] px-2 py-2 text-left'
                  : anySelling
                    ? 'w-[12%] px-2 py-2 text-left'
                    : 'w-[20%] px-2 py-2 text-left'
              }
            >
              Remarks
            </th>
            {/* The eye and the trash can: two 28px icons. */}
            <th className="w-[72px] px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => (
            <LineRow
              key={line.key}
              line={line}
              index={index}
              priceMode={priceMode}
              isMobile={isMobile}
              anySelling={anySelling}
              pricing={editor.linePricing[line.key] ?? null}
              fetchItemOptions={editor.fetchItemOptions}
              fetchPartOptions={editor.fetchPartOptions}
              onItemSelect={editor.handleItemSelect}
              onUpdate={editor.updateLine}
              onRemove={editor.removeLine}
              onChoosePackage={editor.choosePackage}
              onChooseTemplate={editor.chooseTemplate}
              onResolvePart={editor.resolvePart}
              onResolvePicks={editor.resolvePicks}
              onRemovePart={editor.removePart}
              onAddPart={editor.addPart}
              onRestoreParts={editor.restoreParts}
              onChoosePromotion={editor.choosePromotion}
              onManualSellPriceChange={editor.setManualSellPrice}
              showNumberErrors={showNumberErrors}
              onPreviewLine={onPreviewLine}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Line row
// ---------------------------------------------------------------------------

interface LineRowProps {
  line: DraftLine;
  index: number;
  priceMode: PriceMode;
  /** Below the mobile breakpoint, List price/Promotion/Selling price stack
   *  under the Item cell instead of living in their own columns (AC-S1-11). */
  isMobile: boolean;
  /** S1/S2: this line's latest `lookupLinePricing` answer, or null before
   *  the first one lands (no product yet, or still in flight). */
  pricing: LinePricingResult | null;
  fetchItemOptions: (query: string) => Promise<SearchableSelectOption[]>;
  fetchPartOptions: (query: string) => Promise<SearchableSelectOption[]>;
  onItemSelect: (key: string, option: SearchableSelectOption | null) => void;
  onUpdate: (key: string, patch: Partial<DraftLine>) => void;
  onRemove: (key: string) => void;
  onChoosePackage: (key: string, comboId: string) => void;
  /** PRICETAG-TEMPLATE-PER-PRODUCT: the Template select on a many-template line. */
  onChooseTemplate: (key: string, templateId: string) => void;
  onResolvePart: (key: string, partKey: string, productId: string) => void;
  onResolvePicks: (key: string, partKey: string, productIds: string[]) => void;
  onRemovePart: (key: string, partKey: string) => void;
  onAddPart: (key: string, option: SearchableSelectOption | null) => void;
  onRestoreParts: (key: string) => void;
  onChoosePromotion: (key: string, promotionId: string) => void;
  onManualSellPriceChange: (key: string, value: number | null) => void;
  /** True once a Save / Submit found a bad number: rows then show their message. */
  showNumberErrors: boolean;
  onPreviewLine?: (key: string) => void;
  /** Any line on the table is SP: the Promotion / Selling price columns exist. */
  anySelling: boolean;
}

/** AC-S2-1: "CODE  RM x" - x is the candidate's LIST price in List mode, or
 *  its price under the line's promotion (offer, else list) in Selling mode
 *  (F1, browser finding) - `pricing.candidates[]` carries both, and reading
 *  `sell_price` unconditionally showed the offer price in List mode too.
 *  Falls back to the bare code while pricing has not answered yet. */
/** Whether the line's chosen template reads any position (fixed part, pick or upgrade). */
function templateUsesPositions(state: LineTemplateState): boolean {
  const needs = (state.kind === 'single' ? state.template : state.kind === 'many' ? state.picked : null)?.needs;
  return !!needs && (needs.fixed > 0 || needs.upgrades > 0 || needs.groups.some((n) => n > 0));
}

function candidateOptionLabel(
  candidate: LinePartCandidate,
  pricing: LinePricingResult | null,
  priceMode: PriceMode,
  upgradeTopup?: { topup: number | string | null | undefined },
): string {
  const code0 = candidate.code || candidate.name;
  // An upgrade is offered at a top-up, never at its list price: the top-up when set,
  // the bare code when blank (the tag prints no amount either).
  if (upgradeTopup) {
    const topup = upgradeTopup.topup;
    return topup == null || topup === '' ? code0 : `${code0}  +${formatRM(Number(topup))}`;
  }
  const price = pricing?.candidates.find((c) => c.product_id === candidate.product_id);
  const code = candidate.code || candidate.name;
  if (!price) return code;
  const amount = priceMode === 'selling' ? price.sell_price : price.list_price;
  return `${code}  ${formatRM(amount)}`;
}

/** An upgrade's top-up from the line's reloaded package lookup (a reopened draft's candidates
 *  carry none). */
function comboTopup(combos: ProductComboOption[], productId: string): number | null {
  for (const combo of combos) {
    const part = combo.parts.find((p) => p.is_upgrade && p.product_id === productId);
    if (part) return part.topup_amount ?? null;
  }
  return null;
}

/** One part row under a line: a fixed or hand-added product, or an open group. */
function PartRow({
  lineKey,
  lineIndex,
  part,
  pricing,
  priceMode,
  combos,
  colSpan,
  picksK,
  onResolvePart,
  onResolvePicks,
  onRemovePart,
}: {
  lineKey: string;
  lineIndex: number;
  part: DraftPart;
  pricing: LinePricingResult | null;
  priceMode: PriceMode;
  combos: ProductComboOption[];
  /** Matches however many real columns the line's own row currently has
   *  (isMobile/priceMode dependent - see `subRowSpan` in `LineRow`). */
  colSpan: number;
  /** How many picks the chosen template reads from this group (2 or more = a multi-select). */
  picksK: number;
  onResolvePart: (key: string, partKey: string, productId: string) => void;
  onResolvePicks: (key: string, partKey: string, productIds: string[]) => void;
  onRemovePart: (key: string, partKey: string) => void;
}) {
  // D17: a group with exactly one candidate resolves on the spot
  // (`partsFromCombo`) and reads like a fixed part - no select, even though
  // `candidates` still carries the one entry. A genuinely open row always
  // has two or more.
  // An upgrade is always a choice, even with one candidate: the dealer may take it or not.
  const choosable =
    part.candidates.length > 1 || (part.role === 'Upgrade' && part.candidates.length > 0);
  const label = part.role || part.code || part.name;
  const discontinued = (candidate: LinePartCandidate) =>
    candidate.is_discontinued ??
    combos.some((combo) =>
      combo.parts.some((p) => p.product_id === candidate.product_id && p.is_discontinued),
    );
  const multi = choosable && picksK >= 2;
  return (
    <tr className="align-top">
      <td colSpan={colSpan} className="px-2 pb-2 pl-9">
        <div className="flex flex-col gap-1.5 border-l-2 border-border pl-3 sm:flex-row sm:items-start sm:gap-2">
          <div className="min-w-0 flex-1">
            {multi ? (
              <SearchableMultiSelect
                value={part.product_ids ?? (part.product_id ? [part.product_id] : [])}
                onChange={(ids) => onResolvePicks(lineKey, part.key, ids)}
                max={picksK}
                options={part.candidates.map((candidate) => ({
                  value: candidate.product_id,
                  label: candidateOptionLabel(candidate, pricing, priceMode),
                  description: distinctName(candidate.code, candidate.name) ?? undefined,
                  disabled: discontinued(candidate),
                  badgeText: discontinued(candidate) ? 'Discontinued' : undefined,
                }))}
                placeholder={`Pick ${picksK}`}
                emptyMessage="No options."
                size="sm"
              />
            ) : choosable ? (
              <div className="space-y-1">
                <SearchableSelect
                  clearable
                  truncateTriggerLabel
                  value={part.product_id ?? ''}
                  onChange={(value) => onResolvePart(lineKey, part.key, value)}
                  options={part.candidates.map((candidate) => ({
                    value: candidate.product_id,
                    label: candidateOptionLabel(
                      candidate,
                      pricing,
                      priceMode,
                      part.role === 'Upgrade'
                        ? { topup: candidate.topup_amount ?? comboTopup(combos, candidate.product_id) }
                        : undefined,
                    ),
                    // Owner, 4 Nov: the code is already the option's first line; a second
                    // line only when the name says something the code does not.
                    description: discontinued(candidate)
                      ? 'Discontinued'
                      : (distinctName(candidate.code, candidate.name) ?? undefined),
                    disabled: discontinued(candidate),
                  }))}
                  placeholder={
                    part.role === 'Upgrade' ? 'No upgrade' : `Not sure, any of ${part.candidates.length}`
                  }
                  emptyMessage="No options."
                  size="sm"
                />
              </div>
            ) : (
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <div className="truncate text-sm" title={part.name || part.code}>
                    {part.name || part.code}
                  </div>
                  {part.is_discontinued ||
                  (part.product_id && discontinued({ product_id: part.product_id, code: part.code, name: part.name })) ? (
                    <Badge variant="warning" appearance="light" size="sm">
                      Discontinued
                    </Badge>
                  ) : null}
                </div>
                {!sameDisplayText(part.code, part.name) ? (
                  <div className="text-xs text-muted-foreground">{part.code || '-'}</div>
                ) : null}
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {part.role ? (
              <span className="text-xs text-muted-foreground">{part.role}</span>
            ) : null}
            {/* No confirm and no countdown: the part row is unsaved form state,
                not a record (the staged-removals rule). */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive"
              onClick={() => onRemovePart(lineKey, part.key)}
              title="Remove part"
              aria-label={`Remove part ${label} from line ${lineIndex + 1}`}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>
      </td>
    </tr>
  );
}

/**
 * One row of the lines table, on the Purchase Request pattern in `SubmissionForm`:
 * a cell per field, a trash button, and horizontal scroll on a narrow screen.
 */
function LineRow({
  line,
  index,
  priceMode,
  isMobile,
  pricing,
  fetchItemOptions,
  fetchPartOptions,
  onItemSelect,
  onUpdate,
  onRemove,
  onChoosePackage,
  onChooseTemplate,
  onResolvePart,
  onResolvePicks,
  onRemovePart,
  onAddPart,
  onRestoreParts,
  onChoosePromotion,
  onManualSellPriceChange,
  showNumberErrors,
  onPreviewLine,
  anySelling,
}: LineRowProps) {
  const templateState = lineTemplateState(line);
  const isSet = line.line_type === 'product_set';
  const warning = packageWarningFor(line);
  // What the chosen template reads from each group, once per part.
  const picksByPart = new Map(line.parts.map((part) => [part.key, picksNeeded(line, part.role)]));
  // Only when there is a choice to make: one combo is applied on pick, and none
  // leaves nothing to select.
  const showPackage = !isSet && line.combos.length > 1;
  // D4 (AC-S2-1..S2-3): "Add part" only once the combos lookup answered AND
  // the product actually has at least one package - nothing to add a part
  // TO otherwise. Existing part rows (a reopened draft) still render with
  // their Remove regardless; this only gates the search below.
  const showParts = !isSet && !!line.product_id && line.combos_loaded && line.combos.length > 0;
  const picked = itemValue(line);
  const selectedItem: SearchableSelectOption | undefined = picked
    ? {
        value: picked,
        label: line.name || line.code,
      }
    : undefined;

  // ---- S1/S2: price cells (product lines only - a set is priced whole,
  // no combo/promotion concept applies to it). ----
  const showPricing = !isSet && !!line.product_id;
  const isSelling = linePriceType(line, priceMode) === 'selling';
  // A product with a finished lookup and no published template has nothing to draw.
  const noTemplate = !isSet && !!line.product_id && templateState.kind === 'none';
  const canPreview = !!(isSet ? line.product_set_id : line.product_id) && !noTemplate;
  const promotionOptions: SearchableSelectOption[] = (pricing?.promotion_options ?? []).map(
    (option) => ({
      value: option.id,
      label: promotionOptionLabel(option),
    }),
  );
  // The last open (unresolved) part row - AC-S2-3's copy sits under it,
  // once per line.
  const lastOpenPartKey = [...line.parts]
    .reverse()
    .find((part) => isOpenPart(part) && (part.candidates.length > 1 || part.role === 'Upgrade'))?.key;

  // Owner ruling after #948: List price / Promotion / Selling price are real
  // `<td>` columns on the line's own row (above the app's 992px mobile
  // breakpoint, useIsMobile), not a `colSpan` sub-row - `subRowSpan` keeps
  // the OTHER sub-rows (guard error, package, parts, warning) spanning the
  // row's actual current column count instead of a stale hard-coded 5.
  // Below the mobile breakpoint the row still has exactly the original 5
  // columns, since the price fields move into the stack nested under the
  // Item cell instead (AC-S1-11) - the two never render at once, so
  // nothing duplicates in the DOM.
  const subRowSpan = isMobile ? 5 : anySelling ? 9 : 7;

  // Owner polish after #948: the desktop `<td>` already sits under a
  // "List price"/"Promotion"/"Selling price" header, so its cell holds only
  // the value/control - the label stays only on the mobile stack, which has
  // no header to read it off. `withLabel` picks between the two; the amount
  // is `whitespace-nowrap` so "RM 1,350" never breaks mid-string, and the
  // "+ option" hint gets its own line rather than fighting it for room.
  const renderTypeCell = () => (
    <PriceModeToggle
      compact
      ariaLabel={`Price type for line ${index + 1}`}
      value={linePriceType(line, priceMode)}
      title={line.price_type ? undefined : 'Follows Preferred Default'}
      onChange={(mode) => onUpdate(line.key, { price_type: mode })}
    />
  );

  const renderListPriceCell = (withLabel: boolean) => (
    <div>
      {withLabel && (
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          List price
        </div>
      )}
      <div className="text-sm font-medium whitespace-nowrap">
        {formatRM(pricing?.list_price)}
      </div>
      {hasOpenGroup(line) ? (
        <div className="text-xs text-muted-foreground">+ option</div>
      ) : null}
    </div>
  );

  const renderPromotionCell = (withLabel: boolean) => (
    <div>
      <Label
        className={
          withLabel
            ? 'text-2xs uppercase tracking-wide text-muted-foreground'
            : 'sr-only'
        }
        htmlFor={`promotion-${line.key}`}
      >
        Promotion
      </Label>
      <SearchableSelect
        id={`promotion-${line.key}`}
        clearable
        truncateTriggerLabel
        value={line.promotion_id ?? ''}
        onChange={(value) => onChoosePromotion(line.key, value)}
        options={promotionOptions}
        placeholder="No covering promotion"
        emptyMessage="No promotion covers this line."
        size="sm"
      />
    </div>
  );

  const renderSellingPriceCell = (withLabel: boolean) => (
    <div>
      {withLabel && (
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          Selling price
        </div>
      )}
      {line.promotion_id ? (
        <div
          className="text-sm font-medium whitespace-nowrap"
          title={partsAtListTitle(line, pricing)}
        >
          {formatRM(pricing?.sell_price)}
        </div>
      ) : (
        <NumberInput
          inputMode="decimal"
          // The server takes `gt=0` with 2 decimal places (`ManualSellPrice`),
          // so 0 is a refusal, not a bound.
          min={0.01}
          step={0.01}
          variant="sm"
          className="w-full max-w-28"
          value={line.manual_sell_price}
          onValueChange={(v) => onManualSellPriceChange(line.key, v)}
          error={
            showNumberErrors
              ? numberFieldError(line.manual_sell_price, { min: 0.01, optional: true })
              : undefined
          }
          // A combo's own price prints without a promotion: show it, not a blank box (AC-2.6).
          placeholder={
            line.combo_id && pricing?.sell_price_basis !== 'list' && pricing?.sell_price != null
              ? formatRM(pricing.sell_price)
              : 'Type a price'
          }
          aria-label={`Selling price for line ${index + 1}`}
        />
      )}
    </div>
  );

  return (
    <>
      <tr className="border-t border-border align-top">
        <td className="px-2 py-2 text-muted-foreground">{index + 1}</td>
        <td className="px-2 py-2">
          <SearchableSelect
            value={picked}
            onChange={() => {
              /* the whole option is what carries the kind; see onOptionChange */
            }}
            onOptionChange={(option) => onItemSelect(line.key, option)}
            fetchOptions={fetchItemOptions}
            selectedOption={selectedItem}
            // The closed cell reads the line's own item, not a picker option's
            // "CODE  RM <price>" text when the picked value is among the options.
            renderTriggerLabel={() => selectedItem?.label}
            clearable
            wrapOptions
            placeholder="Search a set or product..."
            emptyMessage="No sets or products match."
          />
          {noTemplate ? (
            <p className="mt-1 text-xs text-muted-foreground">No tag template yet</p>
          ) : null}
          {/* AC-S1-11: below the app's 992px mobile breakpoint (useIsMobile),
              the same fields stack here instead of living in their own
              columns - never both at once (isMobile picks exactly one), so
              nothing in the row duplicates. */}
          {isMobile && showPricing && (
            <div
              data-testid="line-pricing-stack"
              className="mt-2 flex flex-col gap-2 border-l-2 border-border pl-3 sm:flex-row sm:flex-wrap sm:items-start sm:gap-4"
            >
              <div className="min-w-[90px]">{renderTypeCell()}</div>
              <div className="min-w-[110px]">{renderListPriceCell(true)}</div>
              {isSelling && (
                <>
                  <div className="min-w-[180px] flex-1 sm:max-w-[260px]">
                    {renderPromotionCell(true)}
                  </div>
                  <div className="min-w-[110px]">{renderSellingPriceCell(true)}</div>
                </>
              )}
            </div>
          )}
        </td>
        <td className="px-2 py-2">
          <NumberInput
            inputMode="numeric"
            min={1}
            value={line.quantity}
            onValueChange={(v) => onUpdate(line.key, { quantity: v })}
            error={
              showNumberErrors
                ? numberFieldError(line.quantity, { min: 1, integer: true })
                : undefined
            }
            aria-label={`Quantity for line ${index + 1}`}
          />
        </td>
        {!isMobile && (
          <td className="px-2 py-2">{showPricing ? renderTypeCell() : null}</td>
        )}
        {!isMobile && (
          <td className="px-2 py-2">
            {showPricing ? renderListPriceCell(false) : null}
          </td>
        )}
        {!isMobile && anySelling && (
          <>
            <td className="px-2 py-2">
              {showPricing && isSelling ? renderPromotionCell(false) : null}
            </td>
            <td className="px-2 py-2">
              {showPricing && isSelling ? renderSellingPriceCell(false) : null}
            </td>
          </>
        )}
        <td className="px-2 py-2">
          <Input
            value={line.remarks}
            onChange={(e) => onUpdate(line.key, { remarks: e.target.value })}
            placeholder="Note for this line..."
            aria-label={`Remarks for line ${index + 1}`}
          />
        </td>
        <td className="px-2 py-2">
          <div className="flex items-center justify-end gap-0.5">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={!canPreview}
              onClick={() => onPreviewLine?.(line.key)}
              title="Preview tag"
              aria-label={`Preview tag for line ${index + 1}`}
            >
              <Eye className="size-3.5" />
            </Button>
            {/* No confirm: the row is unsaved form state, not a record. */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive"
              onClick={() => onRemove(line.key)}
              title="Remove line"
              aria-label={`Remove line ${index + 1}`}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </td>
      </tr>
      {line.guard_error && (
        <tr>
          <td colSpan={subRowSpan} className="px-2 pb-2">
            {/* The anchor the form's Submit scrolls to (`scrollToFirstProblem`): a
                row's own refusal, the missing-template one included, sits below
                the fold on a long request (crew browser pass). */}
            <p
              data-error-anchor={`line:${index}`}
              className="sticky left-0 max-w-[calc(100vw-6rem)] rounded bg-destructive/10 px-2 py-1.5 text-xs text-destructive sm:max-w-none"
            >
              {line.guard_error}
            </p>
          </td>
        </tr>
      )}
      {templateState.kind === 'single' && (
        <tr className="align-top">
          <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
            {/* Sticky + capped to the viewport: the table scrolls sideways at
                375px, and a sub-row spanning every column otherwise runs past
                the card's right edge (browser pass). */}
            <p
              className="sticky left-0 max-w-[calc(100vw-9rem)] truncate border-l-2 border-border pl-3 text-xs text-muted-foreground sm:max-w-none"
              title={templateState.template.name}
            >
              Template: {templateState.template.name}
            </p>
          </td>
        </tr>
      )}
      {templateState.kind === 'many' && (
        <tr className="align-top">
          <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
            <div className="sticky left-0 max-w-[calc(100vw-9rem)] border-l-2 border-border pl-3 sm:max-w-none">
              <SearchableSelect
                clearable
                truncateTriggerLabel
                value={line.tag_template_id ?? ''}
                onChange={(value) => onChooseTemplate(line.key, value)}
                options={templateState.options.map((template) => {
                  const size =
                    template.width_mm && template.height_mm
                      ? `${template.width_mm} x ${template.height_mm} mm`
                      : '';
                  // AC-B4: what the template reads, in this combo's own words.
                  const combo = comboOfLine(line);
                  const needs =
                    combo && template.needs ? needsText(template.needs, comboShape(combo.parts)) : '';
                  return {
                    value: template.id,
                    label: template.name,
                    description: [size, needs].filter(Boolean).join('. ') || undefined,
                  };
                })}
                placeholder="Tag template"
                emptyMessage="No templates."
                size="sm"
              />
            </div>
          </td>
        </tr>
      )}
      {showPackage && (
        <tr className="align-top">
          <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
            <div className="border-l-2 border-border pl-3">
              <SearchableSelect
                clearable
                truncateTriggerLabel
                value={line.combo_id ?? ''}
                onChange={(value) => onChoosePackage(line.key, value)}
                options={line.combos.map((combo) => ({
                  value: combo.combo_id,
                  label: combo.name,
                }))}
                placeholder="Package"
                emptyMessage="No packages."
                size="sm"
              />
            </div>
          </td>
        </tr>
      )}
      {line.parts.map((part) => (
        <Fragment key={part.key}>
          <PartRow
            lineKey={line.key}
            lineIndex={index}
            part={part}
            pricing={pricing}
            priceMode={linePriceType(line, priceMode)}
            combos={line.combos.filter((combo) => combo.combo_id === line.combo_id)}
            colSpan={subRowSpan}
            picksK={picksByPart.get(part.key) ?? 0}
            onResolvePart={onResolvePart}
            onResolvePicks={onResolvePicks}
            onRemovePart={onRemovePart}
          />
          {/* AC-C5: how many picks a multi-pick group still lacks. */}
          {(() => {
            const k = picksByPart.get(part.key) ?? 0;
            const held = part.product_ids?.length ?? (part.product_id ? 1 : 0);
            return k >= 2 && part.candidates.length > 1 && held < k ? (
              <tr>
                <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
                  <p className="border-l-2 border-border pl-3 text-xs text-muted-foreground">
                    {`${part.role}: pick ${k - held} more.`}
                  </p>
                </td>
              </tr>
            ) : null;
          })()}
          {/* AC-S2-3: once per line, under the LAST unresolved row. */}
          {part.key === lastOpenPartKey && !templateUsesPositions(templateState) && (
            <tr>
              <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
                <p className="border-l-2 border-border pl-3 text-xs text-muted-foreground">
                  {/* A line with a combo gets one tag listing every option (AC-3.1). */}
                  {line.combo_id
                    ? 'The tag will list every option.'
                    : 'Marketing will prepare one tag per option.'}
                </p>
              </td>
            </tr>
          )}
        </Fragment>
      ))}
      {showParts && (
        <tr className="align-top">
          <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
            <div className="border-l-2 border-border pl-3">
              {/* The shared catalogue search, so a part missing from the package -
                  or on a product that has none - can be named by hand (AC-S2-4).
                  It holds no value of its own: picking adds a row and it returns
                  to its placeholder, so there is nothing to clear. */}
              <SearchableSelect
                value=""
                onChange={() => {
                  /* the whole option carries the code; see onOptionChange */
                }}
                onOptionChange={(option) => onAddPart(line.key, option)}
                fetchOptions={fetchPartOptions}
                wrapOptions
                placeholder="Add part"
                emptyMessage="No products match."
                size="sm"
              />
            </div>
          </td>
        </tr>
      )}
      {warning && (
        <tr>
          <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
            <div className="flex flex-wrap items-center gap-1.5 border-l-2 border-border pl-3">
              <Badge variant="warning" appearance="light" size="sm">
                Package warning
              </Badge>
              <span className="text-xs text-muted-foreground">{warning}</span>
              {/* D19: put back exactly what is named missing above - only
                  while there is a chosen package to restore it FROM. */}
              {line.combo_id && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-2xs"
                  onClick={() => onRestoreParts(line.key)}
                >
                  Restore
                </Button>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
