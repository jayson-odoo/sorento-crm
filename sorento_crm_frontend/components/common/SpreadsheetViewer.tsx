'use client';

import { useMemo, useRef, useState } from 'react';
import { observeElementRect, useVirtualizer } from '@tanstack/react-virtual';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

/**
 * A workbook shown in our own grid style (PLAN-excel-preview-26sep, section 3): one line tab
 * per sheet, the header row frozen, the first column pinned, numbers right-aligned, and only
 * the rows in view in the DOM, so a 50,000-row sheet scrolls like a 50-row one.
 *
 * It renders a normalised model, never a file: S1 feeds it the low stock report's view (the
 * workbook before it exists); S2 adds a SheetJS feeder for stored files. Not a `DataGrid`:
 * a sheet is not a record list (no row click, no column config, no pagination), and a
 * workbook can hold hundreds of sheets of different columns.
 */

export type SpreadsheetCell = string | number | null;

export interface SpreadsheetSheet {
  title: string;
  columns: string[];
  rows: SpreadsheetCell[][];
  /** Marks a sheet worth noticing in the tab strip (the low stock report's "- Low" sheets). */
  flagged?: boolean;
  /** What an empty sheet says instead of a bare header. */
  emptyText?: string;
}

export interface SpreadsheetWorkbook {
  sheets: SpreadsheetSheet[];
}

export interface SpreadsheetViewerProps {
  workbook: SpreadsheetWorkbook;
  /** The open sheet, by title. Unknown or omitted opens the first sheet. */
  activeSheet?: string | null;
  onActiveSheetChange?: (title: string) => void;
  /** Previous content kept on screen while the next arrives. */
  busy?: boolean;
  className?: string;
}

/** Past this many sheets a tab strip is not scannable; a searchable picker joins it. */
const GO_TO_SHEET_AFTER = 12;
const ROW_HEIGHT = 32;
/** Rows read when sizing columns: enough to see a typical cell, cheap on 50,000 rows. */
const WIDTH_SAMPLE = 200;

/**
 * What the virtualiser assumes when the scroller measures 0px tall: a container that is not
 * laid out yet (or a test DOM, which lays nothing out). A laid-out scroller holding rows is
 * never 0px, so this only ever stands in for a real measurement that does not exist.
 */
const FALLBACK_RECT = { width: 1280, height: 640 };

const numberFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 });

function cellText(value: SpreadsheetCell): string {
  if (value === null || value === undefined) return '';
  return typeof value === 'number' ? numberFormat.format(value) : value;
}

/** A column is numeric when its first filled cells are numbers. */
function numericColumns(sheet: SpreadsheetSheet): boolean[] {
  return sheet.columns.map((_, col) => {
    for (let i = 0; i < Math.min(sheet.rows.length, WIDTH_SAMPLE); i += 1) {
      const value = sheet.rows[i][col];
      if (value === null || value === '') continue;
      return typeof value === 'number';
    }
    return false;
  });
}

function columnWidths(sheet: SpreadsheetSheet): number[] {
  return sheet.columns.map((header, col) => {
    let longest = header.length;
    for (let i = 0; i < Math.min(sheet.rows.length, WIDTH_SAMPLE); i += 1) {
      longest = Math.max(longest, cellText(sheet.rows[i][col]).length);
    }
    return Math.min(320, Math.max(72, Math.round(longest * 7.5) + 24));
  });
}

export function SpreadsheetViewer({
  workbook,
  activeSheet,
  onActiveSheetChange,
  busy = false,
  className,
}: SpreadsheetViewerProps) {
  const [localSheet, setLocalSheet] = useState<string | null>(null);
  const requested = activeSheet !== undefined ? activeSheet : localSheet;
  const sheets = workbook.sheets;
  const sheet = sheets.find((s) => s.title === requested) ?? sheets[0];

  const select = (title: string) => {
    setLocalSheet(title);
    onActiveSheetChange?.(title);
  };

  const numeric = useMemo(() => (sheet ? numericColumns(sheet) : []), [sheet]);
  const widths = useMemo(() => (sheet ? columnWidths(sheet) : []), [sheet]);
  const template = widths.map((w) => `${w}px`).join(' ');
  const totalWidth = widths.reduce((sum, w) => sum + w, 0);

  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: sheet?.rows.length ?? 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
    initialRect: FALLBACK_RECT,
    observeElementRect: (instance, callback) =>
      observeElementRect(instance, (rect) => callback(rect.height > 0 ? rect : FALLBACK_RECT)),
  });

  const sheetOptions = useMemo(
    () => sheets.map((s) => ({ value: s.title, label: s.title })),
    [sheets],
  );

  if (!sheet) return null;

  const cellClass = (col: number) =>
    cn(
      'truncate border-e border-border px-2.5 leading-8',
      numeric[col] && 'text-end tabular-nums',
      col === 0 && 'sticky start-0 z-10 bg-background',
    );

  return (
    <div className={cn('flex min-w-0 flex-col', className)} data-slot="spreadsheet-viewer">
      <Tabs value={sheet.title} onValueChange={select} className="min-w-0">
        <TabsList variant="line" size="sm" className="px-2">
          {sheets.map((s) => (
            <TabsTrigger key={s.title} value={s.title}>
              {s.flagged ? (
                <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-warning" />
              ) : null}
              {s.title}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="flex flex-wrap items-center gap-2 border-b border-border px-2 py-1.5">
        {sheets.length > GO_TO_SHEET_AFTER ? (
          <div className="w-full max-w-64">
            <label htmlFor="spreadsheet-go-to-sheet" className="sr-only">
              Go to sheet
            </label>
            <SearchableSelect
              id="spreadsheet-go-to-sheet"
              size="sm"
              value={sheet.title}
              onChange={(value) => value && select(value)}
              options={sheetOptions}
              placeholder="Go to sheet"
            />
          </div>
        ) : null}
        <span className="ms-auto text-xs tabular-nums text-muted-foreground">
          {numberFormat.format(sheet.rows.length)} {sheet.rows.length === 1 ? 'row' : 'rows'}
        </span>
      </div>

      <div
        ref={scrollRef}
        data-testid="spreadsheet-scroller"
        className={cn(
          'relative min-w-0 max-h-(--grid-max-h) overflow-auto',
          busy && 'opacity-60',
        )}
        aria-busy={busy || undefined}
      >
        <div
          role="grid"
          aria-label={sheet.title}
          aria-rowcount={sheet.rows.length + 1}
          aria-colcount={sheet.columns.length}
          className="text-2sm"
          style={{ width: totalWidth, minWidth: '100%' }}
        >
          <div
            role="row"
            aria-rowindex={1}
            className="sticky top-0 z-20 grid border-b border-border bg-background/90 backdrop-blur-xs"
            style={{ gridTemplateColumns: template }}
          >
            {sheet.columns.map((column, col) => (
              <div
                key={col}
                role="columnheader"
                title={column}
                className={cn(cellClass(col), 'text-xs font-medium text-muted-foreground')}
              >
                {column}
              </div>
            ))}
          </div>

          {sheet.rows.length === 0 ? (
            <div className="px-4 py-12 text-center text-sm text-muted-foreground">
              {sheet.emptyText ?? 'No rows'}
            </div>
          ) : (
            <div className="relative" style={{ height: virtualizer.getTotalSize() }}>
              {virtualizer.getVirtualItems().map((item) => {
                const row = sheet.rows[item.index];
                return (
                  <div
                    key={item.key}
                    role="row"
                    aria-rowindex={item.index + 2}
                    className="absolute start-0 top-0 grid w-full border-b border-border"
                    style={{
                      gridTemplateColumns: template,
                      height: ROW_HEIGHT,
                      transform: `translateY(${item.start}px)`,
                    }}
                  >
                    {sheet.columns.map((_, col) => {
                      const text = cellText(row[col] ?? null);
                      return (
                        <div key={col} role="gridcell" title={text} className={cellClass(col)}>
                          {text}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
