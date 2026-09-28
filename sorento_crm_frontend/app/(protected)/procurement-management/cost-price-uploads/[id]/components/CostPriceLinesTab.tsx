'use client';

import * as React from 'react';
import { Ban } from 'lucide-react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useIsMobile } from '@/hooks/use-mobile';
import {
  useCostPriceChangeLines,
  useDecideAllCostPriceLines,
  useDecideCostPriceLine,
  usePatchCostPriceChangeLine,
  useReturnCostPriceChangeSet,
} from '../../hooks/useCostPriceChangeSets';
import { searchCostPriceProductOptions, type PatchLineInput } from '../../services/costPriceService';
import type { CostPriceChangeLine, CostPriceChangeSetDetail } from '../../types/costPrice.types';
import { CostPriceApplyButton } from './CostPriceApplyButton';

// Round 6 R6: no Duplicate code filter - a duplicate code is one line now (the backend
// collapses it and carries the other rows on it as `duplicate_rows`), nothing to resolve.
type FilterKey = 'changed' | 'unchanged' | 'new_link' | 'unmatched' | 'needs_attention';

const FILTERS: { key: FilterKey; label: string; predicate: (l: CostPriceChangeLine) => boolean }[] = [
  { key: 'changed', label: 'Cost changed', predicate: (l) => !l.skipped && l.line_state === 'changed' },
  { key: 'unchanged', label: 'Unchanged', predicate: (l) => !l.skipped && l.line_state === 'unchanged' },
  { key: 'new_link', label: 'New for this supplier', predicate: (l) => !l.skipped && l.line_state === 'new_link' },
  { key: 'unmatched', label: 'Not found', predicate: (l) => !l.skipped && l.match_outcome === 'unmatched' },
  { key: 'needs_attention', label: 'Needs attention', predicate: (l) => !l.skipped && l.line_state === 'needs_attention' },
];

/** A row that rode on another line of its code (R6). The backend already leaves these out. */
const isDuplicateRow = (l: CostPriceChangeLine) => l.flags.includes('duplicate_row');

/** Every grid cell is exactly one line (round 6 R2): one no-wrap row, nothing stacked. */
const ONE_LINE = 'flex min-w-0 items-center gap-1.5 whitespace-nowrap';

function searchTokens(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function matchesSearch(line: CostPriceChangeLine, tokens: string[]): boolean {
  if (!tokens.length) return true;
  const haystack = [line.supplier_code, line.configuration, line.product?.product_code, line.product?.description, line.sheet]
    .filter(Boolean)
    .map((s) => (s as string).toLowerCase());
  return tokens.every((t) => haystack.some((h) => h.includes(t)));
}

function ChangeBadge({ line }: { line: CostPriceChangeLine }) {
  if (line.line_state === 'new_link') return <Badge variant="info">New link</Badge>;
  if (line.change_pct == null) return <span className="text-muted-foreground">-</span>;
  if (line.change_pct === 0) return <Badge variant="secondary">0%</Badge>;
  const rise = line.change_pct > 0;
  return (
    <Badge variant={rise ? 'destructive' : 'success'}>
      {rise ? '+' : ''}
      {line.change_pct.toFixed(1)}%
    </Badge>
  );
}

/**
 * Round 6 R4 (owner, 28 Sep 2026: "show the currency at each line also"): "CNY 10.50" beside
 * both costs on every line. A cost with no currency of its own is in the set's currency.
 */
function costText(value: number | null, currency: string | null): string {
  if (value == null) return 'none';
  return `${currency ? `${currency} ` : ''}${value.toFixed(2)}`;
}

/** AC-S2-06: recorded vs live, terse, on the same one line as the cost now. */
function StaleCell({ line, setCurrency }: { line: CostPriceChangeLine; setCurrency: string }) {
  const stale = line.stale;
  if (!stale) return null;
  const recorded = costText(line.current_unit_cost, line.current_currency ?? setCurrency);
  const live = costText(stale.live_unit_cost, stale.live_currency ?? setCurrency);
  return (
    <span className={`${ONE_LINE} justify-end text-amber-700`} title={`Recorded ${recorded}, now ${live}`}>
      <span className="truncate tabular-nums">{recorded}</span>
      <span className="shrink-0 text-xs">now {stale.live_unit_cost != null ? stale.live_unit_cost.toFixed(2) : 'none'}</span>
    </span>
  );
}

function CostCell({ value, currency }: { value: number | null; currency: string | null }) {
  const text = costText(value, currency);
  return (
    <span className={`${ONE_LINE} justify-end`}>
      <span className="truncate tabular-nums" title={text}>
        {text}
      </span>
    </span>
  );
}

/** R6: the other rows of this code, inline and small ("OPP 9.90 · 彩盒 11.00"). */
function duplicateRowsText(line: CostPriceChangeLine): string | null {
  const rows = line.duplicate_rows ?? [];
  if (!rows.length) return null;
  return rows
    .map((d) => {
      const label = [d.supplier_code !== line.supplier_code ? d.supplier_code : null, d.code_note].filter(Boolean).join(' ');
      const cost = d.new_unit_cost != null ? d.new_unit_cost.toFixed(2) : 'none';
      return label ? `${label} ${cost}` : cost;
    })
    .join(' · ');
}

/** Round 6 R2: skip is a small icon on the line, never a second line of its own. */
function SkipIconButton({ onSkip }: { onSkip: () => void }) {
  return (
    <Button
      type="button"
      size="sm"
      mode="icon"
      variant="ghost"
      className="size-7 shrink-0 text-muted-foreground"
      aria-label="Skip this one"
      title="Skip this one"
      onClick={onSkip}
    >
      <Ban />
    </Button>
  );
}

/**
 * One line, as a card (mockup `cost-price-review.html`, "At 375 wide"): the DataGrid's
 * horizontal-scroll table does not fit a phone, so mobile gets its own layout rather than
 * a narrower cut of the same columns - same fields (code, sheet/row, configuration, our
 * product, price now to new, decision), stacked.
 */
function LineCard({
  line,
  showDecisionColumn,
  isPendingForVerifier,
  onPatch,
  onDecide,
  setCurrency,
}: {
  line: CostPriceChangeLine;
  setCurrency: string;
  showDecisionColumn: boolean;
  isPendingForVerifier: boolean;
  onPatch: (patch: PatchLineInput) => void;
  onDecide: (decision: 'accepted' | 'rejected', reason?: string) => void;
}) {
  const showDecision = isPendingForVerifier && !line.skipped && (line.line_state === 'changed' || line.line_state === 'new_link');
  const showReadOnlyDecision = showDecisionColumn && !isPendingForVerifier && line.decision != null;
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="font-medium">{line.supplier_code}</span>
          {line.code_note ? <span className="ms-1.5 text-xs text-muted-foreground">{line.code_note}</span> : null}
          {duplicateRowsText(line) ? (
            <div className="truncate text-xs text-muted-foreground">{duplicateRowsText(line)}</div>
          ) : null}
        </div>
        <ChangeBadge line={line} />
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {line.sheet} row {line.row_no}
        </span>
        <span className="truncate">{line.configuration ?? ''}</span>
      </div>

      {line.match_outcome === 'unmatched' ? (
        <div className="mt-2 flex items-center gap-1.5">
          <SearchableSelect
            id={`map-mobile-${line.id}`}
            value=""
            onChange={() => {}}
            onOptionChange={(opt) => onPatch({ product_id: opt?.value ?? null })}
            fetchOptions={searchCostPriceProductOptions}
            clearable
            size="sm"
            placeholder="Pick a product"
            triggerClassName="w-full"
          />
          <SkipIconButton onSkip={() => onPatch({ skipped: true, skip_reason: 'Not found' })} />
        </div>
      ) : (
        <>
          <div className="mt-2 flex items-center justify-between text-sm">
            <span className="text-xs text-muted-foreground">Our product</span>
            <span className="font-medium">{line.product?.product_code ?? '-'}</span>
          </div>
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="text-xs text-muted-foreground">Cost now to new</span>
            <span className="tabular-nums">
              {line.current_unit_cost != null ? (
                <span className="text-muted-foreground line-through">{costText(line.current_unit_cost, line.current_currency ?? setCurrency)}</span>
              ) : null}{' '}
              {costText(line.new_unit_cost, setCurrency)}
            </span>
          </div>
          {line.stale ? (
            <div className="mt-1 flex justify-end">
              <StaleCell line={line} setCurrency={setCurrency} />
            </div>
          ) : null}
          {line.line_state === 'needs_attention' ? (
            <div className="mt-1 flex items-center justify-between gap-1.5">
              <span className="text-xs text-destructive">{line.new_unit_cost == null ? 'No readable cost' : 'Needs attention'}</span>
              <SkipIconButton onSkip={() => onPatch({ skipped: true, skip_reason: line.new_unit_cost == null ? 'No readable cost' : 'Needs attention' })} />
            </div>
          ) : null}
        </>
      )}

      {showDecision ? (
        <div className="mt-2 flex items-center gap-1.5">
          <Button type="button" size="sm" variant={line.decision === 'accepted' ? 'primary' : 'outline'} onClick={() => onDecide('accepted')}>
            Accept
          </Button>
          <RejectLineButton
            active={line.decision === 'rejected'}
            supplierCode={line.supplier_code}
            onReject={(reason) => onDecide('rejected', reason)}
          />
        </div>
      ) : null}
      {showReadOnlyDecision ? (
        <div className="mt-2">
          {line.decision === 'accepted' ? (
            <Badge variant="success">Accepted</Badge>
          ) : (
            <>
              <Badge variant="destructive" title={line.decision_reason ?? undefined}>
                Rejected
              </Badge>
              {line.decision_reason ? (
                <div className="mt-0.5 truncate text-xs text-muted-foreground" title={line.decision_reason}>
                  {line.decision_reason}
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * AC-S2-01 + J7: a line is rejected "optionally with a reason", and the reason shown under
 * the Reject (mockup) and in History must be the verifier's own words, so Reject asks for
 * it here; an empty reason sends none.
 */
function RejectLineButton({
  active,
  supplierCode,
  onReject,
}: {
  active: boolean;
  supplierCode: string | null;
  onReject: (reason?: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const fieldId = React.useId();

  return (
    <>
      <Button type="button" size="sm" variant={active ? 'destructive' : 'outline'} onClick={() => setOpen(true)}>
        Reject
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reject {supplierCode ?? 'this line'}</DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-1.5">
            <Label htmlFor={fieldId}>Reason (optional)</Label>
            <Textarea
              id={fieldId}
              value={reason}
              onChange={(e) => setReason(e.target.value.slice(0, 500))}
              rows={3}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                onReject(reason.trim() || undefined);
                setOpen(false);
                setReason('');
              }}
            >
              Reject line
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Return to submitter needs a reason (AC-S2-09), so it is the one action here with a dialog. */
function ReturnDialog({ setId, onDone }: { setId: string; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const returnSet = useReturnCostPriceChangeSet(setId);

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        Return to submitter
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Return to submitter</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value.slice(0, 500))}
              placeholder="Why is this set going back?"
              rows={4}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!reason.trim() || returnSet.isPending}
              onClick={async () => {
                await returnSet.mutateAsync(reason.trim());
                setOpen(false);
                setReason('');
                onDone();
              }}
            >
              Return
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function CostPriceLinesTab({ changeSet }: { changeSet: CostPriceChangeSetDetail }) {
  const { data } = useCostPriceChangeLines(changeSet.id);
  const lines = React.useMemo(() => (data?.data ?? []).filter((l) => !isDuplicateRow(l)), [data]);
  // Cards at 375 (mockup "At 375 wide"), the DataGrid at sm+ - a JS switch, not a CSS
  // one: `sm:hidden`/`hidden sm:block` render BOTH into the DOM regardless of viewport
  // (jsdom applies no CSS), which doubled every button `getByRole` sees in the existing
  // vitest suite. `useIsMobile` defaults to false until its effect runs, which in jsdom
  // (innerWidth 1024) settles on the desktop view - the same one these tests render today.
  const isMobile = useIsMobile();

  const [activeFilter, setActiveFilter] = React.useState<FilterKey>('changed');
  const [search, setSearch] = React.useState('');
  const [activeSheet, setActiveSheet] = React.useState('all');

  const patchLine = usePatchCostPriceChangeLine(changeSet.id);
  const decideLine = useDecideCostPriceLine(changeSet.id);
  const decideAll = useDecideAllCostPriceLines(changeSet.id);

  const tokens = React.useMemo(() => searchTokens(search), [search]);
  const searchedLines = React.useMemo(() => lines.filter((l) => matchesSearch(l, tokens)), [lines, tokens]);

  const sheets = React.useMemo(() => Array.from(new Set(lines.map((l) => l.sheet))), [lines]);

  const filteredLines = React.useMemo(() => {
    const predicate = FILTERS.find((f) => f.key === activeFilter)!.predicate;
    return searchedLines.filter((l) => predicate(l) && (activeSheet === 'all' || l.sheet === activeSheet));
  }, [searchedLines, activeFilter, activeSheet]);

  const isVerifier = changeSet.actions.can_decide || changeSet.actions.can_return;
  const isPendingForVerifier = isVerifier && changeSet.status === 'pending_verification';
  // J14/AC-AU-04 (tester finding 1): once a set leaves Pending, a line's decision must
  // stay visible - read-only - not vanish the moment `showDecisionColumn`'s original
  // "verifier on a Pending set" condition goes false. A read-only column earns its
  // place ONLY when there is something to show; an untouched draft/applied-with-no-
  // decisions set gets no Decision column at all.
  const anyLineHasDecision = lines.some((l) => l.decision != null);
  const showDecisionColumn = isPendingForVerifier || anyLineHasDecision;

  const columns = React.useMemo<ColumnDef<CostPriceChangeLine>[]>(() => {
    const skip = (line: CostPriceChangeLine, reason: string) =>
      void patchLine.mutateAsync({ lineId: line.id, patch: { skipped: true, skip_reason: reason } });
    // Widths (1280, round 6 R2): every cell is one line, and a verifier's Decision column
    // (150) still lands inside ~950px: 80 + 200 + 80 + 150 + 110 + 110 + 70 + 150 = 950.
    const base: ColumnDef<CostPriceChangeLine>[] = [
      {
        // Sheet and Row merged into one column (column-width budget, 1280 breakpoint).
        id: 'sheet_row',
        header: 'Sheet / row',
        size: 80,
        cell: ({ row }) => (
          <div className={`${ONE_LINE} text-xs`} title={`${row.original.sheet}, row ${row.original.row_no}`}>
            <span className="truncate font-medium">{row.original.sheet}</span>
            <span className="shrink-0 text-muted-foreground">{row.original.row_no}</span>
          </div>
        ),
      },
      {
        id: 'supplier_code',
        header: 'Supplier code',
        size: 200,
        cell: ({ row }) => {
          const line = row.original;
          const others = duplicateRowsText(line);
          const title = [line.supplier_code, line.code_note, others].filter(Boolean).join(' · ');
          return (
            <div className={ONE_LINE} title={title}>
              <span className="shrink-0 font-medium">{line.supplier_code}</span>
              {line.code_note ? <span className="truncate text-xs text-muted-foreground">{line.code_note}</span> : null}
              {others ? <span className="truncate text-xs text-muted-foreground">{others}</span> : null}
            </div>
          );
        },
      },
      {
        id: 'configuration',
        header: 'Configuration',
        size: 80,
        cell: ({ row }) => (
          <div className={ONE_LINE} title={row.original.configuration ?? ''}>
            <span className="truncate">{row.original.configuration ?? '-'}</span>
            {row.original.flags.includes('configuration_from_merge') ? (
              <span className="shrink-0 text-xs text-muted-foreground">merged</span>
            ) : null}
          </div>
        ),
      },
      {
        id: 'product',
        header: 'Our product',
        size: 150,
        cell: ({ row }) => {
          const line = row.original;
          if (line.match_outcome === 'unmatched') {
            return (
              <div className={ONE_LINE}>
                <div className="min-w-0 flex-1">
                  <SearchableSelect
                    id={`map-${line.id}`}
                    value=""
                    onChange={() => {}}
                    onOptionChange={(opt) =>
                      void patchLine.mutateAsync({ lineId: line.id, patch: { product_id: opt?.value ?? null } })
                    }
                    fetchOptions={searchCostPriceProductOptions}
                    clearable
                    size="sm"
                    placeholder="Pick a product"
                    triggerClassName="w-full"
                  />
                </div>
                <SkipIconButton onSkip={() => skip(line, 'Not found')} />
              </div>
            );
          }
          const matchNote =
            line.match_rung || line.match_outcome !== 'exact'
              ? `${line.match_outcome === 'manual' ? 'mapped by hand' : line.match_rung ? `supplier code rule: ${line.match_rung}` : line.match_outcome}${
                  line.line_state === 'new_link' ? ', new for this supplier' : ''
                }`
              : null;
          if (line.line_state === 'needs_attention') {
            const reason = line.new_unit_cost == null ? 'No readable cost' : 'Needs attention';
            return (
              <div className={ONE_LINE} title={[line.product?.product_code, reason].filter(Boolean).join(' · ')}>
                <span className="truncate font-medium">{line.product?.product_code ?? '-'}</span>
                <span className="truncate text-xs text-destructive">{reason}</span>
                <SkipIconButton onSkip={() => skip(line, reason)} />
              </div>
            );
          }
          return (
            <div className={ONE_LINE} title={[line.product?.product_code, matchNote].filter(Boolean).join(' · ')}>
              <span className="truncate font-medium">{line.product?.product_code ?? '-'}</span>
              {matchNote ? <span className="truncate text-xs text-muted-foreground">{matchNote}</span> : null}
            </div>
          );
        },
      },
      {
        id: 'current',
        header: 'Cost now',
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) =>
          row.original.stale ? (
            <StaleCell line={row.original} setCurrency={changeSet.currency} />
          ) : (
            <CostCell value={row.original.current_unit_cost} currency={row.original.current_currency ?? changeSet.currency} />
          ),
      },
      {
        id: 'new',
        header: 'New cost',
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => <CostCell value={row.original.new_unit_cost} currency={changeSet.currency} />,
      },
      {
        id: 'change',
        header: 'Change',
        size: 70,
        cell: ({ row }) => (
          <div className={ONE_LINE}>
            <ChangeBadge line={row.original} />
          </div>
        ),
      },
    ];

    if (showDecisionColumn) {
      base.push({
        id: 'decision',
        header: 'Decision',
        size: isPendingForVerifier ? 150 : 130,
        cell: ({ row }) => {
          const line = row.original;
          if (isPendingForVerifier) {
            if (line.skipped || (line.line_state !== 'changed' && line.line_state !== 'new_link')) {
              return (
                <div className={ONE_LINE}>
                  <span className="text-muted-foreground">-</span>
                </div>
              );
            }
            return (
              <div className={ONE_LINE}>
                <Button
                  type="button"
                  size="sm"
                  variant={line.decision === 'accepted' ? 'primary' : 'outline'}
                  onClick={() => void decideLine.mutateAsync({ lineId: line.id, decision: 'accepted' })}
                >
                  Accept
                </Button>
                <RejectLineButton
                  active={line.decision === 'rejected'}
                  supplierCode={line.supplier_code}
                  onReject={(reason) => void decideLine.mutateAsync({ lineId: line.id, decision: 'rejected', reason })}
                />
              </div>
            );
          }
          // J14/AC-AU-04: the set has left Pending (or the caller isn't the verifier who
          // decided it) - a line's decision is now a FACT of the record, not something
          // to re-decide, so it renders read-only. The reject reason travels with it on the
          // same line (visible text AND `title`), so no reviewer has to cross-reference
          // the History tab to learn why a line was rejected.
          if (!line.decision) {
            return (
              <div className={ONE_LINE}>
                <span className="text-muted-foreground">-</span>
              </div>
            );
          }
          if (line.decision === 'accepted') {
            return (
              <div className={ONE_LINE}>
                <Badge variant="success">Accepted</Badge>
              </div>
            );
          }
          return (
            <div className={ONE_LINE}>
              <Badge variant="destructive" title={line.decision_reason ?? undefined}>
                Rejected
              </Badge>
              {line.decision_reason ? (
                <span className="truncate text-xs text-muted-foreground" title={line.decision_reason}>
                  {line.decision_reason}
                </span>
              ) : null}
            </div>
          );
        },
      });
    }
    return base;
  }, [changeSet.currency, decideLine, isPendingForVerifier, patchLine, showDecisionColumn]);

  const table = useReactTable({
    columns,
    data: filteredLines,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyMessages: Record<FilterKey, string> = {
    changed: 'Nothing changed against current costs',
    unchanged: 'No unchanged rows',
    new_link: 'No new products from this supplier',
    unmatched: 'No codes need mapping',
    needs_attention: 'Nothing needs attention',
  };

  const actions = changeSet.actions;

  return (
    <div className="space-y-4">
      {/* Stat cards as filters (search-scoped counts, AC-SR-02). */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {FILTERS.map((f) => {
          const count = searchedLines.filter(f.predicate).length;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setActiveFilter(f.key)}
              className={`rounded-lg border p-2.5 text-left transition-colors ${
                activeFilter === f.key ? 'border-primary bg-primary/5' : 'border-border bg-card'
              }`}
            >
              <div className="text-lg font-bold tabular-nums">{count}</div>
              <div className="text-xs text-muted-foreground">{f.label}</div>
            </button>
          );
        })}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <ListSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search code, configuration or product"
          className="w-full sm:w-72"
        />
        {sheets.length > 1 ? (
          <Tabs value={activeSheet} onValueChange={setActiveSheet} className="min-w-0 flex-1">
            <TabsList variant="line" className="w-full justify-start">
              <TabsTrigger value="all">All sheets</TabsTrigger>
              {sheets.map((sheet) => (
                <TabsTrigger key={sheet} value={sheet}>
                  {sheet}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        ) : null}
      </div>

      {filteredLines.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center gap-3 p-10 text-center">
            <p className="text-sm font-medium">{emptyMessages[activeFilter]}</p>
            {activeFilter === 'changed' && searchedLines.length === lines.length && lines.every((l) => l.line_state === 'unchanged' || l.skipped) && actions.can_discard ? (
              <p className="text-xs text-muted-foreground">Discard this set from the header above.</p>
            ) : null}
          </div>
        </Card>
      ) : isMobile ? (
        <div className="space-y-2">
          {filteredLines.map((line) => (
            <LineCard
              key={line.id}
              line={line}
              showDecisionColumn={showDecisionColumn}
              isPendingForVerifier={isPendingForVerifier}
              setCurrency={changeSet.currency}
              onPatch={(patch) => void patchLine.mutateAsync({ lineId: line.id, patch })}
              onDecide={(decision, reason) => void decideLine.mutateAsync({ lineId: line.id, decision, reason })}
            />
          ))}
        </div>
      ) : (
        <DataGrid table={table} recordCount={filteredLines.length} listingKey="" tableLayout={{ width: 'fixed', columnsResizable: true }}>
          <Card>
            <CardTable>
              <DataGridTable />
            </CardTable>
          </Card>
        </DataGrid>
      )}

      {/* Sticky apply bar, driven only by `actions` from the detail (contract 1.4) - the FE
          never re-derives the four-eyes rule. Nothing left to do on an applied set. Its
          button is the header's call to action too (round 6 R1), one component for both;
          "N row(s) still need you" only shows while the backend counts such rows. */}
      {changeSet.status !== 'applied' ? (
        <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-background p-3 shadow-sm">
          <span className="text-sm font-medium">
            {actions.apply_count} {actions.apply_count === 1 ? 'change' : 'changes'} ready
          </span>
          {changeSet.largest_rise ? (
            <span className="text-sm text-muted-foreground">
              Largest rise: {changeSet.largest_rise.supplier_code} +{changeSet.largest_rise.change_pct.toFixed(1)}%
            </span>
          ) : null}
          {actions.apply_blocked_reason ? (
            <span className="text-sm text-muted-foreground">{actions.apply_blocked_reason}</span>
          ) : null}
          <div className="ms-auto flex flex-wrap items-center gap-2">
            {actions.can_decide ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void decideAll.mutateAsync('accepted')}>
                Accept all
              </Button>
            ) : null}
            {actions.can_return ? <ReturnDialog setId={changeSet.id} onDone={() => {}} /> : null}
            <CostPriceApplyButton changeSet={changeSet} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default CostPriceLinesTab;
