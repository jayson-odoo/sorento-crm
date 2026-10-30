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
import { Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { numberFieldError } from '@/lib/number-field';
import { promotionOptionName, type LinePricingResult } from '@/lib/dealer-kit/line-pricing-types';
import { distinctName, sameDisplayText } from '@/lib/product-display';
import type { LinePartCandidate, PriceMode } from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { PriceTagLineEditor } from '@/hooks/usePriceTagLineEditor';
import {
  formatRM,
  hasOpenGroup,
  itemValue,
  packageWarningFor,
  partsAtListTitle,
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
}

export function PriceTagLinesTable({ lines, priceMode, isMobile, editor, showNumberErrors }: PriceTagLinesTableProps) {
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
                  ? 'w-[46%] px-2 py-2 text-left'
                  : priceMode === 'selling'
                    ? 'w-[31%] px-2 py-2 text-left'
                    : 'w-[43%] px-2 py-2 text-left'
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
                  ? 'w-[12%] min-w-[3.5rem] px-2 py-2 text-left'
                  : priceMode === 'selling'
                    ? 'w-[9%] min-w-[3.5rem] px-2 py-2 text-left'
                    : 'w-[12%] min-w-[3.5rem] px-2 py-2 text-left'
              }
            >
              Qty (tags)
            </th>
            {!isMobile && (
              <th
                className={
                  priceMode === 'selling'
                    ? 'w-[13%] px-2 py-2 text-left'
                    : 'w-[14%] px-2 py-2 text-left'
                }
              >
                List price
              </th>
            )}
            {!isMobile && priceMode === 'selling' && (
              <>
                <th className="w-[14%] px-2 py-2 text-left">Promotion</th>
                <th className="w-[12%] px-2 py-2 text-left">Selling price</th>
              </>
            )}
            <th
              className={
                isMobile
                  ? 'w-[35%] px-2 py-2 text-left'
                  : priceMode === 'selling'
                    ? 'w-[14%] px-2 py-2 text-left'
                    : 'w-[24%] px-2 py-2 text-left'
              }
            >
              Remarks
            </th>
            {/* One 28px icon, not a fifth of the row. */}
            <th className="w-[7%] px-2 py-2"></th>
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
              pricing={editor.linePricing[line.key] ?? null}
              fetchItemOptions={editor.fetchItemOptions}
              fetchPartOptions={editor.fetchPartOptions}
              onItemSelect={editor.handleItemSelect}
              onUpdate={editor.updateLine}
              onRemove={editor.removeLine}
              onChoosePackage={editor.choosePackage}
              onResolvePart={editor.resolvePart}
              onRemovePart={editor.removePart}
              onAddPart={editor.addPart}
              onRestoreParts={editor.restoreParts}
              onChoosePromotion={editor.choosePromotion}
              onManualSellPriceChange={editor.setManualSellPrice}
              showNumberErrors={showNumberErrors}
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
  onResolvePart: (key: string, partKey: string, productId: string) => void;
  onRemovePart: (key: string, partKey: string) => void;
  onAddPart: (key: string, option: SearchableSelectOption | null) => void;
  onRestoreParts: (key: string) => void;
  onChoosePromotion: (key: string, promotionId: string) => void;
  onManualSellPriceChange: (key: string, value: number | null) => void;
  /** True once a Save / Submit found a bad number: rows then show their message. */
  showNumberErrors: boolean;
}

/** AC-S2-1: "CODE  RM x" - x is the candidate's LIST price in List mode, or
 *  its price under the line's promotion (offer, else list) in Selling mode
 *  (F1, browser finding) - `pricing.candidates[]` carries both, and reading
 *  `sell_price` unconditionally showed the offer price in List mode too.
 *  Falls back to the bare code while pricing has not answered yet. */
function candidateOptionLabel(
  candidate: LinePartCandidate,
  pricing: LinePricingResult | null,
  priceMode: PriceMode,
): string {
  const price = pricing?.candidates.find((c) => c.product_id === candidate.product_id);
  const code = candidate.code || candidate.name;
  if (!price) return code;
  const amount = priceMode === 'selling' ? price.sell_price : price.list_price;
  return `${code}  ${formatRM(amount)}`;
}

/** One part row under a line: a fixed or hand-added product, or an open group. */
function PartRow({
  lineKey,
  lineIndex,
  part,
  pricing,
  priceMode,
  colSpan,
  onResolvePart,
  onRemovePart,
}: {
  lineKey: string;
  lineIndex: number;
  part: DraftPart;
  pricing: LinePricingResult | null;
  priceMode: PriceMode;
  /** Matches however many real columns the line's own row currently has
   *  (isMobile/priceMode dependent - see `subRowSpan` in `LineRow`). */
  colSpan: number;
  onResolvePart: (key: string, partKey: string, productId: string) => void;
  onRemovePart: (key: string, partKey: string) => void;
}) {
  // D17: a group with exactly one candidate resolves on the spot
  // (`partsFromCombo`) and reads like a fixed part - no select, even though
  // `candidates` still carries the one entry. A genuinely open row always
  // has two or more.
  const choosable = part.candidates.length > 1;
  const label = part.role || part.code || part.name;
  return (
    <tr className="align-top">
      <td colSpan={colSpan} className="px-2 pb-2 pl-9">
        <div className="flex flex-col gap-1.5 border-l-2 border-border pl-3 sm:flex-row sm:items-start sm:gap-2">
          <div className="min-w-0 flex-1">
            {choosable ? (
              <div className="space-y-1">
                <SearchableSelect
                  clearable
                  truncateTriggerLabel
                  value={part.product_id ?? ''}
                  onChange={(value) => onResolvePart(lineKey, part.key, value)}
                  options={part.candidates.map((candidate) => ({
                    value: candidate.product_id,
                    label: candidateOptionLabel(candidate, pricing, priceMode),
                    description: candidate.code,
                  }))}
                  placeholder={`Not sure, any of ${part.candidates.length}`}
                  emptyMessage="No options."
                  size="sm"
                />
              </div>
            ) : (
              <div className="min-w-0">
                <div className="truncate text-sm" title={part.name || part.code}>
                  {part.name || part.code}
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
  onResolvePart,
  onRemovePart,
  onAddPart,
  onRestoreParts,
  onChoosePromotion,
  onManualSellPriceChange,
  showNumberErrors,
}: LineRowProps) {
  const isSet = line.line_type === 'product_set';
  const warning = packageWarningFor(line);
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
        description: distinctName(line.code, line.name)
          ? `${isSet ? 'Set' : 'Product'}${line.code ? ` - ${line.code}` : ''}`
          : isSet
            ? 'Set'
            : 'Product',
      }
    : undefined;

  // ---- S1/S2: price cells (product lines only - a set is priced whole,
  // no combo/promotion concept applies to it). ----
  const showPricing = !isSet && !!line.product_id;
  const promotionOptions: SearchableSelectOption[] = (pricing?.promotion_options ?? []).map(
    (option) => ({
      value: option.id,
      label: `${promotionOptionName(option)} - ${formatRM(option.sell_price)}`,
    }),
  );
  // The last open (unresolved) part row - AC-S2-3's copy sits under it,
  // once per line.
  const lastOpenPartKey = [...line.parts]
    .reverse()
    .find((part) => !part.product_id && part.candidates.length > 1)?.key;

  // Owner ruling after #948: List price / Promotion / Selling price are real
  // `<td>` columns on the line's own row (above the app's 992px mobile
  // breakpoint, useIsMobile), not a `colSpan` sub-row - `subRowSpan` keeps
  // the OTHER sub-rows (guard error, package, parts, warning) spanning the
  // row's actual current column count instead of a stale hard-coded 5.
  // Below the mobile breakpoint the row still has exactly the original 5
  // columns, since the price fields move into the stack nested under the
  // Item cell instead (AC-S1-11) - the two never render at once, so
  // nothing duplicates in the DOM.
  const subRowSpan = isMobile ? 5 : priceMode === 'selling' ? 8 : 6;

  // Owner polish after #948: the desktop `<td>` already sits under a
  // "List price"/"Promotion"/"Selling price" header, so its cell holds only
  // the value/control - the label stays only on the mobile stack, which has
  // no header to read it off. `withLabel` picks between the two; the amount
  // is `whitespace-nowrap` so "RM 1,350" never breaks mid-string, and the
  // "+ option" hint gets its own line rather than fighting it for room.
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
          placeholder="Type a price"
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
            clearable
            wrapOptions
            placeholder="Search a set or product..."
            emptyMessage="No sets or products match."
          />
          {/* AC-S1-11: below the app's 992px mobile breakpoint (useIsMobile),
              the same fields stack here instead of living in their own
              columns - never both at once (isMobile picks exactly one), so
              nothing in the row duplicates. */}
          {isMobile && showPricing && (
            <div
              data-testid="line-pricing-stack"
              className="mt-2 flex flex-col gap-2 border-l-2 border-border pl-3 sm:flex-row sm:flex-wrap sm:items-start sm:gap-4"
            >
              <div className="min-w-[110px]">{renderListPriceCell(true)}</div>
              {priceMode === 'selling' && (
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
          <td className="px-2 py-2">
            {showPricing ? renderListPriceCell(false) : null}
          </td>
        )}
        {!isMobile && priceMode === 'selling' && (
          <>
            <td className="px-2 py-2">
              {showPricing ? renderPromotionCell(false) : null}
            </td>
            <td className="px-2 py-2">
              {showPricing ? renderSellingPriceCell(false) : null}
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
            <p className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1.5">
              {line.guard_error}
            </p>
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
            priceMode={priceMode}
            colSpan={subRowSpan}
            onResolvePart={onResolvePart}
            onRemovePart={onRemovePart}
          />
          {/* AC-S2-3: once per line, under the LAST unresolved row. */}
          {part.key === lastOpenPartKey && (
            <tr>
              <td colSpan={subRowSpan} className="px-2 pb-2 pl-9">
                <p className="border-l-2 border-border pl-3 text-xs text-muted-foreground">
                  Marketing will prepare one tag per option.
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
