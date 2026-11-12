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

const REQUIRED = ['ps_number', 'customer', 'po_number'];

/** The Columns step (AC-PI-09..11): the headings of the first ticked sheet, one field each. */
export function ColumnsStep({ run }: { run: ProjectImportRun }) {
  const { columns } = useProjectImportMutations(run.id);
  // The field list and its words come from the server (`field_labels`); no copy here.
  const fields = React.useMemo<ImportMappingField[]>(
    () => Object.entries(run.field_labels ?? {}).map(([field, label]) => ({ field, label })),
    [run.field_labels],
  );
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
  const labelOf = (field: string) => run.field_labels?.[field] ?? field;

  // A field the server holds a heading for keeps it unless sent (round 4), so a field the
  // person took away (its column set to Ignore) is sent as "ignore"; every pick is sent as is.
  // Pressing Next on the auto-match sends the same headings back.
  const save = () => {
    const chosen: Record<string, string> = {};
    for (const pick of picks) {
      if (pick.field && pick.field !== IGNORE_FIELD) chosen[pick.field] = pick.header;
    }
    for (const field of Object.keys(run.columns ?? {})) {
      if (!(field in chosen)) chosen[field] = IGNORE_FIELD;
    }
    columns.mutate({
      sheets: run.sheets.filter((s) => s.ticked).map((s) => s.name),
      columns: chosen,
    });
  };

  return (
    <div className="space-y-4">
      <ImportColumnMapper
        probe={probe}
        fields={fields}
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
