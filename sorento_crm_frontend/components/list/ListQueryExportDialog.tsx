'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { generateExcelFile, type ColumnOption } from '@/lib/excel-utils';
import {
  fetchListQueryFields,
  postListQueryExport,
  type ListQueryFieldMeta,
  type ListQueryResourceKey,
} from '@/lib/list-query/listQueryService';
import { groupOrderListFields, shortNestedOrderLineLabel } from '@/lib/list-query/orderFieldGroups';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

export type ListQueryExportDialogProps = {
  resourceKey: ListQueryResourceKey;
  filename?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Extra POST body fields: filter, quick_search, legacy list params (snake_case). */
  getPayload: () => Record<string, unknown>;
  /** When non-empty, export only these row ids (server still applies list filters). */
  selectedRecordIds?: string[];
  /** Workflow submissions: include form-field columns from this definition's published schema. */
  workflowDefinitionId?: string | null;
};

function ExportFieldRow({
  f,
  selected,
  toggle,
  sub,
}: {
  f: ListQueryFieldMeta;
  selected: Set<string>;
  toggle: (key: string) => void;
  sub?: 'product' | 'warehouse';
}) {
  const text = sub ? shortNestedOrderLineLabel(f.label, sub) : f.label;
  return (
    <label
      className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1.5 hover:bg-muted/60"
    >
      <Checkbox checked={selected.has(f.field_key)} onCheckedChange={() => toggle(f.field_key)} />
      <span className="text-sm">
        {text}
        {!sub && f.is_line_field ? (
          <span className="text-muted-foreground"></span>
        ) : null}
      </span>
    </label>
  );
}

function OrdersExportColumnsTree({
  exportable,
  selected,
  toggle,
}: {
  exportable: ListQueryFieldMeta[];
  selected: Set<string>;
  toggle: (key: string) => void;
}) {
  const groups = useMemo(() => groupOrderListFields(exportable), [exportable]);

  const hasNestedLineGroups = groups.product.length > 0 || groups.warehouse.length > 0;
  const hasAnyLineFields =
    groups.lineDirect.length > 0 || hasNestedLineGroups;

  const accordionTriggerClass =
    'py-3 text-sm font-semibold hover:no-underline [&[data-state=open]]:text-foreground';
  const nestedTriggerClass =
    'py-2.5 text-sm font-medium hover:no-underline [&[data-state=open]]:text-foreground';

  const defaultOpen = ['export-order', ...(hasAnyLineFields ? (['export-line'] as const) : [])];

  return (
    <Accordion
      type="multiple"
      defaultValue={[...defaultOpen]}
      variant="outline"
      className="w-full space-y-2"
    >
      <AccordionItem value="export-order" className="rounded-lg border border-border px-3">
        <AccordionTrigger className={accordionTriggerClass}>Order columns</AccordionTrigger>
        <AccordionContent>
          <div className="space-y-1 border-s-2 border-primary/25 ps-3 pb-1">
            {groups.order.map((f) => (
              <ExportFieldRow key={f.field_key} f={f} selected={selected} toggle={toggle} />
            ))}
          </div>
        </AccordionContent>
      </AccordionItem>

      {hasAnyLineFields ? (
      <AccordionItem value="export-line" className="rounded-lg border border-border px-3">
        <AccordionTrigger className={accordionTriggerClass}>Line items</AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 border-s-2 border-primary/25 ps-3 pb-1">
            {groups.lineDirect.length > 0 ? (
              <div className="space-y-1">
                {groups.lineDirect.map((f) => (
                  <ExportFieldRow key={f.field_key} f={f} selected={selected} toggle={toggle} />
                ))}
              </div>
            ) : null}

            {hasNestedLineGroups ? (
              <div className="rounded-md bg-muted/40 p-2">
                <Accordion
                  type="multiple"
                  defaultValue={[]}
                  variant="outline"
                  className="space-y-2 border-0 bg-transparent p-0 shadow-none"
                >
                  {groups.product.length > 0 ? (
                    <AccordionItem
                      value="export-line-product"
                      className="rounded-md border border-border/80 bg-background px-3"
                    >
                      <AccordionTrigger className={nestedTriggerClass}>
                        Product
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="space-y-1 ps-1">
                          {groups.product.map((f) => (
                            <ExportFieldRow
                              key={f.field_key}
                              f={f}
                              selected={selected}
                              toggle={toggle}
                              sub="product"
                            />
                          ))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ) : null}
                  {groups.warehouse.length > 0 ? (
                    <AccordionItem
                      value="export-line-warehouse"
                      className="rounded-md border border-border/80 bg-background px-3"
                    >
                      <AccordionTrigger className={nestedTriggerClass}>
                        Warehouse
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="space-y-1 ps-1">
                          {groups.warehouse.map((f) => (
                            <ExportFieldRow
                              key={f.field_key}
                              f={f}
                              selected={selected}
                              toggle={toggle}
                              sub="warehouse"
                            />
                          ))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ) : null}
                </Accordion>
              </div>
            ) : null}
          </div>
        </AccordionContent>
      </AccordionItem>
      ) : null}
    </Accordion>
  );
}

export function ListQueryExportDialog({
  resourceKey,
  filename,
  open,
  onOpenChange,
  getPayload,
  selectedRecordIds,
  workflowDefinitionId,
}: ListQueryExportDialogProps) {
  const { data: fields = [], isLoading } = useQuery({
    queryKey: ['list-query-fields', resourceKey, workflowDefinitionId ?? ''],
    queryFn: () =>
      fetchListQueryFields(resourceKey, {
        definitionId:
          resourceKey === 'workflow_form_submissions' ? workflowDefinitionId ?? undefined : undefined,
      }),
    enabled: open,
    staleTime: 60_000,
  });

  const exportable = useMemo(() => fields.filter((f) => f.exportable), [fields]);
  /** DB missing migration 102: only legacy line_product_id / line_warehouse_id exist, not nested attribute columns. */
  const ordersMissingNestedLineFields = useMemo(
    () =>
      resourceKey === 'orders' &&
      exportable.length > 0 &&
      !exportable.some((f) => f.field_key === 'line_product_code'),
    [resourceKey, exportable],
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!open) return;
    setSelected(new Set(exportable.map((f) => f.field_key)));
  }, [open, exportable]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  };

  const selectAll = () => setSelected(new Set(exportable.map((f) => f.field_key)));
  const selectNone = () => setSelected(new Set());

  const handleDownload = async () => {
    if (selected.size === 0) {
      toast.error('Select at least one column');
      return;
    }
    try {
      const base = getPayload();
      const recordIds =
        selectedRecordIds && selectedRecordIds.length > 0 ? selectedRecordIds : undefined;
      const { data } = await postListQueryExport({
        resource: resourceKey,
        fields: Array.from(selected).map((field_key) => ({ field_key })),
        ...base,
        ...(recordIds ? { record_ids: recordIds } : {}),
      });
      const cols: ColumnOption[] = exportable
        .filter((f) => selected.has(f.field_key))
        .map((f) => ({
          key: (f.export_column_name || f.field_key) as string,
          label: f.label,
          selected: true,
        }));
      await generateExcelFile(data, cols, filename || `${resourceKey}_export.xlsx`);
      toast.success(`Exported ${data.length} row(s)`);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          'flex max-h-[90vh] flex-col overflow-hidden',
          resourceKey === 'orders' ? 'max-w-lg' : 'max-w-md',
        )}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="size-4" />
            Export
          </DialogTitle>
          <DialogDescription>
            {selectedRecordIds ? (
              <>
                Exporting <strong>{selectedRecordIds.length}</strong> selected row
                {selectedRecordIds.length === 1 ? '' : 's'}
              </>
            ) : <>Exporting 0 rows. Please select at least 1 record to export.</>}
          </DialogDescription>
        </DialogHeader>

        {!isLoading && ordersMissingNestedLineFields ? (
          <div
            className="shrink-0 rounded-md border border-amber-500/45 bg-amber-500/10 px-3 py-2 text-sm dark:bg-amber-500/15"
            role="status"
          >
            <p className="font-medium text-amber-950 dark:text-amber-50">
              Product &amp; warehouse sub-columns are missing from the database
            </p>
            <p className="mt-1 text-amber-900/90 dark:text-amber-100/90">
              Run backend migration{' '}
              <code className="rounded bg-background/80 px-1 py-0.5 text-xs font-mono">
                102_order_line_nested_export
              </code>{' '}
              (<code className="rounded bg-background/80 px-1 py-0.5 text-xs font-mono">alembic upgrade head</code>
              ), then refresh. Until then you only see the legacy &quot;Line — product&quot; / &quot;Line —
              warehouse&quot; id fields.
            </p>
          </div>
        ) : null}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading columns…</p>
        ) : !exportable.length ? (
          <p className="text-sm text-muted-foreground">No exportable fields.</p>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            <div className="flex shrink-0 gap-2">
              <Button type="button" variant="outline" size="sm" onClick={selectAll}>
                Select all
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={selectNone}>
                Clear
              </Button>
            </div>
            <div
              className="min-h-0 max-h-[min(360px,50vh)] flex-1 overflow-y-auto overscroll-contain rounded-md border p-2"
              role="list"
              aria-label="Columns to export"
            >
              {resourceKey === 'orders' ? (
                <OrdersExportColumnsTree exportable={exportable} selected={selected} toggle={toggle} />
              ) : (
                <div className="space-y-2">
                  {exportable.map((f) => (
                    <ExportFieldRow key={f.field_key} f={f} selected={selected} toggle={toggle} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <DialogFooter className="shrink-0">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleDownload} disabled={isLoading || !exportable.length}>
            Download Excel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
