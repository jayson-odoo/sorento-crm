'use client';

import * as React from 'react';
import { AlertTriangle, Lock, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useUOMSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
// The shared products `/select` mapper, keeping the fields a picked product decides.
import { getProductsForLineSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import type { ProductLineRef } from '@/app/(protected)/master-data-management/products/types/product.types';
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
  INLINE_CHECKED,
  isInlineChecked,
  type InlineDraft,
  type InlineLineColumn,
} from '../../_shared/components/InlineLineTable';
import { ReviseQuotationDialog } from './ReviseQuotationDialog';
import { formatMyr } from './QuotationsPanel';
import { formatMyrExact, isDecimalString, multiplyMoney, sumMoney } from './POIntakeMoney';

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
  onTotalChange,
}: {
  project: Project;
  quotation: ProjectQuotation;
  /**
   * The scope's live quoted total, as a decimal STRING (`"9000.00"`), whenever it moves.
   *
   * For a header that sits outside this editor and must not disagree with the footer inside
   * it. Fired off the same drafts the footer sums, so the two cannot drift: rate-only lines
   * contribute nothing, and an uncommitted keystroke counts. Unformatted on purpose - the
   * header decides how to print it.
   */
  onTotalChange?: (total: string) => void;
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
  // The line snapshots the brand as TEXT (what was quoted, not who owns the SKU today), so the
  // product's brand_id has to be resolved to a name before it can go on a row. Same cached
  // master-data hook the rest of the app uses; no UUID reaches the cell.
  const brands = useBrandSelectQuery();

  /**
   * The products the picker has shown, by id.
   *
   * The dropdown already holds the whole record when somebody chooses one, so the fill reads it
   * from here instead of asking the server again for a row it just rendered.
   */
  const productsById = React.useRef(new Map<string, ProductLineRef>());

  const fetchProducts = React.useCallback(async (query: string) => {
    const products = await getProductsForLineSelect(query || undefined);
    products.forEach((product) => productsById.current.set(product.id, product));
    return products.map((product) => ({
      value: product.id,
      label: product.product_code,
      description: product.product_name,
    }));
  }, []);

  /**
   * What picking a product decides for the rest of its line.
   *
   * Every one of these fields is the product's, so a line quoting SRT-WC-01 reads the same
   * whoever typed it. The shared table applies this AS STATED, over hand-typed text included
   * (the client's call: one product, one set of fields, every time), so this returns a key even
   * when the product has nothing for it - that is how the previous product's wording is cleared.
   *
   * `list_price` has no column: it is the annotation under the unit price, and it must follow
   * the product from the moment it is picked rather than waiting for the save to come back.
   *
   * NOT filled, both deliberately:
   * - `technical_spec`. The client asked for it, and the products table has no such column -
   *   only the quotation line does. Nothing to copy, so the cell is left for the salesperson
   *   rather than filled with a guess, and returning it blank would wipe what they wrote.
   * - `unit_price`. It is the QUOTED price, not the product's, and under an always-overwrite
   *   fill a re-pick would throw away a negotiated figure. The list price is shown beside it
   *   so the discount is visible; the number that gets charged stays a decision.
   */
  const fillFromProduct = React.useCallback(
    (option: { value: string } | null): InlineDraft => {
      if (!option) return {};
      const product = productsById.current.get(option.value);
      if (!product) return {};
      const brand = (brands.data ?? []).find((row) => row.id === product.brand_id);
      const unit = (uoms.data ?? []).find((row) => row.id === product.base_uom_id);
      return {
        // The rule the backend snapshots by, so what shows now is what gets stored.
        description: product.description || product.product_name || '',
        brand_snapshot: brand?.brand_name ?? '',
        uom: unit?.uom_code ?? '',
        list_price: product.list_price ?? '',
      };
    },
    [brands.data, uoms.data],
  );

  // The order the printed quotation uses, so a line is entered reading left to right the way
  // the customer will read it back: item number, what it is, how much, then what it comes to.
  const columns = React.useMemo<InlineLineColumn<QuotationLine>[]>(
    () => [
      {
        key: 'item_no',
        header: 'Item',
        width: 70,
        /**
         * The row's position, not a box to type in.
         *
         * It was free text ("Item A"), which asked the salesperson to number 52 lines by hand
         * and to renumber all of them after every insert, and let two lines claim the same
         * letter. It counts CONTINUOUSLY through the scope - 1, 2 under the first heading and
         * 3, 4 under the second - because that is how the customer's own bill of quantities
         * reads (the client's decision); a section is a heading over the sequence, not a
         * restart of it.
         */
        kind: 'derived',
        derive: (_draft, index) => index + 1,
      },
      {
        key: 'product_id',
        header: 'Product',
        width: 200,
        kind: 'searchable-select',
        placeholder: 'Off-catalog line',
        fetchOptions: fetchProducts,
        // One decision fills the row: the description, brand, unit and list price all come off
        // the product record rather than being retyped beside it.
        onOptionSelected: (option) => fillFromProduct(option),
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
        key: 'technical_spec',
        header: 'Tech spec',
        width: 200,
        kind: 'text',
        placeholder: 'Rimless, 4/2.6L dual flush',
      },
      {
        // The draft key is the REQUEST field. The response calls the same value `brand`, and
        // naming the cell after what is sent keeps `toBody` a straight copy of the draft.
        key: 'brand_snapshot',
        header: 'Brand',
        width: 140,
        kind: 'text',
        placeholder: 'SORENTO',
        maxLength: 100,
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
        // The DRAFT's list price first: picking a product must show its price at once, and
        // reading the saved row instead is what left "List RM 0.00" beside a real product
        // until the save came back.
        annotate: (line, draft) => {
          const listPrice = draft.list_price || line?.list_price;
          return listPrice ? (
            <span className="mt-0.5 block text-end text-xs text-muted-foreground">
              {`List ${formatMyr(listPrice)}`}
            </span>
          ) : null;
        },
      },
      {
        key: 'complete_set',
        header: 'Complete set',
        width: 160,
        kind: 'text',
        placeholder: 'c/w seat cover, flush valve',
        maxLength: 100,
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
        // In the row, next to the money it governs, rather than behind the notes popover: a
        // reader scanning the Total column has to be able to see WHY a line says "rate only"
        // without opening anything, and five of them in the sample quotation is normal.
        key: 'is_rate_only',
        header: 'Rate only',
        width: 92,
        kind: 'checkbox',
      },
      {
        key: 'line_total',
        header: 'Total',
        width: 128,
        kind: 'derived',
        align: 'end',
        // Recomputed from the draft rather than read off the row, so the number moves
        // while a quantity is being typed instead of after the save lands. A rate-only line
        // prints the words: blank reads as "we forgot" and RM 0.00 reads as "free", while the
        // customer is in fact being quoted a rate that nobody adds up (AC-C2, AC-D3).
        derive: (draft) =>
          isInlineChecked(draft.is_rate_only) ? (
            <Badge variant="secondary" appearance="light">
              rate only
            </Badge>
          ) : (
            // Grouped from the STRING `multiplyMoney` produced, like the footer below it, so
            // one column is never rendered by two different formatters.
            formatMyrExact(multiplyMoney(draft.quantity, draft.unit_price) ?? '0')
          ),
        /**
         * The version's total, under the column it sums. It used to sit in the metadata strip
         * beside "Issued by" and "Opened", where it read as one more fact about the version
         * rather than as the sum of the numbers directly above it.
         *
         * Summed from the LIVE drafts, so it moves with the numbers above it. Reading the saved
         * rows instead left the footer stating last save's answer while the cells said something
         * else, and the first thing anybody does after changing a quantity is look down here.
         * Off the STRINGS, to the cent, and skipping rate-only lines exactly as the backend's
         * total does, so this footer and the document's grand total cannot drift apart.
         */
        footer: (drafts) => {
          const total = totalFromDrafts(drafts);
          return total === null ? '-' : formatMyrExact(total);
        },
      },
    ],
    [fetchProducts, fillFromProduct, uomOptions],
  );

  const toDraft = React.useCallback(
    (line: QuotationLine): InlineDraft => ({
      product_id: line.product_id ?? '',
      description: line.description ?? '',
      technical_spec: line.technical_spec ?? '',
      // The response names this one `brand`, the request `brand_snapshot`. The draft holds the
      // request's name so the payload stays a copy rather than a translation.
      brand_snapshot: line.brand ?? '',
      quantity: line.quantity ?? '1',
      uom: line.uom ?? '',
      unit_price: line.unit_price ?? '',
      complete_set: line.complete_set ?? '',
      unit_type: line.unit_type ?? '',
      is_rate_only: line.is_rate_only ? INLINE_CHECKED : '',
      band_label: line.band_label ?? '',
      notes: line.notes ?? '',
      // No column of its own: read under the unit price, and never sent back (the server
      // snapshots it from the product it belongs to).
      list_price: line.list_price ?? '',
    }),
    [],
  );

  const emptyDraft = React.useCallback(
    (): InlineDraft => ({
      product_id: '',
      description: '',
      technical_spec: '',
      brand_snapshot: '',
      quantity: '1',
      uom: '',
      unit_price: '',
      complete_set: '',
      unit_type: '',
      is_rate_only: '',
      band_label: '',
      notes: '',
      list_price: '',
    }),
    [],
  );

  /**
   * The same sum the footer shows, pushed to whoever asked for it.
   *
   * A ref rather than state: this fires on every keystroke that moves a number, and the editor
   * itself has nothing to re-render over a figure it is not drawing. The guard also keeps a
   * parent from re-rendering when a description changes and the money did not.
   */
  const lastTotal = React.useRef<string | null>(null);
  const handleDraftsChange = React.useCallback(
    (drafts: InlineDraft[]) => {
      // Lines that exist but have not been turned into drafts yet are not "nothing quoted":
      // announcing RM 0.00 on the way in would flash a wrong figure in whatever is showing it.
      if (drafts.length === 0 && sortedLines.length > 0) return;
      const total = totalFromDrafts(drafts);
      if (total === null || total === lastTotal.current) return;
      lastTotal.current = total;
      onTotalChange?.(total);
    },
    [onTotalChange, sortedLines.length],
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
        addSectionLabel="Add a section"
        onDraftsChange={handleDraftsChange}
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
        // Free text off the customer's own bill of quantities. The CRM does not model bill and
        // page numbers because the next customer numbers their BQ differently (AC-C3).
        band={{
          key: 'band_label',
          label: 'Section heading',
          placeholder: 'e.g. BILL NO 3 PAGE 15/4, OPTIONAL ITEMS',
          maxLength: 150,
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

/**
 * The scope's money, off the LIVE drafts.
 *
 * Rate-only lines contribute nothing, the same rule the PDF and the backend total apply: the
 * customer is being shown a rate, and adding the sample quotation's five alternates would have
 * overstated it by RM 235,000. A cell that is not a number yet counts as zero rather than
 * blanking the whole total, so the figure survives a half-typed price.
 */
function totalFromDrafts(drafts: InlineDraft[]): string | null {
  return sumMoney(
    drafts
      .filter((draft) => !isInlineChecked(draft.is_rate_only))
      .map((draft) => multiplyMoney(draft.quantity, draft.unit_price) ?? '0'),
  );
}

/**
 * Draft to the body the per-line endpoint takes.
 *
 * `brand_snapshot` is the request's name for the field the response calls `brand`. The
 * asymmetry is the API's and is deliberate (the column snapshots the brand at the moment the
 * line was priced), so it is honoured here rather than smoothed over.
 *
 * `item_label` is NOT sent any more: the ITEM column is the row's position now, so a stored
 * label could only ever disagree with what is on screen.
 */
function toBody(draft: InlineDraft) {
  return {
    product_id: draft.product_id || null,
    description_snapshot: draft.description.trim() || null,
    unit_price: draft.unit_price.trim() || '0',
    quantity: draft.quantity.trim() || '1',
    uom: draft.uom.trim() || null,
    unit_type: (draft.unit_type || null) as UnitType | null,
    notes: draft.notes.trim() || null,
    brand_snapshot: draft.brand_snapshot.trim() || null,
    technical_spec: draft.technical_spec.trim() || null,
    complete_set: draft.complete_set.trim() || null,
    band_label: draft.band_label.trim() || null,
    is_rate_only: isInlineChecked(draft.is_rate_only),
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
