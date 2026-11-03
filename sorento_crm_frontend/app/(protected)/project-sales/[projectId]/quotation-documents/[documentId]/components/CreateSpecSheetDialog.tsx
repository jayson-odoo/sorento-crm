'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';

import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { Label } from '@/components/ui/label';

import {
  useSpecSheetMutations,
  useSpecSheets,
} from '../../../../_shared/hooks/useSpecSheet';
import type { SpecSheetTemplateOption } from '../../../../_shared/services/specSheetService';

function templateOptions(rows: SpecSheetTemplateOption[]): SearchableSelectOption[] {
  return rows.map((row) => ({
    value: row.id,
    label:
      row.width_mm && row.height_mm
        ? `${row.name} (${row.width_mm} x ${row.height_mm} mm)`
        : row.name,
  }));
}

interface Picked {
  source?: string;
  cover?: string;
  page?: string;
  single?: string;
}

/**
 * Create spec sheet: the revision (the draft first when it is ahead of the last issue), the cover
 * and page templates, and an optional single item template. Options and defaults come from the
 * list read; nothing else is fetched. On success the new sheet opens.
 */
export function CreateSpecSheetDialog({
  open,
  onOpenChange,
  projectId,
  documentId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  documentId: string;
}) {
  const router = useRouter();
  const list = useSpecSheets(projectId, documentId);
  const { create } = useSpecSheetMutations(projectId, documentId);
  const [picked, setPicked] = React.useState<Picked>({});
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) {
      setPicked({});
      setError(null);
    }
  }, [open]);

  const data = list.data;
  const defaults = data?.defaults;
  // A cleared Single item template is '' and must not fall back to the default.
  const source = picked.source ?? defaults?.source ?? '';
  const cover = picked.cover ?? defaults?.cover_template_id ?? '';
  const page = picked.page ?? defaults?.page_template_id ?? '';
  const single = picked.single ?? defaults?.single_page_template_id ?? '';

  const sourceOptions = React.useMemo<SearchableSelectOption[]>(
    () =>
      (data?.sources ?? []).map((row) => ({
        value: row.value,
        label: row.label,
        description: row.hint,
      })),
    [data?.sources],
  );
  const coverOptions = React.useMemo(() => templateOptions(data?.templates.cover ?? []), [data]);
  const pageOptions = React.useMemo(() => templateOptions(data?.templates.page ?? []), [data]);

  const ids = {
    source: 'spec-sheet-source',
    cover: 'spec-sheet-cover',
    page: 'spec-sheet-page',
    single: 'spec-sheet-single',
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!source) return setError('Pick a revision.');
    if (!cover || !page) return setError('Pick a cover template and a page template.');
    setError(null);
    create.mutate(
      {
        source,
        cover_template_id: cover,
        page_template_id: page,
        single_page_template_id: single || null,
      },
      {
        onSuccess: (sheet) => {
          onOpenChange(false);
          router.push(
            `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet/${sheet.id}`,
          );
        },
        onError: (err: Error) => setError(err.message),
      },
    );
  };

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title="Create spec sheet"
      submitLabel="Create"
      isPending={create.isPending}
      error={error}
      onSubmit={submit}
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.source}>Revision</Label>
        <SearchableSelect
          id={ids.source}
          value={source}
          onChange={(value: string) => setPicked((p) => ({ ...p, source: value }))}
          options={sourceOptions}
          placeholder="Pick a revision"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.cover}>Cover template</Label>
        <SearchableSelect
          id={ids.cover}
          value={cover}
          onChange={(value: string) => setPicked((p) => ({ ...p, cover: value }))}
          options={coverOptions}
          placeholder="Pick a cover"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.page}>Page template</Label>
        <SearchableSelect
          id={ids.page}
          value={page}
          onChange={(value: string) => setPicked((p) => ({ ...p, page: value }))}
          options={pageOptions}
          placeholder="Pick a page"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.single}>Single item template</Label>
        <SearchableSelect
          id={ids.single}
          clearable
          value={single}
          onChange={(value: string) => setPicked((p) => ({ ...p, single: value }))}
          options={pageOptions}
          placeholder="Same as page template"
        />
      </div>
    </FormDialogScaffold>
  );
}
