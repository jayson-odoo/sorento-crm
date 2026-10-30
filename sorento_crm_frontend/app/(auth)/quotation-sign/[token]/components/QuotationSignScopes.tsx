'use client';

import * as React from 'react';
import { Trash2, Undo2 } from 'lucide-react';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
// The one decimal-exact money formatter in the repo. Imported rather than re-implemented: a
// second formatter is how the public page and the PDF end up disagreeing by a cent, and the
// customer reading this screen is the person who would notice.
import {
  compareMoney,
  formatMyrExact,
  formatQty,
  multiplyMoney,
} from '@/app/(protected)/project-sales/_shared/lib/money';
import type {
  QuotationSignAmendment,
  QuotationSignAmendmentRow,
  QuotationSignLine,
  QuotationSignScope,
} from '../../services/quotationSignService';
import {
  editOf,
  editedAmount,
  priceError,
  priceIsEditable,
  quantityError,
  type LineEdit,
  type LineEdits,
} from './quotationSuggest';

/** The sample workbook's column set, minus the product image. */
const COLUMNS = 9;

/** Suggest mode: Qty and Unit rate become inputs, and one narrow column holds Remove / Restore. */
export type QuotationSignSuggest = {
  edits: LineEdits;
  onEdit: (line: QuotationSignLine, patch: Partial<LineEdit>) => void;
  onToggleRemove: (line: QuotationSignLine) => void;
  disabled?: boolean;
};

/** The suggestions already sent, by line and field, shown in the cells they concern. */
type Answers = Map<string, QuotationSignAmendmentRow>;

function answersOf(amendment: QuotationSignAmendment | null | undefined): Answers {
  const map: Answers = new Map();
  (amendment?.rows ?? []).forEach((row) => map.set(`${row.line_id}:${row.field}`, row));
  return map;
}

/**
 * One sent suggestion in its cell. While open: the issued value struck through above the
 * suggested one. Once answered: the value that now stands, and Accepted or Not accepted with the
 * reason. A request closed by a newer revision says it was not applied.
 */
function SentValue({
  row,
  status,
  issued,
  format,
}: {
  row: QuotationSignAmendmentRow;
  status: QuotationSignAmendment['status'];
  issued: string;
  format: (value: string) => string;
}) {
  const suggested = row.value_to ? format(row.value_to) : '-';
  if (status === 'open') {
    return (
      <span className="flex flex-col items-end">
        <s className="text-xs text-muted-foreground">{format(issued)}</s>
        <span className="font-medium">{suggested}</span>
      </span>
    );
  }
  if (status === 'superseded') {
    return (
      <span className="flex flex-col items-end gap-0.5">
        <span>{format(issued)}</span>
        <Badge variant="secondary" appearance="light" size="sm">
          Not applied
        </Badge>
      </span>
    );
  }
  const accepted = row.decision === 'accepted';
  return (
    <span className="flex flex-col items-end gap-0.5">
      <span>{accepted ? suggested : format(issued)}</span>
      <Badge variant={accepted ? 'success' : 'secondary'} appearance="light" size="sm">
        {accepted ? 'Accepted' : 'Not accepted'}
      </Badge>
      {!accepted && row.decision_reason && (
        <span className="max-w-[160px] whitespace-normal break-words text-xs text-muted-foreground">
          {`"${row.decision_reason}"`}
        </span>
      )}
    </span>
  );
}

/**
 * What a line comes to once its suggestions were answered: the accepted quantity and price, the
 * issued value for a side not accepted. Null when nothing on the line was accepted (or the
 * request is not answered yet), so the issued amount stands.
 */
function answeredAmount(
  line: QuotationSignLine,
  answers: Answers,
  amendment: QuotationSignAmendment | null | undefined,
): string | null {
  if (amendment?.status !== 'applied' || line.is_rate_only) return null;
  const accepted = (field: string) => {
    const row = answers.get(`${line.id}:${field}`);
    return row && row.decision === 'accepted' ? row.value_to : null;
  };
  const quantity = accepted('quantity');
  const price = accepted('unit_price');
  if (quantity === null && price === null) return null;
  return multiplyMoney(quantity ?? line.quantity, price ?? line.unit_price);
}

function RemovalAnswer({
  row,
  status,
}: {
  row: QuotationSignAmendmentRow;
  status: QuotationSignAmendment['status'];
}) {
  const [variant, words] =
    status === 'open'
      ? (['warning', 'Removal suggested'] as const)
      : status === 'superseded'
        ? (['secondary', 'Not applied'] as const)
        : row.decision === 'accepted'
          ? (['success', 'Removal accepted'] as const)
          : (['secondary', 'Removal not accepted'] as const);
  return (
    <span className="flex flex-col items-end gap-0.5">
      <Badge variant={variant} appearance="light" size="sm">
        {words}
      </Badge>
      {status === 'applied' && row.decision === 'rejected' && row.decision_reason && (
        <span className="max-w-[160px] whitespace-normal break-words text-xs text-muted-foreground">
          {`"${row.decision_reason}"`}
        </span>
      )}
    </span>
  );
}

function text(value: string | null | undefined): string {
  return value?.trim() ? value : '-';
}

/**
 * Money on a line, where zero means "no separate charge" and the cell stays empty.
 *
 * Quotations list the parts of a complete set on their own rows, priced at nothing because the
 * money is already on the parent item. `RM 0.00` on those rows tells the customer they are
 * getting four free products, and this page is the one they are signing. Same rule as the PDF and
 * the workbook, deliberately: the three have to agree.
 */
function lineMoney(value: string | null | undefined): string {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) && amount === 0 ? '' : formatMyrExact(value ?? '0');
}

/**
 * The amount column for ONE line.
 *
 * A rate-only line prints the WORDS rather than a blank, because it is a different fact: not "no
 * separate charge" but "quoted at this rate, and not added into the total" (AC-C2 / AC-D3).
 */
function LineAmount({ line }: { line: QuotationSignLine }) {
  if (line.is_rate_only) {
    return <span className="italic text-muted-foreground">rate only</span>;
  }
  return <span className="tabular-nums">{lineMoney(line.amount)}</span>;
}

function ScopeTable({
  lines,
  suggest,
  amendment,
}: {
  lines: QuotationSignLine[];
  suggest?: QuotationSignSuggest;
  amendment?: QuotationSignAmendment | null;
}) {
  const answers = React.useMemo(() => answersOf(amendment), [amendment]);
  const columns = suggest ? COLUMNS + 1 : COLUMNS;
  // A band label heads its section ONCE, above the line that opens it. Repeating it on every row
  // is how the printed quotation stops being readable.
  let currentBand: string | null = null;

  return (
    // Hand-rolled and read-only on purpose: this is a printed quotation being read by a stranger
    // on a phone, with nothing to sort, page or select, so DataGrid's toolbar and pagination
    // would be furniture in the way. `overflow-x-auto` + `min-w-0` keep the wide table scrolling
    // inside its own gutter instead of dragging the whole PAGE sideways at 375px.
    // `relative` so the sr-only header label (position: absolute) is clipped by this scroller
    // instead of escaping it and widening the whole page at 375px.
    <div data-testid="quotation-sign-scroller" className="relative min-w-0 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="min-w-[140px] px-2 py-2 text-left font-semibold">Item</th>
            <th className="min-w-[160px] px-2 py-2 text-left font-semibold">Technical spec</th>
            <th className="min-w-[200px] px-2 py-2 text-left font-semibold">Description</th>
            <th className="min-w-[100px] px-2 py-2 text-left font-semibold">Brand</th>
            <th className="min-w-[120px] px-2 py-2 text-left font-semibold">Product code</th>
            <th className="min-w-[70px] px-2 py-2 text-right font-semibold">Qty</th>
            <th className="min-w-[120px] px-2 py-2 text-right font-semibold">Unit rate</th>
            <th className="min-w-[140px] px-2 py-2 text-left font-semibold">Complete set</th>
            <th className="min-w-[120px] px-2 py-2 text-right font-semibold">Amount</th>
            {suggest && (
              <th className="w-10 px-1 py-2">
                <span className="sr-only">Remove</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => {
            const band = line.band_label?.trim() ? line.band_label.trim() : null;
            const opensBand = band !== null && band !== currentBand;
            if (opensBand) currentBand = band;
            return (
              <React.Fragment key={index}>
                {opensBand && (
                  <tr className="bg-muted/60">
                    <td
                      colSpan={columns}
                      className="px-2 py-2 text-xs font-semibold uppercase tracking-wide"
                    >
                      {band}
                    </td>
                  </tr>
                )}
                {suggest ? (
                  <SuggestRow line={line} position={index} suggest={suggest} />
                ) : (
                  <tr className="border-t border-border align-top">
                    <td className="px-2 py-2">{text(line.item_label)}</td>
                    <td className="px-2 py-2 text-muted-foreground">{text(line.technical_spec)}</td>
                    <td className="px-2 py-2">{text(line.description)}</td>
                    <td className="px-2 py-2">{text(line.brand)}</td>
                    <td className="px-2 py-2">{text(line.product_code)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">
                      {amendment && answers.get(`${line.id}:quantity`) ? (
                        <SentValue
                          row={answers.get(`${line.id}:quantity`)!}
                          status={amendment.status}
                          issued={line.quantity}
                          format={formatQty}
                        />
                      ) : (
                        formatQty(line.quantity)
                      )}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">
                      {amendment && answers.get(`${line.id}:unit_price`) ? (
                        <SentValue
                          row={answers.get(`${line.id}:unit_price`)!}
                          status={amendment.status}
                          issued={line.unit_price}
                          format={formatMyrExact}
                        />
                      ) : (
                        lineMoney(line.unit_price)
                      )}
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">{text(line.complete_set)}</td>
                    <td className="px-2 py-2 text-right">
                      {amendment && answers.get(`${line.id}:remove`) ? (
                        <span className="flex flex-col items-end gap-0.5">
                          {/* An accepted removal leaves no amount; any other keeps the issued one. */}
                          {!(
                            amendment.status === 'applied' &&
                            answers.get(`${line.id}:remove`)!.decision === 'accepted'
                          ) && <LineAmount line={line} />}
                          <RemovalAnswer
                            row={answers.get(`${line.id}:remove`)!}
                            status={amendment.status}
                          />
                        </span>
                      ) : answeredAmount(line, answers, amendment) !== null ? (
                        <span className="tabular-nums">
                          {lineMoney(answeredAmount(line, answers, amendment))}
                        </span>
                      ) : (
                        <LineAmount line={line} />
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** One line in suggest mode: the page's own cells, with Qty and Unit rate as inputs. */
function SuggestRow({
  line,
  position,
  suggest,
}: {
  line: QuotationSignLine;
  position: number;
  suggest: QuotationSignSuggest;
}) {
  const edit = editOf(suggest.edits, line);
  const name = line.item_label?.trim() || String(position + 1);
  const removed = edit.remove;
  const pricing = priceIsEditable(line);
  const qtyError = removed ? null : quantityError(edit.quantity);
  const rateError = removed || !pricing ? null : priceError(edit.unit_price);
  const qtyChanged = !removed && compareMoney(edit.quantity.trim(), line.quantity) !== 0;
  const rateChanged =
    !removed && pricing && compareMoney(edit.unit_price.trim(), line.unit_price) !== 0;
  const inputs = suggest.disabled || removed;

  return (
    <tr
      className={cn(
        'border-t border-border align-top',
        removed && 'text-muted-foreground line-through',
      )}
    >
      <td className="px-2 py-2">{text(line.item_label)}</td>
      <td className="px-2 py-2 text-muted-foreground">{text(line.technical_spec)}</td>
      <td className="px-2 py-2">{text(line.description)}</td>
      <td className="px-2 py-2">{text(line.brand)}</td>
      <td className="px-2 py-2">{text(line.product_code)}</td>
      <td className="px-2 py-2 text-right">
        <Input
          variant="sm"
          value={edit.quantity}
          inputMode="decimal"
          aria-label={`Quantity on line ${name}`}
          aria-invalid={qtyError ? true : undefined}
          disabled={inputs}
          className={cn('w-20 text-end tabular-nums', qtyChanged && 'border-warning bg-warning/10')}
          onChange={(event) => suggest.onEdit(line, { quantity: event.target.value })}
        />
        {qtyError ? (
          <p className="mt-1 max-w-[120px] whitespace-normal text-xs text-destructive">{qtyError}</p>
        ) : qtyChanged ? (
          <p className="mt-1 text-xs text-muted-foreground">{`quoted ${formatQty(line.quantity)}`}</p>
        ) : null}
      </td>
      <td className="px-2 py-2 text-right">
        {pricing ? (
          <>
            <Input
              variant="sm"
              value={edit.unit_price}
              inputMode="decimal"
              aria-label={`Unit rate on line ${name}`}
              aria-invalid={rateError ? true : undefined}
              disabled={inputs}
              className={cn(
                'w-28 text-end tabular-nums',
                rateChanged && 'border-warning bg-warning/10',
              )}
              onChange={(event) => suggest.onEdit(line, { unit_price: event.target.value })}
            />
            {rateError ? (
              <p className="mt-1 max-w-[140px] whitespace-normal text-xs text-destructive">
                {rateError}
              </p>
            ) : rateChanged ? (
              <p className="mt-1 text-xs text-muted-foreground">{`quoted ${formatMyrExact(line.unit_price)}`}</p>
            ) : null}
          </>
        ) : (
          <span className="tabular-nums">{lineMoney(line.unit_price)}</span>
        )}
      </td>
      <td className="px-2 py-2 text-muted-foreground">{text(line.complete_set)}</td>
      <td className="px-2 py-2 text-right">
        {removed ? (
          <Badge variant="destructive" appearance="light" size="sm">
            Remove
          </Badge>
        ) : line.is_rate_only ? (
          <LineAmount line={line} />
        ) : (
          <span className="tabular-nums">{lineMoney(editedAmount(line, edit))}</span>
        )}
      </td>
      <td className="px-1 py-1.5 text-center">
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          aria-label={removed ? `Restore line ${name}` : `Remove line ${name}`}
          title={removed ? 'Restore' : 'Remove'}
          disabled={suggest.disabled}
          onClick={() => suggest.onToggleRemove(line)}
        >
          {removed ? (
            <Undo2 className="size-3.5 text-primary" />
          ) : (
            <Trash2 className="size-3.5 text-destructive" />
          )}
        </Button>
      </td>
    </tr>
  );
}

/**
 * Every scope the issue carried as one card: a row per section that opens to its lines, then the
 * grand total as the last row.
 *
 * A lone section opens on load, because hiding the only thing there is to read behind a tap is
 * friction; two or more start closed so a long quotation reads as a short list of totals first.
 *
 * Rendered even when the issue carries none: a quotation with no scopes is a state somebody can
 * produce, and a section that vanishes reads as a broken page to the person being asked to sign.
 */
export function QuotationSignScopes({
  scopes,
  grandTotal,
  suggest,
  amendment,
}: {
  scopes: QuotationSignScope[];
  grandTotal: string;
  /** Present while the customer is suggesting changes. */
  suggest?: QuotationSignSuggest;
  /** The suggestions already sent, shown in the cells they concern. */
  amendment?: QuotationSignAmendment | null;
}) {
  const keys = scopes.map((_, index) => `scope-${index}`);
  const [open, setOpen] = React.useState<string[]>(scopes.length === 1 ? keys : []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">Quotation</CardTitle>
      </CardHeader>
      <CardContent className="min-w-0 px-3 py-0 sm:px-6">
        {scopes.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            This quotation has no priced items on it.
          </p>
        ) : (
          <Accordion type="multiple" value={open} onValueChange={setOpen}>
            {scopes.map((scope, index) => (
              <AccordionItem key={`${scope.scope_label}-${index}`} value={keys[index]}>
                <AccordionTrigger>
                  <span className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-3 gap-y-1 text-left text-sm">
                    <span className="min-w-0 break-words font-medium">{text(scope.scope_label)}</span>
                    <span className="flex items-center gap-3">
                      <span className="text-muted-foreground">
                        {scope.lines.length === 1 ? '1 item' : `${scope.lines.length} items`}
                      </span>
                      <span className="font-semibold tabular-nums">
                        {formatMyrExact(scope.scope_total)}
                      </span>
                    </span>
                  </span>
                </AccordionTrigger>
                {/* min-w-0 on the content, or the wide table refuses to shrink and the page
                    itself scrolls sideways on a phone. */}
                <AccordionContent className="min-w-0">
                  {scope.lines.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No items under this section.</p>
                  ) : (
                    <ScopeTable lines={scope.lines} suggest={suggest} amendment={amendment} />
                  )}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        )}
        <div
          className={cn(
            'flex flex-wrap items-center justify-between gap-2 py-4',
            scopes.length > 0 && 'border-t border-border',
          )}
        >
          <span className="text-sm font-semibold uppercase tracking-wide">Total amount</span>
          <span className="text-base font-semibold tabular-nums">
            {formatMyrExact(grandTotal)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
