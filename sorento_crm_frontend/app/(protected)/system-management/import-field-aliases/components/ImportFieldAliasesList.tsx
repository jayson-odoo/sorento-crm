'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useMockDeferredWindow } from '@/hooks/useMockDeferredWindow';
import {
  deleteImportFieldAlias,
  importFieldAliasListQueryKey,
  useImportFieldAliases,
} from '../hooks/useImportFieldAliases';
import { IMPORT_FIELD_ALIAS_DOC_TYPES } from '../types/importFieldAlias.types';
import type { ImportFieldAliasDocType, ImportFieldAliasGroup } from '../types/importFieldAlias.types';
import { ImportFieldAliasFormDialog } from './ImportFieldAliasFormDialog';
import { useQueryClient } from '@tanstack/react-query';

/**
 * Import column mappings (S5, AC-E3): per document type, every system field and the
 * headers on file that resolve to it. A chip's × parks a deferred delete
 * (`useMockDeferredWindow`, Phase 1 stand-in for `useDeferredRowAction` - see that
 * hook's own comment) rather than removing the row outright; a mapping is a small,
 * frequently-corrected fact, so the countdown lives in a toast the same way a list row's
 * delete does, not a confirmation dialog.
 */
export default function ImportFieldAliasesList() {
  const [docType, setDocType] = useState<ImportFieldAliasDocType>('proforma_invoice');
  const { data: groups, isLoading } = useImportFieldAliases(docType);
  const [addOpen, setAddOpen] = useState(false);
  const qc = useQueryClient();
  const deferred = useMockDeferredWindow(5);
  // Optimistically hidden the instant × is pressed - the toast is the undo, not this list.
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set());

  const removeAlias = (id: string, field: string, alias: string) => {
    setRemovedIds((prev) => new Set(prev).add(id));
    deferred.run({
      id,
      entityType: 'import_field_alias',
      apply: () => {
        void deleteImportFieldAlias(id).then(() =>
          qc.invalidateQueries({ queryKey: importFieldAliasListQueryKey(docType) }),
        );
      },
      undo: () => {
        setRemovedIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      },
      toast: { verb: 'Removing', subject: `"${alias}" from ${field}` },
    });
  };

  const columns = useMemo<ColumnDef<ImportFieldAliasGroup>[]>(
    () => [
      {
        accessorKey: 'label',
        header: ({ column }) => <DataGridColumnHeader title="System field" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.label}</span>,
        size: 200,
      },
      {
        id: 'aliases',
        header: () => 'Headers on file',
        cell: ({ row }) => {
          const visible = row.original.aliases.filter((a) => !removedIds.has(a.id));
          if (!visible.length) {
            return <span className="text-xs text-muted-foreground">No header maps here yet.</span>;
          }
          return (
            <div className="flex flex-wrap gap-1.5 py-1">
              {visible.map((a) => (
                <Badge key={a.id} variant="secondary" appearance="light" size="sm" className="gap-1">
                  {a.alias}
                  {a.locale ? <span className="text-muted-foreground">({a.locale})</span> : null}
                  <button
                    type="button"
                    aria-label={`Remove ${a.alias}`}
                    className="ms-0.5 rounded-full hover:bg-muted"
                    onClick={() => removeAlias(a.id, row.original.label, a.alias)}
                  >
                    <X className="size-3" />
                  </button>
                </Badge>
              ))}
            </div>
          );
        },
        size: 480,
        enableSorting: false,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [removedIds],
  );

  const table = useReactTable({
    columns,
    data: groups ?? [],
    getRowId: (row) => row.field,
    getCoreRowModel: getCoreRowModel(),
  });

  const addButton = (
    <Button onClick={() => setAddOpen(true)}>
      <Plus className="size-4" />
      Add mapping
    </Button>
  );

  return (
    <>
      <div className="mb-4 max-w-xs">
        <Label htmlFor="import-field-alias-doc-type" className="mb-1 block text-xs">
          Document type
        </Label>
        <SearchableSelect
          id="import-field-alias-doc-type"
          value={docType}
          onChange={(v: string) => setDocType(v as ImportFieldAliasDocType)}
          options={IMPORT_FIELD_ALIAS_DOC_TYPES}
        />
      </div>
      <DataGrid
        table={table}
        recordCount={groups?.length ?? 0}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyAction={addButton}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar table={table} primaryAction={addButton} />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>
      <ImportFieldAliasFormDialog open={addOpen} onOpenChange={setAddOpen} docType={docType} />
    </>
  );
}
