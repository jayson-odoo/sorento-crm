'use client';

import { useMemo, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import {
  SpreadsheetViewer,
  type SpreadsheetWorkbook,
} from '@/components/common/SpreadsheetViewer';
import type { ExportSplit } from '@/components/common/export-split';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatDateInMalaysia } from '@/lib/helpers';
import { fmtInt } from '../../lib/format';
import { useLowStockDownload } from '../hooks/useLowStockDownload';
import { useLowStockView } from '../hooks/useLowStockView';
import type { LowStockFacet, LowStockView } from '../types/lowStockReport.types';

/** Owner, 26 Sep 01:40Z: "default is split by both". */
const SPLITS: { value: ExportSplit; label: string }[] = [
  { value: 'supplier_category', label: 'Supplier and category' },
  { value: 'supplier', label: 'Supplier' },
  { value: 'category', label: 'Category' },
  { value: 'none', label: 'None' },
];

function plural(n: number, one: string, many: string) {
  return `${fmtInt(n)} ${n === 1 ? one : many}`;
}

/** The view's sheets, each holding its own rows, as the viewer reads a workbook. */
function toWorkbook(view: LowStockView): SpreadsheetWorkbook {
  return {
    sheets: view.sheets.map((sheet) => ({
      title: sheet.title,
      columns: view.columns,
      rows: sheet.row_indexes.map((index) => view.rows[index]),
      flagged: sheet.low,
      emptyText: sheet.low ? 'Nothing low here' : 'No rows',
    })),
  };
}

function FacetFilter({
  id,
  label,
  allLabel,
  many,
  facets,
  value,
  onChange,
}: {
  id: string;
  label: string;
  allLabel: string;
  many: string;
  facets: LowStockFacet[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const counts = useMemo(() => new Map(facets.map((f) => [f.key, f])), [facets]);
  const options = useMemo(() => facets.map((f) => ({ value: f.key, label: f.key })), [facets]);
  return (
    <div className="w-full min-w-0 sm:w-56">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <SearchableMultiSelect
        id={id}
        size="sm"
        value={value}
        onChange={onChange}
        options={options}
        placeholder={allLabel}
        renderTriggerLabel={(selected) =>
          selected.length === 0 ? (
            <span className="text-muted-foreground">{allLabel}</span>
          ) : selected.length === 1 ? (
            <span className="block truncate">{selected[0].label}</span>
          ) : (
            `${fmtInt(selected.length)} ${many}`
          )
        }
        renderOption={(option) => {
          const facet = counts.get(option.value);
          return (
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <span className="min-w-0 flex-1 break-words">{option.label}</span>
              {facet ? (
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {fmtInt(facet.low)} low of {fmtInt(facet.rows)}
                </span>
              ) : null}
            </div>
          );
        }}
      />
    </div>
  );
}

/**
 * The low stock report page (PLAN-excel-preview-26sep S1, AC-10..AC-17): the Excel the buyer
 * is about to download, shown first. Split by supplier and category by default, narrowed by
 * suppliers and categories, one Download that gives exactly what is on screen. No reorder
 * planning grid or actions here (owner, 26 Sep 01:40Z: "too confusing").
 */
export function LowStockReportView({ runId }: { runId?: string }) {
  const [split, setSplit] = useState<ExportSplit>('supplier_category');
  const [suppliers, setSuppliers] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState<string | null>(null);

  const view = useLowStockView({ runId, split, suppliers, categories });
  const download = useLowStockDownload();
  const data = view.data;
  const workbook = useMemo(() => (data ? toWorkbook(data) : null), [data]);

  const emptyRun = !!data && data.facets.suppliers.length === 0;
  const canDownload =
    !!data && !data.over_cap && data.counts.rows > 0 && !view.settling && !download.preparing;

  const onDownload = () => {
    if (!data) return;
    // The request the screen answers, never the one still settling: the file is the view.
    download.start({ ...view.shownRequest, runId: data.run.run_id });
  };

  let body: React.ReactNode;
  if (view.isLoading) {
    body = <SectionSkeleton rows={8} className="p-4" />;
  } else if (!data) {
    body = (
      <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
        <p className="text-sm text-destructive">
          {view.error instanceof Error ? view.error.message : 'Failed to load the low stock report'}
        </p>
        <Button variant="outline" size="sm" onClick={() => void view.refetch()}>
          Retry
        </Button>
      </div>
    );
  } else if (emptyRun) {
    body = (
      <p className="px-4 py-12 text-center text-sm text-muted-foreground">
        No products on this plan
      </p>
    );
  } else if (data.over_cap) {
    body = (
      <p className="px-4 py-12 text-center text-sm text-muted-foreground">
        {fmtInt(data.counts.rows)} rows is over the {fmtInt(data.max_rows)} row limit. Narrow by
        supplier or category.
      </p>
    );
  } else if (workbook) {
    body = (
      <SpreadsheetViewer
        workbook={workbook}
        activeSheet={activeSheet}
        onActiveSheetChange={setActiveSheet}
        busy={view.settling}
      />
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Low stock report">
        {data?.run.as_of ? (
          <p className="text-sm text-muted-foreground">{formatDateInMalaysia(data.run.as_of)}</p>
        ) : null}
      </PageHeader>

      <Card className="min-w-0 overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <Tabs value={split} onValueChange={(value) => setSplit(value as ExportSplit)}>
            <TabsList variant="default" size="sm" aria-label="Split into sheets">
              {SPLITS.map((option) => (
                <TabsTrigger key={option.value} value={option.value}>
                  {option.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <FacetFilter
            id="low-stock-suppliers"
            label="Suppliers"
            allLabel="All suppliers"
            many="suppliers"
            facets={data?.facets.suppliers ?? []}
            value={suppliers}
            onChange={setSuppliers}
          />
          <FacetFilter
            id="low-stock-categories"
            label="Categories"
            allLabel="All categories"
            many="categories"
            facets={data?.facets.categories ?? []}
            value={categories}
            onChange={setCategories}
          />
          {data && !emptyRun ? (
            <span className="text-xs tabular-nums text-muted-foreground">
              {plural(data.counts.rows, 'row', 'rows')}, {plural(data.counts.sheets, 'sheet', 'sheets')}
            </span>
          ) : null}
          <Button className="ms-auto" size="sm" onClick={onDownload} disabled={!canDownload}>
            {download.preparing ? (
              <>
                <Loader2 className="animate-spin" aria-hidden />
                Preparing...
              </>
            ) : (
              <>
                <Download aria-hidden />
                Download
              </>
            )}
          </Button>
        </div>
        {body}
      </Card>
    </div>
  );
}
