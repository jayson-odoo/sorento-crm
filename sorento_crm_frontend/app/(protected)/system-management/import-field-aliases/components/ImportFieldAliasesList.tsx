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
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { pendingEntityKey, usePendingEntityKeys } from '@/lib/pending-entity-store';
import {
  importFieldAliasListQueryKey,
  useImportFieldAliases,
} from '../hooks/useImportFieldAliases';
import { IMPORT_FIELD_ALIAS_DOC_TYPES } from '../types/importFieldAlias.types';
import type { ImportFieldAliasDocType, ImportFieldAliasGroup } from '../types/importFieldAlias.types';
import { ImportFieldAliasFormDialog } from './ImportFieldAliasFormDialog';

/** One frozen empty array while the query is in flight: TanStack reads `data` by identity
 *  and a fresh `[]` per render is a render loop with a clean console
 *  (`data-grid.stable-data.inventory.test.ts`, and this page's own measured 100% CPU on a
 *  doc-type switch). */
const NO_GROUPS: ImportFieldAliasGroup[] = [];

/**
 * Import column mappings (S5, AC-E3): per document type, every system field and the
 * headers on file that resolve to it. A chip's × parks a deferred `import_field_alias
 * .forget` on the SERVER (`useDeferredRowAction`), which commits when the window lapses
 * even if this tab is closed; a mapping is a small, frequently-corrected fact, so the
 * countdown lives in a toast the same way a list row's delete does, not a confirmation
 * dialog.
 */
export default function ImportFieldAliasesList() {
  const [docType, setDocType] = useState<ImportFieldAliasDocType>('proforma_invoice');
  const { data: groups, isLoading } = useImportFieldAliases(docType);
  const [addOpen, setAddOpen] = useState(false);
  const removal = useDeferredRowAction({
    actionKey: 'import_field_alias.forget',
    entityType: 'import_field_alias',
    verb: 'Removing',
    successMessage: 'Mapping removed',
    invalidateKeys: [importFieldAliasListQueryKey(docType)],
  });
  // Which chips are counting down - read from the tab's pending store rather than a local
  // set, so a cancelled window puts the chip back with nothing here to undo.
  const pendingKeys = usePendingEntityKeys();

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
          const visible = row.original.aliases.filter(
            (a) => !pendingKeys.has(pendingEntityKey('import_field_alias', a.id)),
          );
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
                    onClick={() =>
                      removal.run({
                        id: a.id,
                        subject: `"${a.alias}" from ${row.original.label}`,
                      })
                    }
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
    [pendingKeys, removal],
  );

  const table = useReactTable({
    columns,
    data: groups ?? NO_GROUPS,
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
