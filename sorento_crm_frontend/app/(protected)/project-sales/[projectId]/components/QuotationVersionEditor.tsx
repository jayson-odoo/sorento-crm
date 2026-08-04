'use client';

import * as React from 'react';
import { AlertTriangle, Lock, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
// The shared products `/select` mapper. Its name says "variant" because that screen
// needed it first; the endpoint and the shape are the generic ones.
import { useUOMSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query';
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import {
  useQuotationLineMutations,
  useQuotationLines,
  useQuotationVersions,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectQuotation,
  QuotationLine,
  UnitType,
} from '../../_shared/types/project.types';
import {
  InlineLineTable,
  type InlineDraft,
  type InlineLineColumn,
} from '../../_shared/components/InlineLineTable';
import { ReviseQuotationDialog } from './ReviseQuotationDialog';
import { formatMyr } from './QuotationsPanel';
import { isDecimalString, multiplyMoney } from './POIntakeMoney';

const FLOOR_LEVEL_LABELS: Record<string, string> = {
  product: 'this product',
  category: 'its category',
  category_ancestor: 'a parent category',
  system: 'the company default',
};

const UNIT_TYPE_OPTIONS: { value: UnitType; label: string; description: string }[] = [
  { value: 'house_unit', label: 'Per house unit', description: 'Multiplied by the unit count' },
  { value: 'bathroom', label: 'Per bathroom', description: 'Multiplied by bathrooms per unit' },
  { value: 'facility', label: 'Per facility', description: 'Gym, pool, surau' },
  { value: 'common_area', label: 'Common area', description: 'Priced once for the whole site' },
];

/**
 * The versions of one scope, and the lines of whichever version is being looked at.
 *
 * Only the newest version is editable, and the editor works that out from the server's
 * `is_current` rather than from a local guess. Everything below it is history the
 * customer already holds (AC-E3), so an older version renders read-only with the reason
 * stated, not merely with its buttons missing.
 */
export function QuotationVersionEditor({
  project,
  quotation,
}: {
  project: Project;
  quotation: ProjectQuotation;
}) {
  const versions = useQuotationVersions(quotation.id);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [revising, setRevising] = React.useState(false);

  const rows = React.useMemo(
    () => [...(versions.data ?? [])].sort((a, b) => b.version_no - a.version_no),
    [versions.data],
  );
  const current = rows.find((version) => version.is_current) ?? null;
  const selected = rows.find((version) => version.id === selectedId) ?? current;

  const lines = useQuotationLines(selected?.id);
  const lineMutations = useQuotationLineMutations(project.id, selected?.id ?? '');

  // `is_editable` from the server, NOT `is_current`. An issued version is still the highest
  // version until somebody revises, so gating on `is_current` left the fields open on a
  // quotation the customer already holds: the user typed a price, the server refused with 422,
  // and the number stayed on screen looking saved.
  const editable = Boolean(selected?.is_editable ?? selected?.is_current) && project.can_edit;
  const sortedLines = React.useMemo(
    () => [...(lines.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [lines.data],
  );
  const nextSortOrder =
    sortedLines.length === 0
      ? 0
      : Math.max(...sortedLines.map((line) => line.sort_order)) + 10;

  // The line stores the CODE, not the id, so the option value is the code. Cached with an
  // infinite staleTime by the shared hook, so opening five versions costs one request.
  const uoms = useUOMSelectQuery();
  const uomOptions = React.useMemo(
    () =>
      (uoms.data ?? []).map((unit) => ({
        value: unit.uom_code,
        label: unit.uom_code,
        description: unit.uom_name,
      })),
    [uoms.data],
  );

  const fetchProducts = React.useCallback(async (query: string) => {
    const products = await getProductsForVariantSelect(query || undefined);
    return products.map((product) => ({
      value: product.id,
      label: product.product_code,
      description: product.product_name,
    }));
  }, []);

  const columns = React.useMemo<InlineLineColumn<QuotationLine>[]>(
    () => [
      {
        key: 'product_id',
        header: 'Product',
        width: 200,
        kind: 'searchable-select',
        placeholder: 'Off-catalog line',
        fetchOptions: fetchProducts,
        // Async mode fetches a page at a time, so the line's own product has to be handed
        // in or a saved row would read as empty until somebody searched for it.
        resolveSelected: (line) =>
          line?.product_id
            ? {
                value: line.product_id,
                label: line.product_code ?? 'Selected product',
                description: line.description ?? undefined,
              }
            : undefined,
        annotate: (line) => (line ? <LineFlags line={line} /> : null),
      },
      {
        key: 'description',
        header: 'Description',
        width: 240,
        kind: 'text',
        placeholder: "The product's own description",
      },
      {
        key: 'quantity',
        header: 'Qty',
        width: 96,
        kind: 'number',
        align: 'end',
        validate: (value) =>
          value.trim() === '' || isDecimalString(value) ? null : 'Must be a number',
        formatReadOnly: (value) => trimAmount(value),
      },
      {
        key: 'uom',
        header: 'UOM',
        width: 110,
        // A dropdown off the master list, not free text: a line typed "pcs" and another
        // "PCS" are the same unit to a reader and two different strings to every report.
        kind: 'select',
        placeholder: 'PCS',
        options: uomOptions,
        resolveSelected: (_line, draft) =>
          uomOptions.find((option) => option.value === draft.uom),
      },
      {
        key: 'unit_price',
        header: 'Unit price',
        width: 128,
        kind: 'number',
        align: 'end',
        placeholder: '0.00',
        validate: (value) =>
          value.trim() === '' || isDecimalString(value) ? null : 'Must be a number',
        formatReadOnly: (value) => formatMyr(value),
        annotate: (line) =>
          line?.list_price ? (
            <span className="mt-0.5 block text-end text-xs text-muted-foreground">
              {`List ${formatMyr(line.list_price)}`}
            </span>
          ) : null,
      },
      {
        key: 'unit_type',
        header: 'Counts per',
        width: 168,
        kind: 'select',
        placeholder: 'Not counted per unit',
        options: UNIT_TYPE_OPTIONS,
        resolveSelected: (_line, draft) =>
          UNIT_TYPE_OPTIONS.find((option) => option.value === draft.unit_type),
      },
      {
        key: 'line_total',
        header: 'Total',
        width: 128,
        kind: 'derived',
        align: 'end',
        // Recomputed from the draft rather than read off the row, so the number moves
        // while a quantity is being typed instead of after the save lands.
        derive: (draft) => formatMyr(multiplyMoney(draft.quantity, draft.unit_price) ?? '0'),
      },
    ],
    [fetchProducts, uomOptions],
  );

  const toDraft = React.useCallback(
    (line: QuotationLine): InlineDraft => ({
      product_id: line.product_id ?? '',
      description: line.description ?? '',
      quantity: line.quantity ?? '1',
      uom: line.uom ?? '',
      unit_price: line.unit_price ?? '',
      unit_type: line.unit_type ?? '',
      notes: line.notes ?? '',
    }),
    [],
  );

  const emptyDraft = React.useCallback(
    (): InlineDraft => ({
      product_id: '',
      description: '',
      quantity: '1',
      uom: '',
      unit_price: '',
      unit_type: '',
      notes: '',
    }),
    [],
  );

  if (versions.isLoading) return <Skeleton className="h-24 w-full" />;

  // `min-w-0` so a wide line table scrolls in its own gutter instead of stretching the
  // panel it sits in, which at 375px would take the whole page sideways with it.
  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {rows.map((version) => (
            <button
              key={version.id}
              type="button"
              onClick={() => setSelectedId(version.id)}
              aria-current={selected?.id === version.id}
              className={
                selected?.id === version.id
                  ? 'rounded-md border border-primary bg-primary/10 px-2.5 py-1 text-xs font-medium'
                  : 'rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted'
              }
            >
              {`v${version.version_no}`}
              {version.is_current ? '' : ' (frozen)'}
            </button>
          ))}
        </div>

        {project.can_edit && current && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setRevising(true)}
          >
            {`Revise to v${current.version_no + 1}`}
          </Button>
        )}
      </div>

      {selected && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">
            {formatMyr(selected.total_amount)}
          </span>
          {selected.issued_by_name && <span>Issued by {selected.issued_by_name}</span>}
          {selected.created_at && (
            <span>Opened {formatDateTimeInMalaysia(selected.created_at)}</span>
          )}
          {!selected.is_current && selected.frozen_at && (
            <span className="flex items-center gap-1">
              <Lock className="size-3" aria-hidden />
              Frozen {formatDateTimeInMalaysia(selected.frozen_at)}
            </span>
          )}
          {selected.is_issued && (
            <span className="flex items-center gap-1">
              <Lock className="size-3" aria-hidden />
              Issued to the customer
            </span>
          )}
        </div>
      )}

      {/* Why this version is read only, in one line. The reasoning behind freezing a
          version was a paragraph and is now simply the consequence. */}
      {selected && selected.is_issued && (
        <p className="text-xs text-muted-foreground">
          The customer holds this version, so its lines cannot be changed. Open a revision to
          re-price it.
        </p>
      )}

      {selected && !selected.is_current && (
        <p className="text-xs text-muted-foreground">
          {`Frozen. Make changes on ${current ? `v${current.version_no}` : 'the current version'}.`}
        </p>
      )}

      <InlineLineTable<QuotationLine>
        rows={sortedLines}
        getRowId={(line) => line.id}
        columns={columns}
        toDraft={toDraft}
        emptyDraft={emptyDraft}
        readOnly={!editable}
        isLoading={lines.isLoading}
        addLabel="Add a line"
        emptyHint={
          editable
            ? 'Nothing quoted yet. Add a line and pick a product to freeze its code, description and list price onto it.'
            : 'This version was frozen without any lines.'
        }
        describeRow={(line, index) =>
          line?.product_code ?? line?.description ?? `line ${index + 1}`
        }
        rowDetail={{
          key: 'notes',
          label: 'Notes',
          placeholder: 'Why this price, what was agreed, what it replaces',
        }}
        // Off-catalog lines carry the description the customer reads, so it is the one
        // thing that cannot be left out.
        validateRow={(draft): Record<string, string> =>
          !draft.product_id && !draft.description.trim()
            ? { description: 'Needed on an off-catalog line' }
            : {}
        }
        onCreate={async (draft) => {
          await lineMutations.create.mutateAsync({
            ...toBody(draft),
            sort_order: nextSortOrder,
          });
        }}
        onUpdate={async (line, draft) => {
          await lineMutations.update.mutateAsync({ id: line.id, body: toBody(draft) });
        }}
        onDelete={async (line) => {
          await lineMutations.remove.mutateAsync(line.id);
        }}
        deleteDescription={(line) =>
          `Remove "${line.product_code ?? line.description}" from v${selected?.version_no}? This action cannot be undone.`
        }
      />

      {revising && current && (
        <ReviseQuotationDialog
          projectId={project.id}
          quotation={quotation}
          currentVersionNo={current.version_no}
          lineCount={sortedLines.length}
          onDone={(newVersionId) => {
            setRevising(false);
            // Land on the version that was just opened, not the one being read a moment ago.
            if (newVersionId) setSelectedId(newVersionId);
          }}
        />
      )}

    </div>
  );
}

/**
 * What the server decided about the line, on the line.
 *
 * The floor is deliberately NOT evaluated in the browser: resolving it means walking the
 * category ancestry, and a second implementation here would eventually disagree with the
 * server's. The price is sent, and the answer that comes back is what is shown.
 */
function LineFlags({ line }: { line: QuotationLine }) {
  const anything = !line.product_id || line.is_below_floor || line.is_non_standard;
  if (!anything) return null;

  return (
    <div className="mt-1 space-y-0.5">
      <div className="flex flex-wrap items-center gap-1">
        {!line.product_id && (
          <Badge variant="outline" className="text-[11px]">
            Off-catalog
          </Badge>
        )}
        {line.is_below_floor && (
          <Badge variant="destructive" className="gap-1 text-[11px]" title={describeFloor(line)}>
            <AlertTriangle className="size-3" aria-hidden />
            Below floor
          </Badge>
        )}
        {line.is_non_standard && (
          <Badge
            variant="secondary"
            className="gap-1 text-[11px]"
            title="Outside the series this scope is quoted from"
          >
            <TriangleAlert className="size-3" aria-hidden />
            Non-standard
          </Badge>
        )}
      </div>
      {line.is_below_floor && (
        <p className="text-xs text-destructive">{describeFloor(line)}</p>
      )}
    </div>
  );
}

/** Draft to the body the per-line endpoint already takes. Unchanged from the dialog. */
function toBody(draft: InlineDraft) {
  return {
    product_id: draft.product_id || null,
    description_snapshot: draft.description.trim() || null,
    unit_price: draft.unit_price.trim() || '0',
    quantity: draft.quantity.trim() || '1',
    uom: draft.uom.trim() || null,
    unit_type: (draft.unit_type || null) as UnitType | null,
    notes: draft.notes.trim() || null,
  };
}

/** Says which rule bit, so the salesperson knows whose policy to argue with. */
function describeFloor(line: QuotationLine): string {
  if (!line.floor_value_applied) return 'Below the floor for this item.';
  const level = line.floor_level_applied
    ? FLOOR_LEVEL_LABELS[line.floor_level_applied] ?? line.floor_level_applied
    : 'policy';
  return `Floor was ${formatMyr(line.floor_value_applied)}, set on ${level}.`;
}

/** Quantities come back as "2.00"; nobody writes two bathrooms as 2.00. */
function trimAmount(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return String(amount);
}
