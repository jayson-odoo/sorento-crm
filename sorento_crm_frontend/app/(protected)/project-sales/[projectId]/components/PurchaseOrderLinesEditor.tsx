'use client';

import * as React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
// The shared products `/select` mapper. Its name says "variant" because that screen
// needed it first; the endpoint and the shape are the generic ones.
import { useUOMSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query';
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import {
  usePurchaseOrderLineMutations,
  usePurchaseOrderLines,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectPurchaseOrder,
  PurchaseOrderLine,
} from '../../_shared/types/project.types';
import {
  InlineLineTable,
  type InlineDraft,
  type InlineLineColumn,
} from '../../_shared/components/InlineLineTable';
import { formatMyr } from './QuotationsPanel';
import { isDecimalString, multiplyMoney } from './POIntakeMoney';

/**
 * The lines of one PO, entered like a spreadsheet, with what each one was quoted at
 * beside what was ordered.
 *
 * Showing both numbers on the same row is the point: "price differs" on its own sends
 * the user hunting through the quotation, and the difference is usually the thing they
 * want to talk to the contractor about within the next ten minutes.
 */
export function PurchaseOrderLinesEditor({
  project,
  po,
}: {
  project: Project;
  po: ProjectPurchaseOrder;
}) {
  const lines = usePurchaseOrderLines(po.id);
  const { create, update, remove } = usePurchaseOrderLineMutations(project.id, po.id);

  const rows = React.useMemo(
    () => [...(lines.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [lines.data],
  );
  const nextSortOrder =
    rows.length === 0 ? 0 : Math.max(...rows.map((line) => line.sort_order)) + 10;
  const editable = project.can_edit;

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

  const columns = React.useMemo<InlineLineColumn<PurchaseOrderLine>[]>(
    () => [
      {
        key: 'product_id',
        header: 'Our product',
        width: 190,
        kind: 'searchable-select',
        // Optional on purpose: contractors order using their own codes, and forcing a
        // match at entry time would mean either a wrong match or an unrecordable PO. An
        // unmatched line is recorded and flagged instead (AC-F9).
        placeholder: 'Not matched',
        fetchOptions: fetchProducts,
        resolveSelected: (line) =>
          line?.product_id
            ? { value: line.product_id, label: line.product_code ?? 'Selected product' }
            : undefined,
        annotate: (line) => (line ? <LineFlags line={line} /> : null),
      },
      {
        key: 'product_code',
        header: 'Code on the PO',
        width: 150,
        kind: 'text',
        placeholder: 'What their document calls it',
      },
      {
        key: 'description',
        header: 'Description',
        width: 230,
        kind: 'text',
        placeholder: 'As written on the PO',
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
        // Same dropdown the quotation editor uses: "pcs" and "PCS" are one unit to a reader
        // and two strings to every report.
        kind: 'select',
        placeholder: 'PCS',
        options: uomOptions,
        resolveSelected: (_line, draft) =>
          uomOptions.find((option) => option.value === draft.uom),
      },
      {
        key: 'unit_price',
        header: 'Ordered at',
        width: 128,
        kind: 'number',
        align: 'end',
        placeholder: '0.00',
        validate: (value) =>
          value.trim() === '' || isDecimalString(value) ? null : 'Must be a number',
        formatReadOnly: (value) => formatMyr(value),
        annotate: (line) =>
          line?.quoted_unit_price ? (
            <span
              className={
                line.price_mismatch
                  ? 'mt-0.5 block text-end text-xs text-destructive'
                  : 'mt-0.5 block text-end text-xs text-muted-foreground'
              }
            >
              {`Quoted ${formatMyr(line.quoted_unit_price)}`}
            </span>
          ) : null,
      },
      {
        key: 'line_total',
        header: 'Total',
        width: 128,
        kind: 'derived',
        align: 'end',
        derive: (draft) => formatMyr(multiplyMoney(draft.quantity, draft.unit_price) ?? '0'),
      },
    ],
    [fetchProducts, uomOptions],
  );

  const toDraft = React.useCallback(
    (line: PurchaseOrderLine): InlineDraft => ({
      product_id: line.product_id ?? '',
      product_code: line.product_code ?? '',
      description: line.description ?? '',
      quantity: line.quantity ?? '1',
      uom: line.uom ?? '',
      unit_price: line.unit_price ?? '',
      notes: line.notes ?? '',
    }),
    [],
  );

  const emptyDraft = React.useCallback(
    (): InlineDraft => ({
      product_id: '',
      product_code: '',
      description: '',
      quantity: '1',
      uom: '',
      unit_price: '',
      notes: '',
    }),
    [],
  );

  return (
    <div className="min-w-0 space-y-3">
      {/* A real risk signal, not a lesson: without a bound version nothing on these lines
          is checked, and a clean-looking table would say the opposite. One line, no
          paragraph. */}
      {!po.quotation_version_id && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="size-3.5 shrink-0 text-amber-600" aria-hidden />
          Not tied to a quotation version, so no price is checked.
        </p>
      )}

      <InlineLineTable<PurchaseOrderLine>
        rows={rows}
        getRowId={(line) => line.id}
        columns={columns}
        toDraft={toDraft}
        emptyDraft={emptyDraft}
        readOnly={!editable}
        isLoading={lines.isLoading}
        addLabel="Add a line"
        emptyHint={
          editable
            ? 'No lines entered. Add one and it is checked against the quoted version.'
            : 'This PO was recorded as a single amount with no line detail.'
        }
        describeRow={(line, index) =>
          line?.product_code ?? line?.description ?? `line ${index + 1}`
        }
        rowDetail={{
          key: 'notes',
          label: 'Notes',
          placeholder: 'Why the price or the model differs, if it does',
        }}
        validateRow={(draft): Record<string, string> =>
          !draft.product_id && !draft.product_code.trim()
            ? { product_code: 'Needed when no product is matched' }
            : {}
        }
        onCreate={async (draft) => {
          await create.mutateAsync({ ...toBody(draft), sort_order: nextSortOrder });
        }}
        onUpdate={async (line, draft) => {
          await update.mutateAsync({ id: line.id, body: toBody(draft) });
        }}
        onDelete={async (line) => {
          await remove.mutateAsync(line.id);
        }}
        deleteDescription={(line) =>
          `Remove "${line.product_code ?? line.description ?? 'this line'}" from ${po.po_number}? This action cannot be undone.`
        }
      />
    </div>
  );
}

/** What the check against the quoted version found, on the line it found it on. */
function LineFlags({ line }: { line: PurchaseOrderLine }) {
  if (!line.model_mismatch && !line.price_mismatch) return null;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {line.model_mismatch && (
        <Badge
          variant="destructive"
          className="gap-1 text-[11px]"
          title="This item does not appear on the quoted version"
        >
          <AlertTriangle className="size-3" aria-hidden />
          Not quoted
        </Badge>
      )}
      {line.price_mismatch && (
        <Badge variant="destructive" className="text-[11px]">
          Price differs
        </Badge>
      )}
    </div>
  );
}

/** Draft to the body the per-line endpoint already takes. Unchanged from the dialog. */
function toBody(draft: InlineDraft) {
  return {
    product_id: draft.product_id || null,
    product_code: draft.product_code.trim() || null,
    description: draft.description.trim() || null,
    unit_price: draft.unit_price.trim() || '0',
    quantity: draft.quantity.trim() || '1',
    uom: draft.uom.trim() || null,
    notes: draft.notes.trim() || null,
  };
}

function trimAmount(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return String(amount);
}
