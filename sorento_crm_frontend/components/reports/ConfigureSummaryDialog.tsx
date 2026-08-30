'use client';

import { useEffect, useMemo, useState } from 'react';
import { Label } from '@/components/ui/label';
import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import type { ReportCatalogColumn, ReportViewConfig } from '@/services/reportService';

type PivotConfig = ReportViewConfig['pivot'];

/**
 * Rows / Columns / Measures, straight off the dataset catalog. This is the whole of
 * "reshape the summary without a developer": agent by month is only the default, and
 * sponsor project by delivery year is one dialog away.
 */
export function ConfigureSummaryDialog({
  open,
  onOpenChange,
  catalog,
  value,
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  catalog: ReportCatalogColumn[];
  value: PivotConfig;
  onApply: (next: PivotConfig) => void;
}) {
  const [draft, setDraft] = useState<PivotConfig>(value);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDraft(value);
      setError(null);
    }
  }, [open, value]);

  const dimensionOptions = useMemo(
    () =>
      catalog
        .filter((c) => c.tag === 'dimension')
        .map((c) => ({ value: c.key, label: c.label })),
    [catalog],
  );
  const measureOptions = useMemo(
    () => catalog.filter((c) => c.tag === 'measure').map((c) => ({ value: c.key, label: c.label })),
    [catalog],
  );

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.rows) {
      setError('Pick a row dimension.');
      return;
    }
    if (!draft.cols) {
      setError('Pick a column dimension.');
      return;
    }
    if (draft.rows === draft.cols) {
      setError('Rows and Columns must be different.');
      return;
    }
    if (draft.measures.length === 0) {
      setError('Pick at least one measure.');
      return;
    }
    onApply(draft);
    onOpenChange(false);
  };

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title="Configure summary"
      submitLabel="Apply"
      onSubmit={submit}
      error={error}
    >
      <div>
        <Label htmlFor="summary-rows">Rows</Label>
        <SearchableSelect
          id="summary-rows"
          value={draft.rows}
          onChange={(next) => setDraft((prev) => ({ ...prev, rows: next }))}
          options={dimensionOptions}
          placeholder="Row dimension"
          triggerClassName="mt-1 w-full"
        />
      </div>
      <div>
        <Label htmlFor="summary-cols">Columns</Label>
        <SearchableSelect
          id="summary-cols"
          value={draft.cols}
          onChange={(next) => setDraft((prev) => ({ ...prev, cols: next }))}
          options={dimensionOptions}
          placeholder="Column dimension"
          triggerClassName="mt-1 w-full"
        />
      </div>
      <div>
        <Label htmlFor="summary-measures">Measures</Label>
        <SearchableMultiSelect
          id="summary-measures"
          value={draft.measures}
          onChange={(next) => setDraft((prev) => ({ ...prev, measures: next }))}
          options={measureOptions}
          placeholder="Measures"
          triggerClassName="mt-1 w-full"
        />
      </div>
    </FormDialogScaffold>
  );
}
