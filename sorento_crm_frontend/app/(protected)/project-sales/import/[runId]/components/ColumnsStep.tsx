'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  IGNORE_FIELD,
  ImportColumnMapper,
  unresolvedRequiredFields,
  type ImportMappingField,
  type ImportMappingProbe,
  type ImportMappingSelection,
} from '@/components/common/ImportColumnMapper';
import { useProjectImportMutations } from '../../../_shared/hooks/useProjectImport';
import type { ProjectImportRun } from '../../../_shared/types/projectImport.types';

/** The register's fields (PLAN "Field keys"), with their screen labels. */
export const FIELD_LABELS: ImportMappingField[] = [
  { field: 'ps_number', label: 'PS number' },
  { field: 'salesperson', label: 'Salesperson' },
  { field: 'customer_service', label: 'Customer service' },
  { field: 'customer', label: 'Customer' },
  { field: 'project_name', label: 'Project name' },
  { field: 'developer', label: 'Developer' },
  { field: 'po_number', label: 'PO number' },
  { field: 'po_value', label: 'PO value' },
  { field: 'po_date', label: 'PO date' },
  { field: 'amended_date', label: 'Amended date' },
  { field: 'schedule', label: 'Schedule' },
  { field: 'delivery', label: 'Delivery' },
  { field: 'outstanding', label: 'Outstanding' },
  { field: 'so_number', label: 'SO number' },
  { field: 'remarks', label: 'Remarks' },
];

const REQUIRED = ['ps_number', 'customer', 'po_number'];

/** The Columns step (AC-PI-09..11): the headings of the first ticked sheet, one field each. */
export function ColumnsStep({ run }: { run: ProjectImportRun }) {
  const { columns } = useProjectImportMutations(run.id);
  const [picks, setPicks] = React.useState<ImportMappingSelection[]>([]);

  const sheet = React.useMemo(
    () => run.sheets.find((s) => s.ticked && s.has_ps_heading) ?? run.sheets.find((s) => s.has_ps_heading),
    [run.sheets],
  );

  const probe = React.useMemo<ImportMappingProbe>(
    () => ({
      header_row: 1,
      required_fields: REQUIRED,
      columns: (sheet?.columns ?? []).map((c) => ({
        position: c.position,
        header: c.header,
        samples: c.sample ? [c.sample] : [],
        field: c.field,
        source: c.field ? 'shared' : 'none',
      })),
    }),
    [sheet],
  );

  const missing = unresolvedRequiredFields(probe, picks);
  const labelOf = (field: string) => FIELD_LABELS.find((f) => f.field === field)?.label ?? field;

  const save = () => {
    const chosen: Record<string, string> = {};
    for (const pick of picks) {
      if (pick.field) chosen[pick.field] = pick.header;
    }
    if (chosen[IGNORE_FIELD] === undefined) delete chosen[IGNORE_FIELD];
    columns.mutate({
      sheets: run.sheets.filter((s) => s.ticked).map((s) => s.name),
      columns: chosen,
    });
  };

  return (
    <div className="space-y-4">
      <ImportColumnMapper
        probe={probe}
        fields={FIELD_LABELS}
        onChange={setPicks}
        onHeaderRowChange={() => undefined}
        busy={columns.isPending}
      />
      <div className="flex flex-wrap items-center justify-end gap-3">
        {missing.length > 0 && (
          <span className="text-sm text-muted-foreground">
            {`Still needed: ${missing.map(labelOf).join(', ')}`}
          </span>
        )}
        <Button onClick={save} disabled={missing.length > 0 || columns.isPending}>
          Next
        </Button>
      </div>
    </div>
  );
}

export default ColumnsStep;
