'use client';

import * as React from 'react';
import { MessageSquarePlus } from 'lucide-react';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
// The one decimal-exact money formatter in the repo. Imported rather than re-implemented: a
// second formatter is how the public page and the PDF end up disagreeing by a cent, and the
// customer reading this screen is the person who would notice.
import {
  formatFigureExact,
  formatMyrExact,
  formatQty,
} from '@/app/(protected)/project-sales/_shared/lib/money';
import {
  hasColumns,
  leaves,
  type MatrixHeader,
} from '@/app/(protected)/project-sales/_shared/lib/quotationMatrix';
import type {
  QuotationSignAmendment,
  QuotationSignColumn,
  QuotationSignLine,
  QuotationSignScope,
} from '../../services/quotationSignService';
import type { FeedbackTarget } from './quotationSuggest';

/**
 * How each column the server sends is drawn. The SET, order and labels are the server's
 * (`scope.columns`, the PDF's own definition); only width and alignment live here. An unknown key
 * still gets its header and an empty cell, so a column added on the server is never dropped.
 */
const PRESENTATION: Record<string, { th: string; td: string }> = {
  item: { th: 'min-w-[60px] text-left', td: '' },
  image: { th: 'min-w-[84px] text-left', td: '' },
  spec: { th: 'min-w-[84px] text-left', td: '' },
  description: { th: 'min-w-[200px] text-left', td: '' },
  brand: { th: 'min-w-[100px] text-left', td: '' },
  product_code: { th: 'min-w-[120px] text-left', td: '' },
  qty: { th: 'min-w-[70px] text-right', td: 'text-right tabular-nums' },
  unit_rate: { th: 'min-w-[120px] text-right', td: 'text-right tabular-nums' },
  complete_set: { th: 'min-w-[140px] text-left', td: 'text-muted-foreground' },
  amount: { th: 'min-w-[120px] text-right', td: 'text-right' },
};

function presentation(key: string) {
  return PRESENTATION[key] ?? { th: 'text-left', td: '' };
}

/** A picture cell: the photo or the drawing, inline, at the PDF's scale. Empty when there is none. */
function Picture({ src, alt }: { src?: string | null; alt: string }) {
  if (!src) return null;
  return (
    <img
      src={src}
      alt={alt}
      className="size-16 max-w-none rounded-sm object-contain"
    />
  );
}

/** The QTY cell as the PDF prints it: the count, then the unit when there is one ("2 pcs"). */
function withUom(line: QuotationSignLine): string {
  const uom = line.uom?.trim();
  return uom ? `${formatQty(line.quantity)} ${uom}` : formatQty(line.quantity);
}

/** Description, with any typed technical-spec text from before drawings beneath it, as the PDF. */
function Description({ line }: { line: QuotationSignLine }) {
  return (
    <>
      {cell(line.description)}
      {line.technical_spec?.trim() ? (
        <span className="mt-1 block whitespace-pre-line text-xs text-muted-foreground">
          {line.technical_spec}
        </span>
      ) : null}
    </>
  );
}

/** The cells every mode shares, by column key. Qty, rate and amount are each mode's own. */
function commonCells(
  line: QuotationSignLine,
  position: number,
): Record<string, React.ReactNode> {
  const name = line.item_label?.trim() || String(position + 1);
  return {
    item: cell(line.item_label),
    image: <Picture src={line.image_url} alt={`Product photo, line ${name}`} />,
    spec: (
      <Picture src={line.drawing_url} alt={`Technical drawing, line ${name}`} />
    ),
    description: <Description line={line} />,
    brand: cell(line.brand),
    product_code: cell(line.product_code),
    complete_set: cell(line.complete_set),
  };
}

function Cells({
  columns,
  cells,
}: {
  columns: QuotationSignColumn[];
  cells: Record<string, React.ReactNode>;
}) {
  return (
    <>
      {columns.map((column) => (
        <td
          key={column.key}
          className={cn('px-2 py-2', presentation(column.key).td)}
        >
          {cells[column.key] ?? null}
        </td>
      ))}
    </>
  );
}


/** What already has feedback on it: whole items by line, cells by line and cell. */
type Sent = { items: Set<string>; cells: Set<string> };

function sentOf(amendment: QuotationSignAmendment | null | undefined): Sent {
  const items = new Set<string>();
  const cells = new Set<string>();
  (amendment?.rows ?? []).forEach((row) => {
    if (row.cell_key) cells.add(`${row.line_id}:${row.cell_key}`);
    else items.add(row.line_id);
  });
  return { items, cells };
}

/**
 * A table cell's text: blank when there is nothing, as the PDF's `_cell` prints it. A dash in a
 * cell the PDF leaves empty is the page and the document disagreeing.
 */
function cell(value: string | null | undefined): string {
  return value?.trim() ? value : '';
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
  return Number.isFinite(amount) && amount === 0
    ? ''
    : formatFigureExact(value ?? '0');
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

/** The item as the customer reads it: its description, else its code, else its position. */
function itemName(line: QuotationSignLine, position: number): string {
  // Not `item_label`: since #2106 that is the printed item NUMBER ("1"), which the ITEM column
  // shows, and "Feedback on 1" names nothing a customer would recognise (fix round 2, B2).
  return line.description?.trim() || line.product_code?.trim() || `Item ${position + 1}`;
}

/** Brand and code under the item's name in the grid, muted (mock v3 frame 4). */
function itemDetail(line: QuotationSignLine): string {
  return [line.brand?.trim(), line.product_code?.trim()].filter(Boolean).join(' · ');
}

/** The amber dot by an item that already has feedback (mock v3 frame 4). */
function SentDot() {
  return (
    <span
      role="img"
      aria-label="Feedback sent"
      data-testid="sign-feedback-dot"
      className="ms-1 inline-block size-2 rounded-full bg-warning align-middle"
    />
  );
}

function FeedbackButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <Button
      type="button"
      mode="icon"
      variant="ghost"
      size="sm"
      aria-label={`Leave feedback on ${name}`}
      title="Leave feedback"
      onClick={onClick}
    >
      <MessageSquarePlus className="size-4 text-primary" />
    </Button>
  );
}

/** A band label heads its section ONCE, above the line that opens it. */
function bandsOf(lines: QuotationSignLine[]): (string | null)[] {
  let current: string | null = null;
  return lines.map((line) => {
    const band = line.band_label?.trim() ? line.band_label.trim() : null;
    if (band !== null && band !== current) {
      current = band;
      return band;
    }
    return null;
  });
}

function ScopeTable({
  scopeLabel,
  columns,
  lines,
  sent,
  onFeedback,
}: {
  scopeLabel: string;
  /** The quotation's own column set for this scope, as the server (and the PDF) decides it. */
  columns: QuotationSignColumn[];
  lines: QuotationSignLine[];
  sent: Sent;
  onFeedback?: (target: FeedbackTarget) => void;
}) {
  const span = onFeedback ? columns.length + 1 : columns.length;
  const bands = bandsOf(lines);

  return (
    // Hand-rolled and read-only on purpose: this is a printed quotation being read by a stranger
    // on a phone, with nothing to sort, page or select, so DataGrid's toolbar and pagination
    // would be furniture in the way. `overflow-x-auto` + `min-w-0` keep the wide table scrolling
    // inside its own gutter instead of dragging the whole PAGE sideways at 375px, and every
    // column stays: a phone scrolls the quotation, it never reads a shorter one.
    // `relative` so the sr-only header label (position: absolute) is clipped by this scroller
    // instead of escaping it and widening the whole page at 375px.
    <div
      data-testid="quotation-sign-scroller"
      className="relative min-w-0 overflow-x-auto"
    >
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={cn('px-2 py-2 font-semibold', presentation(column.key).th)}
              >
                {column.label}
              </th>
            ))}
            {onFeedback && (
              <th className="w-10 px-1 py-2">
                <span className="sr-only">Feedback</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => {
            const name = itemName(line, index);
            const common = commonCells(line, index);
            return (
              <React.Fragment key={index}>
                {bands[index] !== null && (
                  <tr className="bg-muted/60">
                    <td
                      colSpan={span}
                      className="px-2 py-2 text-xs font-semibold uppercase tracking-wide"
                    >
                      {bands[index]}
                    </td>
                  </tr>
                )}
                <tr className="border-t border-border align-top">
                  <Cells
                    columns={columns}
                    cells={{
                      ...common,
                      // The dot marks an item that already has feedback, beside its number.
                      item: (
                        <>
                          {common.item}
                          {sent.items.has(line.id) && <SentDot />}
                        </>
                      ),
                      qty: withUom(line),
                      unit_rate: lineMoney(line.unit_price),
                      amount: <LineAmount line={line} />,
                    }}
                  />
                  {onFeedback && (
                    <td className="px-1 py-1.5 text-center">
                      <FeedbackButton
                        name={name}
                        onClick={() => onFeedback({ line, itemLabel: name, scopeLabel })}
                      />
                    </td>
                  )}
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * A scope with column headers, read-only (R18, mock v3 frame 4): the item pinned on the left, the
 * headers over their columns, Total qty, the rate and the amount; the table scrolls sideways on a
 * phone. Tapping a quantity leaves feedback on that cell; the item's button, on the whole item.
 */
function MatrixScopeTable({
  scopeLabel,
  columns,
  headers,
  lines,
  sent,
  onFeedback,
}: {
  scopeLabel: string;
  /** The quotation's own column set: the grid shows the photo column when it carries one. */
  columns: QuotationSignColumn[];
  headers: MatrixHeader[];
  lines: QuotationSignLine[];
  sent: Sent;
  onFeedback?: (target: FeedbackTarget) => void;
}) {
  const allLeaves = leaves(headers);
  const photo = columns.find((column) => column.key === 'image');
  const span = 1 + (photo ? 1 : 0) + allLeaves.length + 3 + (onFeedback ? 1 : 0);
  const bands = bandsOf(lines);
  const pinned = 'sticky left-0 z-10 bg-background';

  return (
    <div
      data-testid="quotation-sign-scroller"
      className="relative min-w-0 overflow-x-auto"
    >
      <table className="w-full border-separate border-spacing-0 text-sm">
        <thead className="text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th
              rowSpan={2}
              className={cn(pinned, 'min-w-[140px] max-w-[180px] bg-muted px-2 py-2 text-left font-semibold')}
            >
              Item
            </th>
            {photo && (
              <th rowSpan={2} className={cn('bg-muted/40 px-2 py-2 font-semibold', presentation('image').th)}>
                {photo.label}
              </th>
            )}
            {headers.map((header) => (
              <th
                key={header.key}
                rowSpan={header.cols.length === 0 ? 2 : 1}
                colSpan={Math.max(header.cols.length, 1)}
                className="border-b border-border bg-primary/5 px-2 py-2 text-center font-semibold"
              >
                {header.label}
              </th>
            ))}
            <th rowSpan={2} className="min-w-[80px] bg-muted/40 px-2 py-2 text-right font-semibold">
              Total qty
            </th>
            <th rowSpan={2} className="min-w-[110px] bg-muted/40 px-2 py-2 text-right font-semibold">
              Unit rate
            </th>
            <th rowSpan={2} className="min-w-[120px] bg-muted/40 px-2 py-2 text-right font-semibold">
              Amount
            </th>
            {onFeedback && (
              <th rowSpan={2} className="w-10 bg-muted/40 px-1 py-2">
                <span className="sr-only">Feedback</span>
              </th>
            )}
          </tr>
          <tr>
            {allLeaves
              .filter((leaf) => !leaf.isHeader)
              .map((leaf) => (
                <th key={leaf.key} className="min-w-[64px] bg-muted/40 px-2 py-2 text-center font-semibold">
                  {leaf.label}
                </th>
              ))}
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => {
            const name = itemName(line, index);
            const cells = line.qty_cells ?? {};
            return (
              <React.Fragment key={index}>
                {bands[index] !== null && (
                  <tr className="bg-muted/60">
                    <td
                      colSpan={span}
                      className="px-2 py-2 text-xs font-semibold uppercase tracking-wide"
                    >
                      {bands[index]}
                    </td>
                  </tr>
                )}
                <tr className="align-top">
                  <td className={cn(pinned, 'max-w-[180px] border-t border-border px-2 py-2')}>
                    <span className="block break-words">
                      {name}
                      {sent.items.has(line.id) && <SentDot />}
                    </span>
                    {itemDetail(line) && itemDetail(line) !== name && (
                      <span className="block break-words text-xs text-muted-foreground">
                        {itemDetail(line)}
                      </span>
                    )}
                  </td>
                  {photo && (
                    <td className="border-t border-border px-2 py-2">
                      {commonCells(line, index).image}
                    </td>
                  )}
                  {allLeaves.map((leaf) => {
                    const value = cells[leaf.key] ?? '';
                    const shown = value.trim() ? formatQty(value) : '';
                    const marked = sent.cells.has(`${line.id}:${leaf.key}`);
                    const where = leaf.isHeader ? leaf.headerLabel : `${leaf.headerLabel} / ${leaf.label}`;
                    return (
                      <td key={leaf.key} className="border-t border-border px-1 py-1 text-center">
                        {onFeedback ? (
                          <button
                            type="button"
                            aria-label={`Leave feedback on ${name}, ${where}`}
                            className="relative inline-flex h-8 min-w-[48px] items-center justify-center rounded-md border border-border bg-background px-1.5 tabular-nums hover:border-primary"
                            onClick={() =>
                              onFeedback({
                                line,
                                itemLabel: name,
                                scopeLabel,
                                cell: { key: leaf.key, label: where, value: shown || '0' },
                              })
                            }
                          >
                            {shown}
                            {marked && <CellCorner />}
                          </button>
                        ) : (
                          <span className="relative inline-block min-w-[48px] tabular-nums">
                            {shown}
                            {marked && <CellCorner />}
                          </span>
                        )}
                      </td>
                    );
                  })}
                  <td className="border-t border-border px-2 py-2 text-right font-medium tabular-nums">
                    {formatQty(line.quantity)}
                  </td>
                  <td className="border-t border-border px-2 py-2 text-right tabular-nums">
                    {lineMoney(line.unit_price)}
                  </td>
                  <td className="border-t border-border px-2 py-2 text-right">
                    <LineAmount line={line} />
                  </td>
                  {onFeedback && (
                    <td className="border-t border-border px-1 py-1.5 text-center">
                      <FeedbackButton
                        name={name}
                        onClick={() => onFeedback({ line, itemLabel: name, scopeLabel })}
                      />
                    </td>
                  )}
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CellCorner() {
  return (
    <span
      role="img"
      aria-label="Feedback sent"
      data-testid="sign-feedback-corner"
      className="absolute end-0 top-0 size-0 border-s-[8px] border-t-[8px] border-s-transparent border-t-warning"
    />
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
  sent,
  onFeedback,
  action,
}: {
  scopes: QuotationSignScope[];
  grandTotal: string;
  /** One control beside the card's title (Leave a note). */
  action?: React.ReactNode;
  /** Feedback already sent, marked on the items and cells it points at. */
  sent?: QuotationSignAmendment | null;
  /** Present while feedback can be left: opens the form for an item or a cell. */
  onFeedback?: (target: FeedbackTarget) => void;
}) {
  const keys = scopes.map((_, index) => `scope-${index}`);
  const [open, setOpen] = React.useState<string[]>(
    scopes.length === 1 ? keys : [],
  );
  const marks = React.useMemo(() => sentOf(sent), [sent]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="min-w-0 break-words text-sm">Quotation</CardTitle>
        {action}
      </CardHeader>
      <CardContent className="min-w-0 px-3 py-0 sm:px-6">
        {scopes.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            This quotation has no priced items on it.
          </p>
        ) : (
          <Accordion type="multiple" value={open} onValueChange={setOpen}>
            {scopes.map((scope, index) => (
              <AccordionItem
                key={`${scope.scope_label}-${index}`}
                value={keys[index]}
              >
                <AccordionTrigger>
                  <span className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-x-3 gap-y-1 text-left text-sm">
                    <span className="min-w-0 break-words font-medium">
                      {text(scope.scope_label)}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="text-muted-foreground">
                        {scope.lines.length === 1
                          ? '1 item'
                          : `${scope.lines.length} items`}
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
                    <p className="text-sm text-muted-foreground">
                      No items under this section.
                    </p>
                  ) : hasColumns(scope.matrix_columns) ? (
                    <MatrixScopeTable
                      scopeLabel={scope.scope_label}
                      columns={scope.columns ?? []}
                      headers={scope.matrix_columns}
                      lines={scope.lines}
                      sent={marks}
                      onFeedback={onFeedback}
                    />
                  ) : (
                    <ScopeTable
                      scopeLabel={scope.scope_label}
                      columns={scope.columns ?? []}
                      lines={scope.lines}
                      sent={marks}
                      onFeedback={onFeedback}
                    />
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
          <span className="text-sm font-semibold uppercase tracking-wide">
            Total amount
          </span>
          <span className="text-base font-semibold tabular-nums">
            {formatMyrExact(grandTotal)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
